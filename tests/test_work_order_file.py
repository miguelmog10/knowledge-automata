import copy
import json
from datetime import UTC, datetime, timedelta

import pytest

from knowledge_automata.core import work_orders as wo
from knowledge_automata.core.schemas import (
    LEDGER_ENTRY_SCHEMA,
    WORK_ORDERS_SCHEMA,
    load_schema,
)
from knowledge_automata.core.validation import validate_work_orders_file
from knowledge_automata.core.work_orders import WorkOrder
from knowledge_automata.storage.work_order_store import WorkOrderStore, WorkOrderStoreError

NOW = datetime(2026, 11, 3, 14, 0, 5, tzinfo=UTC)
LATER = NOW + timedelta(seconds=30)
RUN_ID = "1b9e8a2c-4f3d-4c6b-9a1e-2d7f5e8c3b10"
OTHER_RUN = "2c0f9b3d-5a4e-4d7c-8b2f-3e8a6f9d4c21"
REGISTERS = ["decision-log", "risk-register"]
ORDERS = [
    WorkOrder(1, "decision-log", "Julie confirmed the status paths", ("Julie confirmed.",)),
    WorkOrder(2, "decision-log", "The team moved the pilot to May", ("The pilot moves.",)),
    WorkOrder(3, "risk-register", "The supplier may be late", ("The supplier may be late.",)),
]
PRODUCED = {
    "schema_version": "1.0",
    "prompt_version": "decision-registrar.v2",
    "model": "command-a-plus-05-2026",
    "record_id": "DEC-0003",
    "register": "decision-log",
}
REJECTED = {
    "stage": "draft",
    "error_paths": ["$.evidence[0]"],
    "prompt_version": "decision-registrar.v2",
    "attempts": 2,
    "register": "decision-log",
    "run_id": RUN_ID,
}


def new(max_items=10, orders=ORDERS):
    return wo.new_file(
        artifact_id="ART-0006",
        run_id=RUN_ID,
        model="command-a-plus-05-2026",
        prompt_version="governor.v1",
        attempts=1,
        definitions=["decision-log.v1", "risk-register.v1"],
        work_orders=orders,
        routed={"decision-log"},
        max_items=max_items,
        now=NOW,
    )


def errors_of(data):
    return validate_work_orders_file(data).errors


# The file and its validation


def test_a_new_file_matches_the_handoff_example_and_is_valid():
    data = new()
    assert errors_of(data) == ()
    assert list(data) == list(load_schema(WORK_ORDERS_SCHEMA)["properties"])
    assert data["schema_version"] == "1.0"
    assert data["created_at"] == data["updated_at"] == "2026-11-03T14:00:05Z"
    assert [order["state"] for order in data["orders"]] == ["pending", "pending", "not-routed"]
    assert data["orders"][0] == {
        "number": 1,
        "register": "decision-log",
        "label": "Julie confirmed the status paths",
        "evidence": ["Julie confirmed."],
        "state": "pending",
        "rejected": [],
    }


def test_produced_and_rejected_reference_the_ledger_definitions():
    order = load_schema(WORK_ORDERS_SCHEMA)["$defs"]["order"]["properties"]
    ledger_id = load_schema(LEDGER_ENTRY_SCHEMA)["$id"]
    assert order["produced"]["$ref"] == f"{ledger_id}#/$defs/produced_record"
    assert order["rejected"]["items"]["$ref"] == f"{ledger_id}#/$defs/rejected_draft"


def test_the_ledger_reference_resolves_so_bad_items_are_caught():
    data = new()
    data["orders"][0]["state"] = "recorded"
    data["orders"][0]["produced"] = {**PRODUCED, "change": "merger"}
    data["orders"][1]["state"] = "rejected"
    data["orders"][1]["rejected"] = [{**REJECTED, "stage": "guessing"}]
    errors = errors_of(data)
    assert any(error.startswith("$.orders[0].produced") for error in errors)
    assert any(error.startswith("$.orders[1].rejected[0]") for error in errors)


