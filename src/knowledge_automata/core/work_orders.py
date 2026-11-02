"""Work orders: the items the Governor (orchestrator) found in an artifact (ADR-0018).

Code builds the work orders from a checked Governor reply: it sorts the items by where
their earliest quote appears in the artifact, numbers them from 1 and builds each label
from the item's first quote, so everything in a work order is verified artifact text.

The work orders file (``schemas/core/work-orders.v1.json``) saves them with each order's
state and results, so an interrupted run continues without calling the Governor again.
The functions here build and change that file and rebuild the Ledger's lists from it;
they are pure: ``storage/work_order_store.py`` reads and writes the file.
"""

import copy
from collections import Counter
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from knowledge_automata.core.evidence import normalize_quote, normalize_text
from knowledge_automata.core.records import format_timestamp, order_like_schema
from knowledge_automata.core.schemas import LEDGER_ENTRY_SCHEMA, WORK_ORDERS_SCHEMA, load_schema

LABEL_MAX_CHARS = 60
ELLIPSIS = "..."
# Straight and typographic quote marks, as normalize_quote strips them.
QUOTE_MARKS = "\"'\u2018\u2019\u201a\u201b\u201c\u201d\u201e\u201f"


@dataclass(frozen=True)
class WorkOrder:
    number: int  # from 1, in artifact order
    register: str
    label: str  # placeholder built from the first quote; the record's title comes later
    evidence: tuple[str, ...]  # verified quotes, in the Governor's order


def placeholder_label(quote: str) -> str:
    """The quote without surrounding quote marks, whitespace collapsed, cut after 60 characters.

    When cut, ``...`` is added after the last whole word (the 60 do not count it); a
    single word longer than 60 characters is cut at 60.
    """
    text = " ".join(quote.split()).strip(QUOTE_MARKS + " ")
    if len(text) <= LABEL_MAX_CHARS:
        return text
    cut = text.rfind(" ", 0, LABEL_MAX_CHARS + 1)
    head = text[:cut] if cut > 0 else text[:LABEL_MAX_CHARS]
    return head + ELLIPSIS


def build_work_orders(
    items: Sequence[Mapping[str, Any]], artifact_text: str
) -> tuple[WorkOrder, ...]:
    """Sort checked items by their earliest quote, number them and label them.

    An item's position is the smallest position of any of its quotes in the normalized
    artifact; ties keep the model's order. Expects a reply that passed
    ``validate_work_orders``: a quote that cannot be found raises ``ValueError``.
    """
    artifact = normalize_text(artifact_text)

    def earliest(item: Mapping[str, Any]) -> int:
        positions = [artifact.find(normalize_quote(quote)) for quote in item["evidence"]]
        if not positions or min(positions) < 0:
            raise ValueError("build_work_orders expects checked items whose quotes are found")
        return min(positions)

    ordered = sorted(items, key=earliest)  # sorted is stable: ties keep the model's order
    return tuple(
        WorkOrder(
            number=number,
            register=item["register"],
            label=placeholder_label(item["evidence"][0]),
            evidence=tuple(item["evidence"]),
        )
        for number, item in enumerate(ordered, start=1)
    )


# The work orders file

FILE_SCHEMA_VERSION = load_schema(WORK_ORDERS_SCHEMA)["x-version"]
# Orders that have run at least once; a file with one of these is never held again.
STARTED_STATES = frozenset({"recorded", "rejected"})
FINAL_STATES = frozenset({"recorded", "not-routed"})


def _file_defs(name: str) -> dict[str, Any]:
    return load_schema(WORK_ORDERS_SCHEMA)["$defs"][name]


def _ledger_defs(name: str) -> dict[str, Any]:
    return load_schema(LEDGER_ENTRY_SCHEMA)["$defs"][name]


def new_file(
    *,
    artifact_id: str,
    run_id: str,
    model: str,
    prompt_version: str,
    attempts: int,
    definitions: Sequence[str],
    work_orders: Sequence[WorkOrder],
    routed: Collection[str],
    max_items: int,
    now: datetime,
) -> dict[str, Any]:
    """Return a new work orders file: every order ``pending``, or ``not-routed`` when its
    register is not in ``routed`` (the registers with a Registrar)."""
    timestamp = format_timestamp(now)
    orders = [
        {
            "number": order.number,
            "register": order.register,
            "label": order.label,
            "evidence": list(order.evidence),
            "state": "pending" if order.register in routed else "not-routed",
            "rejected": [],
        }
        for order in work_orders
    ]
    return {
        "schema_version": FILE_SCHEMA_VERSION,
        "artifact_id": artifact_id,
        "created_at": timestamp,
        "updated_at": timestamp,
        "run_id": run_id,
        "governor": {
            "model": model,
            "prompt_version": prompt_version,
            "attempts": attempts,
            "definitions": list(definitions),
        },
        "max_items": max_items,
        "orders": orders,
    }


