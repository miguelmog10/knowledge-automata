"""Work orders: the items the Governor (orchestrator) found in an artifact (ADR-0018).

Code builds the work orders from a checked Governor reply: it sorts the items by where
their earliest quote appears in the artifact, numbers them from 1 and builds each label
from the item's first quote, so everything in a work order is verified artifact text.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from knowledge_automata.core.evidence import normalize_quote, normalize_text

LABEL_MAX_CHARS = 60
ELLIPSIS = "..."


@dataclass(frozen=True)
class WorkOrder:
    number: int  # from 1, in artifact order
    register: str
    label: str  # placeholder built from the first quote; the record's title comes later
    evidence: tuple[str, ...]  # verified quotes, in the Governor's order


def placeholder_label(quote: str) -> str:
    """The quote with whitespace collapsed, cut at a word boundary after 60 characters.

    When cut, ``...`` is added after the last whole word (the 60 do not count it); a
    single word longer than 60 characters is cut at 60.
    """
    text = " ".join(quote.split())
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