def test_a_recorded_order_may_also_list_drafts_rejected_before_it():
    data = wo.with_order_result(new(), 1, now=NOW, rejected=REJECTED)
    data = wo.with_order_result(data, 1, now=LATER, produced=PRODUCED)
    order = data["orders"][0]
    assert order["state"] == "recorded"
    assert order["rejected"] == [REJECTED]
    assert errors_of(data) == ()


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            lambda d: d["orders"][1].update(number=5),
            "$.orders[1].number: expected 2, got 5",
        ),
        (
            lambda d: d["orders"][0].update(state="recorded"),
            "$.orders[0]: a 'recorded' order needs its produced item",
        ),
        (
            lambda d: d["orders"][0].update(produced=PRODUCED),
            "$.orders[0].produced: only a 'recorded' order has one",
        ),
        (
            lambda d: d["orders"][0].update(state="rejected"),
            "$.orders[0].rejected: a 'rejected' order lists at least one rejected item",
        ),
        (
            lambda d: d["orders"][0].update(rejected=[REJECTED]),
            "$.orders[0].rejected: must be empty for a 'pending' order",
        ),
        (
            lambda d: d["orders"][2].update(rejected=[REJECTED]),
            "$.orders[2].rejected: must be empty for a 'not-routed' order",
        ),
        (
            lambda d: d.update(updated_at="2026-11-03T13:00:00Z"),
            "$.updated_at: earlier than created_at",
        ),
        (
            lambda d: d.update(schema_version="2.0"),
            "$.schema_version: '2.0' is not a 1.x version",
        ),
        (
            lambda d: d.update(schema_version="1.9"),
            "$.schema_version: '1.9' is newer than this code's '1.0'",
        ),
    ],
)
def test_order_numbers_and_states_must_agree(change, message):
    data = new()
    change(data)
    assert message in errors_of(data)


@pytest.mark.parametrize(
    ("produced", "rejected", "message"),
    [
        (
            {**PRODUCED, "work_order": 1},
            None,
            "$.orders[0].produced.work_order: the order's number stands in for it",
        ),
        (
            {**PRODUCED, "register": "risk-register"},
            None,
            "$.orders[0].produced.register: not the order's register",
        ),
        (
            {**PRODUCED, "change": "supersession"},
            None,
            "$.orders[0].produced: a 'supersession' needs the related_id it superseded",
        ),
        (
            None,
            {**REJECTED, "work_order": 1},
            "$.orders[0].rejected[0].work_order: the order's number stands in for it",
        ),
        (
            None,
            {"stage": "governor", **{k: REJECTED[k] for k in ("error_paths", "prompt_version")}}
            | {"attempts": 1, "run_id": RUN_ID},
            "$.orders[0].rejected[0].stage: a work order's draft is never rejected by the Governor",
        ),
        (
            None,
            {**REJECTED, "register": "risk-register"},
            "$.orders[0].rejected[0].register: not the order's register",
        ),
        (
            None,
            {key: value for key, value in REJECTED.items() if key != "run_id"},
            "$.orders[0].rejected[0]: needs the run_id that rejected it",
        ),
    ],
)
def test_order_items_must_belong_to_their_order(produced, rejected, message):
    data = new()
    order = data["orders"][0]
    if produced is not None:
        order.update(state="recorded", produced=produced)
    else:
        order.update(state="rejected", rejected=[rejected])
    assert message in errors_of(data)


def test_validation_never_raises_for_non_objects():
    for value in (None, [], "file", 3):
        assert errors_of(value)


# Order results


def test_with_order_result_records_or_rejects_and_leaves_the_input_alone():
    data = new()
    before = copy.deepcopy(data)
    rejected = wo.with_order_result(data, 2, now=LATER, rejected={**REJECTED, "work_order": 2})
    recorded = wo.with_order_result(rejected, 1, now=LATER, produced={**PRODUCED, "work_order": 1})
    assert data == before
    assert recorded["updated_at"] == "2026-11-03T14:00:35Z"
    assert recorded["orders"][0]["state"] == "recorded"
    assert recorded["orders"][0]["produced"] == PRODUCED
    assert list(recorded["orders"][0]) == [
        "number",
        "register",
        "label",
        "evidence",
        "state",
        "produced",
        "rejected",
    ]
    assert recorded["orders"][1]["rejected"] == [REJECTED]
    assert errors_of(recorded) == ()


@pytest.mark.parametrize(
    ("number", "kwargs", "message"),
    [
        (1, {}, "Give exactly one of produced and rejected"),
        (1, {"produced": PRODUCED, "rejected": REJECTED}, "Give exactly one"),
        (4, {"produced": PRODUCED}, "No work order 4 in ART-0006"),
        (3, {"produced": PRODUCED}, "Work order 3 is not-routed; it never changes"),
    ],
)
def test_with_order_result_refuses_a_final_or_missing_order(number, kwargs, message):
    with pytest.raises(ValueError, match=message):
        wo.with_order_result(new(), number, now=LATER, **kwargs)


