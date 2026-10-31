"""Finding the records a new draft might relate to (ADR-0017).

Pure functions: no file access and no model calls. The Comparator (reconciliation) embeds
the texts built here, keeps the top K by cosine similarity, then reranks them.
"""

import math
from collections.abc import Mapping, Sequence
from typing import Any

COMPARED_FIELDS = ("title", "statement", "context")


def comparison_text(content: Mapping[str, Any]) -> str:
    """Return the title, statement and context (when present), joined with newlines.

    Only what was decided is compared; rationale, alternatives and impacts are left out.
    """
    return "\n".join(str(content[field]) for field in COMPARED_FIELDS if content.get(field))


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Return the cosine similarity of two vectors of the same length; 0.0 for a zero vector."""
    if len(a) != len(b):
        raise ValueError(f"Vectors differ in length: {len(a)} and {len(b)}")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def _id_order(record_id: str) -> tuple[str, int]:
    prefix, _, sequence = record_id.rpartition("-")
    return (prefix, int(sequence)) if sequence.isdigit() else (record_id, -1)


def top_k(
    query_vector: Sequence[float], vectors_by_id: Mapping[str, Sequence[float]], k: int
) -> list[str]:
    """Return at most ``k`` record IDs, most similar first, ties by ID ascending.

    IDs compare by sequence number, so DEC-9999 comes before DEC-10000.
    """
    if k < 1:
        raise ValueError(f"k must be at least 1, got {k}")
    scored = [
        (cosine(query_vector, vector), record_id) for record_id, vector in vectors_by_id.items()
    ]
    scored.sort(key=lambda item: (-item[0], _id_order(item[1])))
    return [record_id for _, record_id in scored[:k]]