def with_order_result(
    file: Mapping[str, Any],
    number: int,
    *,
    now: datetime,
    produced: Mapping[str, Any] | None = None,
    rejected: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a copy of ``file`` with one order's result: ``recorded`` with its produced
    item, or ``rejected`` with one more rejected item. Items are stored without
    ``work_order``. Raises ``ValueError`` for an order that is final or does not exist."""
    if (produced is None) == (rejected is None):
        raise ValueError("Give exactly one of produced and rejected")
    updated = copy.deepcopy(dict(file))
    orders = updated["orders"]
    if not 1 <= number <= len(orders):
        raise ValueError(f"No work order {number} in {file['artifact_id']}")
    order = orders[number - 1]
    if order["state"] in FINAL_STATES:
        raise ValueError(f"Work order {number} is {order['state']}; it never changes")
    if produced is not None:
        item = {key: value for key, value in produced.items() if key != "work_order"}
        order["produced"] = order_like_schema(copy.deepcopy(item), _ledger_defs("produced_record"))
        order["state"] = "recorded"
    else:
        item = {key: value for key, value in rejected.items() if key != "work_order"}
        order["rejected"].append(
            order_like_schema(copy.deepcopy(item), _ledger_defs("rejected_draft"))
        )
        order["state"] = "rejected"
    orders[number - 1] = order_like_schema(order, _file_defs("order"))
    updated["updated_at"] = format_timestamp(now)
    return updated


def routed_orders(file: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The orders for a register with a Registrar, in order number."""
    return [order for order in file["orders"] if order["state"] != "not-routed"]


def orders_to_run(file: Mapping[str, Any], status: str) -> list[dict[str, Any]]:
    """The orders a run drafts, in order number (3.7).

    ``accepted`` (a first run, one interrupted before its Ledger write, or a release) runs
    only ``pending`` orders; ``failed`` and ``processed`` (a rerun) also run ``rejected``
    ones. ``recorded`` and ``not-routed`` orders never run.
    """
    states = {"pending"} if status == "accepted" else {"pending", "rejected"}
    return [order for order in file["orders"] if order["state"] in states]


def is_released(file: Mapping[str, Any], history: Sequence[Mapping[str, Any]]) -> bool:
    """Whether the Ledger history holds this file's run and then releases it: a ``held``
    entry with the file's ``run_id``, followed by ``accepted`` by ``operator``."""
    for step, following in zip(history, history[1:], strict=False):
        if (
            step["status"] == "held"
            and step.get("run_id") == file["run_id"]
            and following["status"] == "accepted"
            and following["by"] == "operator"
        ):
            return True
    return False


def needs_hold(file: Mapping[str, Any], history: Sequence[Mapping[str, Any]]) -> bool:
    """Whether the file must be held before any draft (3.7): no order has run yet, it has
    more routed orders than its own ``max_items``, and the Operator has not released it."""
    started = any(order["state"] in STARTED_STATES for order in file["orders"])
    if started or len(routed_orders(file)) <= file["max_items"]:
        return False
    return not is_released(file, history)


def ledger_governor_block(file: Mapping[str, Any], register_names: Sequence[str]) -> dict[str, Any]:
    """The Ledger's ``governor`` block: the file's Governor run, and how many work orders
    it found per register, in register order, leaving out registers with none."""
    counts: Counter[str] = Counter(order["register"] for order in file["orders"])
    routed = {order["register"] for order in routed_orders(file)}
    names = [name for name in register_names if counts[name]]
    names += [name for name in counts if name not in names]
    return {
        **copy.deepcopy(file["governor"]),
        "run_id": file["run_id"],
        "work_orders": [
            {"register": name, "count": counts[name], "routed": name in routed} for name in names
        ],
    }


def rebuilt_lists(
    entry: Mapping[str, Any], file: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Rebuild the Ledger's ``produced`` and ``rejected`` lists from the work orders file.

    The entry's items stay first, unchanged and in place, so both lists only ever grow;
    then each order's items the entry does not list yet are added with their
    ``work_order``, in order number.
    """
    produced = [copy.deepcopy(dict(item)) for item in entry["produced"]]
    listed = {item.get("work_order") for item in produced}
    rejected = [copy.deepcopy(dict(item)) for item in entry["rejected"]]
    unmatched = list(rejected)
    for order in file["orders"]:
        number = order["number"]
        if order["state"] == "recorded" and number not in listed:
            produced.append({**copy.deepcopy(order["produced"]), "work_order": number})
        for item in order["rejected"]:
            numbered = {**copy.deepcopy(item), "work_order": number}
            if numbered in unmatched:
                unmatched.remove(numbered)
            else:
                rejected.append(numbered)
    return produced, rejected


def ledger_is_behind(
    entry: Mapping[str, Any], file: Mapping[str, Any], register_names: Sequence[str]
) -> bool:
    """Whether the file holds results or a Governor run the Ledger entry does not list."""
    produced, rejected = rebuilt_lists(entry, file)
    return (
        produced != entry["produced"]
        or rejected != entry["rejected"]
        or entry.get("governor") != ledger_governor_block(file, register_names)
    )


def history_count_problems(
    file: Mapping[str, Any], records: Iterable[Mapping[str, Any]], artifact_id: str
) -> list[str]:
    """The records whose history disagrees with the file's recorded orders (3.5).

    Every change a recorded order makes adds exactly one history entry naming the artifact
    to each record it touches (``record_id``, and ``related_id`` for a supersession). A
    record with more such entries than recorded orders touching it was changed by a run
    that stopped before saving the order's result.
    """
    expected: Counter[str] = Counter()
    for order in file["orders"]:
        if order["state"] == "recorded":
            item = order["produced"]
            expected[item["record_id"]] += 1
            if "related_id" in item:
                expected[item["related_id"]] += 1
    found: Counter[str] = Counter()
    for record in records:
        count = sum(1 for step in record["history"] if step["artifact_id"] == artifact_id)
        if count:
            found[record["id"]] = count
    return [
        f"{record_id}: {_changes(found[record_id])} from {artifact_id} in its history, "
        f"{_changes(expected[record_id])} in the work orders file"
        for record_id in sorted(expected.keys() | found.keys())
        if expected[record_id] != found[record_id]
    ]


def _changes(count: int) -> str:
    return f"{count} change{'s' if count != 1 else ''}"