def test_a_recorded_order_never_changes():
    data = wo.with_order_result(new(), 1, now=LATER, produced=PRODUCED)
    with pytest.raises(ValueError, match="Work order 1 is recorded"):
        wo.with_order_result(data, 1, now=LATER, rejected=REJECTED)


def test_orders_to_run_depend_on_the_ledger_status():
    data = wo.with_order_result(new(), 1, now=LATER, rejected=REJECTED)
    assert [order["number"] for order in wo.orders_to_run(data, "accepted")] == [2]
    for status in ("failed", "processed"):
        assert [order["number"] for order in wo.orders_to_run(data, status)] == [1, 2]
    data = wo.with_order_result(data, 2, now=LATER, produced=PRODUCED)
    assert [order["number"] for order in wo.orders_to_run(data, "accepted")] == []
    assert [order["number"] for order in wo.orders_to_run(data, "failed")] == [1]


# The hold


def history(*steps):
    return [{"status": status, "by": by, **extra} for status, by, extra in steps]


ACCEPTED = ("accepted", "sensor", {})
HELD = ("held", "governor", {"run_id": RUN_ID})
RELEASED = ("accepted", "operator", {})


def test_a_file_with_more_routed_orders_than_its_max_items_is_held_until_released():
    data = new(max_items=1)
    assert wo.needs_hold(data, history(ACCEPTED))
    assert wo.needs_hold(data, history(ACCEPTED, HELD))
    assert not wo.needs_hold(data, history(ACCEPTED, HELD, RELEASED))
    assert wo.is_released(data, history(ACCEPTED, HELD, RELEASED))


def test_not_routed_orders_do_not_count_toward_the_limit():
    assert not wo.needs_hold(new(max_items=2), history(ACCEPTED))
    assert wo.routed_orders(new()) == new()["orders"][:2]


def test_a_release_covers_only_the_file_of_the_held_run():
    other_hold = ("held", "governor", {"run_id": OTHER_RUN})
    assert wo.needs_hold(new(max_items=1), history(ACCEPTED, other_hold, RELEASED))
    assert not wo.is_released(new(max_items=1), history(ACCEPTED, HELD, ACCEPTED))


def test_a_file_whose_orders_started_is_never_held_again():
    data = wo.with_order_result(new(max_items=1), 1, now=LATER, rejected=REJECTED)
    assert not wo.needs_hold(data, history(ACCEPTED))


# The Ledger, rebuilt from the file


def test_the_ledger_governor_block_counts_orders_per_register_in_register_order():
    orders = [ORDERS[2], *ORDERS[:2]]
    orders = [WorkOrder(i + 1, o.register, o.label, o.evidence) for i, o in enumerate(orders)]
    block = wo.ledger_governor_block(new(orders=orders), REGISTERS)
    assert block == {
        "model": "command-a-plus-05-2026",
        "prompt_version": "governor.v1",
        "attempts": 1,
        "definitions": ["decision-log.v1", "risk-register.v1"],
        "run_id": RUN_ID,
        "work_orders": [
            {"register": "decision-log", "count": 2, "routed": True},
            {"register": "risk-register", "count": 1, "routed": False},
        ],
    }
    assert wo.ledger_governor_block(new(orders=[]), REGISTERS)["work_orders"] == []


def entry(produced=(), rejected=(), governor=None):
    data = {"produced": list(produced), "rejected": list(rejected)}
    if governor is not None:
        data["governor"] = governor
    return data


def test_rebuilt_lists_number_each_item_in_order_number():
    data = wo.with_order_result(new(), 2, now=LATER, produced=PRODUCED)
    data = wo.with_order_result(data, 1, now=LATER, rejected=REJECTED)
    governor_stage = {"stage": "governor", "error_paths": ["$"], "prompt_version": "governor.v1"}
    produced, rejected = wo.rebuilt_lists(entry(rejected=[governor_stage]), data)
    assert produced == [{**PRODUCED, "work_order": 2}]
    assert rejected == [governor_stage, {**REJECTED, "work_order": 1}]


