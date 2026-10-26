"""Building a new record's envelope: every field code owns (ADR-0011).

The Registrar drafts ``content`` and evidence quotes; this module adds the ID, register,
schema version, status, revision, timestamps, sources and history. It never calls a model
and never writes files.
"""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from knowledge_automata.core.registers import RegisterSpec
from knowledge_automata.core.schemas import RECORD_SCHEMA, load_schema, schema_version


def format_timestamp(moment: datetime) -> str:
    """Return ``moment`` in UTC as ``YYYY-MM-DDTHH:MM:SSZ``; naive datetimes are refused."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("Timestamps must be timezone-aware")
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def order_like_schema(values: Mapping[str, Any], schema: Mapping[str, Any]) -> dict[str, Any]:
    """Return ``values`` with keys in the schema's property order; unknown keys go last."""
    order = list(schema.get("properties", {}))
    known = [key for key in order if key in values]
    unknown = [key for key in values if key not in order]
    return {key: values[key] for key in known + unknown}


def _defs(name: str) -> dict[str, Any]:
    return load_schema(RECORD_SCHEMA)["$defs"][name]


def new_record(
    *,
    spec: RegisterSpec,
    record_id: str,
    content: Mapping[str, Any],
    quotes: Sequence[str],
    artifact_id: str,
    artifact_date: str | None,
    model: str | None,
    prompt_version: str | None,
    now: datetime,
) -> dict[str, Any]:
    """Build a ``revision: 1``, ``active`` record from a validated draft.

    One source per quote, in order. ``artifact_date`` is added to the sources only when
    given; ``model`` and ``prompt_version`` go into the history entry when given.
    """
    timestamp = format_timestamp(now)
    ordered_content = order_like_schema(content, load_schema(spec.content_schema))

    sources = []
    for quote in quotes:
        source = {"artifact_id": artifact_id}
        if artifact_date is not None:
            source["artifact_date"] = artifact_date
        source["excerpt"] = quote
        source["added_at"] = timestamp
        sources.append(order_like_schema(source, _defs("source")))

    entry: dict[str, Any] = {
        "revision": 1,
        "at": timestamp,
        "change": "new",
        "artifact_id": artifact_id,
        "fields": list(ordered_content),
    }
    if model is not None:
        entry["model"] = model
    if prompt_version is not None:
        entry["prompt_version"] = prompt_version

    record = {
        "id": record_id,
        "register": spec.name,
        "schema_version": schema_version(spec),
        "record_status": "active",
        "revision": 1,
        "created_at": timestamp,
        "updated_at": timestamp,
        "content": ordered_content,
        "sources": sources,
        "history": [order_like_schema(entry, _defs("history_entry"))],
    }
    return order_like_schema(record, load_schema(RECORD_SCHEMA))
