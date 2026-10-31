"""Artifact Ledger entries: building them and changing their status (ADR-0006, ADR-0015).

Pure functions, no file access. Every function returns a new entry and leaves its input
unchanged; history entries are only ever appended. ``LedgerStore`` validates an entry with
``validate_ledger_entry`` before writing it.
"""

import copy
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any

from knowledge_automata.core.records import format_timestamp, order_like_schema
from knowledge_automata.core.schemas import LEDGER_ENTRY_SCHEMA, load_schema

STATUSES = ("received", "accepted", "quarantined", "rejected", "processed", "failed")
# rejected is always final; processed is final once it lists a record (ADR-0015).
FINAL_STATUSES = frozenset({"rejected"})
STORED_COPY_STATUSES = frozenset({"accepted", "quarantined", "processed", "failed"})
ACTORS = ("sensor", "operator", "pipeline", "governor")
# Copies live in <memory>/artifacts/; stored_path is relative to the memory folder.
ARTIFACTS_FOLDER = "artifacts"

_PIPELINE = frozenset({"pipeline", "governor"})

# (from, to) -> who may make the change. "pipeline" stands in for the Governor until it exists.
TRANSITIONS: dict[tuple[str | None, str], frozenset[str]] = {
    (None, "received"): frozenset({"sensor"}),
    ("received", "accepted"): frozenset({"sensor"}),
    ("received", "quarantined"): frozenset({"sensor"}),
    ("received", "rejected"): frozenset({"sensor"}),
    ("quarantined", "accepted"): frozenset({"operator"}),
    ("accepted", "processed"): _PIPELINE,
    ("accepted", "failed"): _PIPELINE,
    ("failed", "processed"): _PIPELINE,
    ("failed", "failed"): _PIPELINE,
    # A rerun of an artifact whose earlier run recorded nothing (refused once it produced).
    ("processed", "processed"): _PIPELINE,
    ("processed", "failed"): _PIPELINE,
}

# Each Sensor check decides one outcome.
CHECK_OUTCOMES = {
    "unsupported-format": "rejected",
    "empty": "rejected",
    "encoding": "quarantined",
    "oversized": "quarantined",
    "delimiter": "quarantined",
}

SCHEMA_VERSION = load_schema(LEDGER_ENTRY_SCHEMA)["x-version"]


class LedgerError(Exception):
    """A status change that the transition rules do not allow."""


def _major(version: str) -> str:
    return version.split(".", 1)[0]


def _schema() -> dict[str, Any]:
    return load_schema(LEDGER_ENTRY_SCHEMA)


def _defs(name: str) -> dict[str, Any]:
    return _schema()["$defs"][name]


def _history_entry(
    *,
    at: str,
    status: str,
    by: str,
    check: str | None = None,
    reason: str | None = None,
    run_id: str | None = None,
    error_type: str | None = None,
) -> dict[str, Any]:
    optional = {"check": check, "reason": reason, "run_id": run_id, "error_type": error_type}
    entry = {"at": at, "status": status, "by": by}
    entry.update({key: value for key, value in optional.items() if value is not None})
    return order_like_schema(entry, _defs("history_entry"))


def new_entry(
    *,
    artifact_id: str,
    title: str,
    source_name: str,
    size_bytes: int,
    content_hash: str,
    at: datetime,
    artifact_date: str | None = None,
    media_type: str | None = None,
    stored_path: str | None = None,
    same_name_as: Sequence[str] = (),
    reason: str | None = None,
) -> dict[str, Any]:
    """Return a new entry with status ``received`` by ``sensor``.

    A ``received`` entry is never stored: the Sensor applies its outcome with
    ``transition`` first. Optional fields are left out when not given.
    """
    timestamp = format_timestamp(at)
    entry: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "id": artifact_id,
        "title": title,
        "source": {"type": "file", "name": source_name},
        "size_bytes": size_bytes,
        "content_hash": content_hash,
        "status": "received",
        "created_at": timestamp,
        "updated_at": timestamp,
        "produced": [],
        "rejected": [],
        "history": [_history_entry(at=timestamp, status="received", by="sensor", reason=reason)],
    }
    optional = {
        "artifact_date": artifact_date,
        "media_type": media_type,
        "stored_path": stored_path,
        "same_name_as": list(same_name_as) or None,
    }
    entry.update({key: value for key, value in optional.items() if value is not None})
    return order_like_schema(entry, _schema())


def transition(
    entry: Mapping[str, Any],
    *,
    to: str,
    by: str,
    at: datetime,
    reason: str | None = None,
    check: str | None = None,
    run_id: str | None = None,
    error_type: str | None = None,
) -> dict[str, Any]:
    """Return a copy of ``entry`` with one history entry appended and the status updated.

    The copy's ``schema_version`` is raised to the current minor version of the same major.
    Raises ``LedgerError`` for a change that is not in the transition table, the wrong
    owner, a rerun of a ``processed`` entry that already lists records, an entry of another
    major schema version, or a time earlier than the last history entry.
    """
    current = entry["status"]
    owners = TRANSITIONS.get((current, to))
    if owners is None:
        raise LedgerError(f"{entry['id']}: cannot change status from {current!r} to {to!r}")
    if by not in owners:
        raise LedgerError(
            f"{entry['id']}: {by!r} cannot change status from {current!r} to {to!r} "
            f"(allowed: {', '.join(sorted(owners))})"
        )
    if current == "processed" and entry["produced"]:
        raise LedgerError(
            f"{entry['id']}: cannot change status from 'processed' to {to!r}: it already "
            "lists records, and reprocessing an artifact that produced records is not "
            "supported"
        )
    if _major(entry["schema_version"]) != _major(SCHEMA_VERSION):
        raise LedgerError(
            f"{entry['id']}: schema version {entry['schema_version']!r} is not a "
            f"{_major(SCHEMA_VERSION)}.x version"
        )
    timestamp = format_timestamp(at)
    if timestamp < entry["history"][-1]["at"]:
        raise LedgerError(f"{entry['id']}: {timestamp} is earlier than the last history entry")

    updated = copy.deepcopy(dict(entry))
    updated["schema_version"] = SCHEMA_VERSION
    updated["history"].append(
        _history_entry(
            at=timestamp,
            status=to,
            by=by,
            check=check,
            reason=reason,
            run_id=run_id,
            error_type=error_type,
        )
    )
    updated["status"] = to
    updated["updated_at"] = timestamp
    return order_like_schema(updated, _schema())


def with_results(
    entry: Mapping[str, Any],
    produced: Iterable[Mapping[str, Any]],
    rejected: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return a copy of ``entry`` with ``produced`` and ``rejected`` set, keys in schema order.

    Used together with the ``processed`` transition. On a rerun the caller passes the
    earlier rejected drafts too, so they are never lost.
    """
    updated = copy.deepcopy(dict(entry))
    updated["produced"] = [
        order_like_schema(dict(item), _defs("produced_record")) for item in produced
    ]
    updated["rejected"] = [
        order_like_schema(dict(item), _defs("rejected_draft")) for item in rejected
    ]
    return updated


def error_paths(errors: Iterable[str]) -> list[str]:
    """Return the JSON path of each validation error, unique, in first-seen order.

    Validator messages start with a path (``$.evidence[1]: ...``); a message that does not,
    such as an unusable response, becomes ``$``.
    """
    paths: list[str] = []
    for error in errors:
        path = error.split(": ", 1)[0] if error.startswith("$") else "$"
        if path not in paths:
            paths.append(path)
    return paths