def test_a_rerun_keeps_the_ledger_lists_in_place_and_appends_new_results():
    # Order 1 rejected, order 2 recorded, order 3 failed on a provider error; the rerun
    # records orders 1 and 3.
    orders = [WorkOrder(i, "decision-log", f"Order {i}", (f"Quote {i}.",)) for i in (1, 2, 3)]
    first = wo.with_order_result(new(orders=orders), 1, now=NOW, rejected=REJECTED)
    first = wo.with_order_result(first, 2, now=NOW, produced={**PRODUCED, "record_id": "DEC-2"})
    failed = entry(*wo.rebuilt_lists(entry(), first))
    assert failed == entry(
        [{**PRODUCED, "record_id": "DEC-2", "work_order": 2}],
        [{**REJECTED, "work_order": 1}],
    )
    rerun = wo.with_order_result(first, 1, now=LATER, produced={**PRODUCED, "record_id": "DEC-1"})
    rerun = wo.with_order_result(rerun, 3, now=LATER, produced={**PRODUCED, "record_id": "DEC-3"})
    produced, rejected = wo.rebuilt_lists(failed, rerun)
    assert [(item["record_id"], item["work_order"]) for item in produced] == [
        ("DEC-2", 2),
        ("DEC-1", 1),
        ("DEC-3", 3),
    ]
    assert rejected == failed["rejected"]


def test_rejected_items_the_ledger_already_lists_are_matched_with_counts():
    data = wo.with_order_result(new(), 1, now=NOW, rejected=REJECTED)
    data = wo.with_order_result(data, 1, now=LATER, rejected=REJECTED)
    numbered = {**REJECTED, "work_order": 1}
    assert wo.rebuilt_lists(entry(rejected=[numbered]), data)[1] == [numbered, numbered]
    assert wo.rebuilt_lists(entry(rejected=[numbered, numbered]), data)[1] == [numbered] * 2


def test_the_ledger_is_behind_when_the_file_has_results_or_a_governor_run_it_lacks():
    data = wo.with_order_result(new(), 1, now=LATER, produced=PRODUCED)
    block = wo.ledger_governor_block(data, REGISTERS)
    assert wo.ledger_is_behind(entry(), data, REGISTERS)
    assert wo.ledger_is_behind(entry([{**PRODUCED, "work_order": 1}]), data, REGISTERS)
    assert not wo.ledger_is_behind(
        entry([{**PRODUCED, "work_order": 1}], governor=block), data, REGISTERS
    )


# The guard before any call


def record(record_id, *artifact_ids):
    return {"id": record_id, "history": [{"artifact_id": a} for a in artifact_ids]}


def test_history_counts_match_the_recorded_orders():
    supersession = {
        **PRODUCED,
        "record_id": "DEC-0004",
        "change": "supersession",
        "related_id": "DEC-0001",
    }
    data = wo.with_order_result(new(), 1, now=LATER, produced=PRODUCED)
    data = wo.with_order_result(data, 2, now=LATER, produced=supersession)
    records = [
        record("DEC-0001", "ART-0001", "ART-0006"),
        record("DEC-0003", "ART-0006"),
        record("DEC-0004", "ART-0006"),
        record("DEC-0005", "ART-0002"),
    ]
    assert wo.history_count_problems(data, records, "ART-0006") == []


def test_a_record_changed_by_an_order_whose_result_was_not_saved_is_found():
    # A split duplicate: order 1 recorded DEC-0003, then order 2 updated it and the run
    # stopped before saving order 2's result.
    data = wo.with_order_result(new(), 1, now=LATER, produced=PRODUCED)
    records = [record("DEC-0003", "ART-0006", "ART-0006"), record("DEC-0007", "ART-0006")]
    assert wo.history_count_problems(data, records, "ART-0006") == [
        "DEC-0003: 2 changes from ART-0006 in its history, 1 change in the work orders file",
        "DEC-0007: 1 change from ART-0006 in its history, 0 changes in the work orders file",
    ]


def test_a_recorded_order_whose_record_is_missing_is_found():
    data = wo.with_order_result(new(), 1, now=LATER, produced=PRODUCED)
    assert wo.history_count_problems(data, [], "ART-0006") == [
        "DEC-0003: 0 changes from ART-0006 in its history, 1 change in the work orders file"
    ]


# The store


def test_the_store_writes_once_and_reads_back(tmp_path):
    store = WorkOrderStore(tmp_path)
    assert store.load("ART-0006") is None
    path = store.save_new(new())
    assert path == tmp_path / "work-orders" / "ART-0006.json"
    assert store.load("ART-0006") == new()
    assert path.read_bytes().endswith(b"}\n")
    with pytest.raises(WorkOrderStoreError, match="already exists, not overwritten"):
        store.save_new(new())


def test_the_store_refuses_an_invalid_file(tmp_path):
    store = WorkOrderStore(tmp_path)
    data = new()
    data["orders"][0]["state"] = "recorded"
    with pytest.raises(WorkOrderStoreError, match="is invalid and was not written"):
        store.save_new(data)
    assert not store.exists("ART-0006")
    with pytest.raises(WorkOrderStoreError, match="Not an artifact ID"):
        store.path("../ART-0006")


def test_a_stored_file_that_is_not_valid_is_refused_when_read(tmp_path):
    store = WorkOrderStore(tmp_path)
    store.save_new(new())
    path = store.path("ART-0006")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["orders"][0]["number"] = 7
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(WorkOrderStoreError, match="number: expected 1, got 7"):
        store.load("ART-0006")
    path.write_text(json.dumps({**new(), "artifact_id": "ART-0007"}), encoding="utf-8")
    with pytest.raises(WorkOrderStoreError, match="holds the work orders of 'ART-0007'"):
        store.load("ART-0006")
    path.write_text("{", encoding="utf-8")
    with pytest.raises(WorkOrderStoreError, match="not valid UTF-8 JSON"):
        store.load("ART-0006")


def test_save_progress_saves_each_order_result(tmp_path):
    store = WorkOrderStore(tmp_path)
    first = new()
    store.save_new(first)
    second = wo.with_order_result(first, 1, now=LATER, rejected=REJECTED)
    store.save_progress(first, second)
    third = wo.with_order_result(second, 1, now=LATER, produced=PRODUCED)
    store.save_progress(second, third)
    assert store.load("ART-0006") == third


def test_save_progress_refuses_a_stale_file(tmp_path):
    store = WorkOrderStore(tmp_path)
    first = new()
    store.save_new(first)
    second = wo.with_order_result(first, 1, now=LATER, rejected=REJECTED)
    store.save_progress(first, second)
    with pytest.raises(WorkOrderStoreError, match="changed since it was read"):
        store.save_progress(first, wo.with_order_result(first, 2, now=LATER, produced=PRODUCED))
    assert store.load("ART-0006") == second


def changed(data, change):
    result = copy.deepcopy(data)
    change(result)
    return result


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d.update(max_items=20), "a work orders file cannot change max_items"),
        (lambda d: d.update(run_id=OTHER_RUN), "a work orders file cannot change run_id"),
        (lambda d: d["orders"][1]["evidence"].append("New."), "work order 2: cannot change"),
        (lambda d: d["orders"][1].update(label="New"), "work order 2: cannot change label"),
        (lambda d: d["orders"].pop(), "work orders cannot be added or removed"),
        (
            lambda d: d["orders"][0]["produced"].update(record_id="DEC-0009"),
            "work order 1 is recorded; it never changes",
        ),
        (
            lambda d: d["orders"][1].update(rejected=[], state="pending"),
            "work order 2: cannot go from rejected to pending",
        ),
        (
            lambda d: d["orders"][1].update(rejected=[{**REJECTED, "attempts": 1}, REJECTED]),
            "work order 2: the new rejected list must keep the old one unchanged",
        ),
    ],
)
def test_save_progress_allows_only_order_results(tmp_path, change, message):
    store = WorkOrderStore(tmp_path)
    first = new()
    store.save_new(first)
    old = wo.with_order_result(first, 1, now=LATER, produced=PRODUCED)
    old = wo.with_order_result(old, 2, now=LATER, rejected=REJECTED)
    store.save_progress(first, old)
    with pytest.raises(WorkOrderStoreError, match=message):
        store.save_progress(old, changed(old, change))
    assert store.load("ART-0006") == old


def test_a_not_routed_order_never_changes(tmp_path):
    store = WorkOrderStore(tmp_path)
    first = new()
    store.save_new(first)
    new_file = changed(
        first,
        lambda d: d["orders"][2].update(
            state="rejected", rejected=[{**REJECTED, "register": "risk-register"}]
        ),
    )
    with pytest.raises(WorkOrderStoreError, match="work order 3 is not-routed"):
        store.save_progress(first, new_file)
