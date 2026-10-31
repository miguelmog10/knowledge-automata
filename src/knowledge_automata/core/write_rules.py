"""Applying a Comparator (reconciliation) classification to the decision log (ADR-0017).

Pure functions that return new records and never change their inputs, like
``core/ledger.py``. They never call a model and never write files: the pipeline writes
what they return through ``RecordStore``. The risk register's rules come with the Risk
Registrar; calling these functions for another register raises ``ValueError``.
"""

import copy
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any

from knowledge_automata.core.records import (
    format_timestamp,
    has_value,
    history_entry,
    new_record,
    new_sources,
    order_like_schema,
    order_record,
)
from knowledge_automata.core.registers import RegisterSpec
from knowledge_automata.core.schemas import load_schema

DECISION_LOG_NAME = "decision-log"


def _require_decision_log(spec: RegisterSpec, target: Mapping[str, Any]) -> None:
    if spec.name != DECISION_LOG_NAME or target["register"] != DECISION_LOG_NAME:
        raise ValueError(f"Write rules exist for the decision log only, not {target['register']!r}")


def _revise(
    target: Mapping[str, Any],
    quotes: Sequence[str],
    *,
    change: str,
    artifact_id: str,
    artifact_date: str | None,
    timestamp: str,
    fields: Sequence[str] | None = None,
    related_id: str | None = None,
    model: str | None = None,
    prompt_version: str | None = None,
) -> dict[str, Any]:
    """Return the next revision of ``target``: new sources and one history entry added."""
    record = copy.deepcopy(dict(target))
    record["revision"] = target["revision"] + 1
    record["updated_at"] = timestamp
    record["sources"] = record["sources"] + new_sources(
        quotes, artifact_id=artifact_id, artifact_date=artifact_date, timestamp=timestamp
    )
    record["history"] = record["history"] + [
        history_entry(
            revision=record["revision"],
            timestamp=timestamp,
            change=change,
            artifact_id=artifact_id,
            fields=fields,
            related_id=related_id,
            model=model,
            prompt_version=prompt_version,
        )
    ]
    return order_record(record)


def apply_update(
    spec: RegisterSpec,
    target: Mapping[str, Any],
    draft: Mapping[str, Any],
    *,
    artifact_id: str,
    artifact_date: str | None,
    model: str | None,
    prompt_version: str | None,
    now: datetime,
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Fill the target's empty fields from the draft and add the draft's quotes as sources.

    Returns ``(record, filled, ignored)``: ``filled`` lists the fields copied over, and
    ``ignored`` the fields present in both whose values differ (kept as they are: a change
    of substance is a supersession). Both follow the content schema's order. An empty
    string or list counts as absent on both sides, as in ``comparison_text``: an empty
    target field can be filled, and an empty draft field fills and reports nothing.
    """
    _require_decision_log(spec, target)
    schema = load_schema(spec.content_schema)
    existing, drafted = target["content"], draft["content"]
    offered = [key for key in schema["properties"] if has_value(drafted, key)]
    filled = [key for key in offered if not has_value(existing, key)]
    ignored = [key for key in offered if has_value(existing, key) and drafted[key] != existing[key]]
    record = _revise(
        target,
        draft["evidence"],
        change="update",
        artifact_id=artifact_id,
        artifact_date=artifact_date,
        timestamp=format_timestamp(now),
        fields=filled,
        model=model,
        prompt_version=prompt_version,
    )
    content = {**record["content"], **{key: copy.deepcopy(drafted[key]) for key in filled}}
    record["content"] = order_like_schema(content, schema)
    return record, filled, ignored


def apply_reaffirmation(
    spec: RegisterSpec,
    target: Mapping[str, Any],
    quotes: Sequence[str],
    *,
    artifact_id: str,
    artifact_date: str | None,
    model: str | None,
    prompt_version: str | None,
    now: datetime,
) -> dict[str, Any]:
    """Add the draft's quotes to the target as sources; the draft's content is ignored."""
    _require_decision_log(spec, target)
    return _revise(
        target,
        quotes,
        change="reaffirmation",
        artifact_id=artifact_id,
        artifact_date=artifact_date,
        timestamp=format_timestamp(now),
        model=model,
        prompt_version=prompt_version,
    )


def apply_supersession(
    spec: RegisterSpec,
    target: Mapping[str, Any],
    new_record_id: str,
    draft: Mapping[str, Any],
    *,
    artifact_id: str,
    artifact_date: str | None,
    model: str | None,
    prompt_version: str | None,
    now: datetime,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ``(new_record, superseded_target)``, linked both ways.

    The new record (revision 1) has ``relations.supersedes`` and a ``supersession`` history
    entry; the target goes to ``superseded`` with ``relations.superseded_by`` and a
    ``superseded`` history entry, which has no model: code made that change, not a draft.
    """
    _require_decision_log(spec, target)
    if target["record_status"] != "active":
        raise ValueError(f"{target['id']} is {target['record_status']!r}, not active")
    record = new_record(
        spec=spec,
        record_id=new_record_id,
        content=draft["content"],
        quotes=draft["evidence"],
        artifact_id=artifact_id,
        artifact_date=artifact_date,
        model=model,
        prompt_version=prompt_version,
        now=now,
        change="supersession",
        supersedes=target["id"],
    )
    superseded = _revise(
        target,
        [],
        change="superseded",
        artifact_id=artifact_id,
        artifact_date=artifact_date,
        timestamp=format_timestamp(now),
        related_id=new_record_id,
    )
    superseded["record_status"] = "superseded"
    superseded["relations"] = {**superseded.get("relations", {}), "superseded_by": new_record_id}
    return record, order_record(superseded)


def check_supersession_links(records: Iterable[Mapping[str, Any]]) -> list[str]:
    """Return a message for every inconsistent supersession link.

    A record that supersedes another needs the other to exist, be ``superseded`` and name
    it in ``superseded_by``; a ``superseded_by`` needs a record that supersedes it, and a
    record that has one cannot be ``active``. The usual cause is a run that stopped between
    writing the new record and marking the old one (handoff 006, 3.5), or a hand edit.
    """
    by_id = {record["id"]: record for record in records}
    messages = []
    for record_id, record in by_id.items():
        relations = record.get("relations", {})
        for old_id in relations.get("supersedes", []):
            old = by_id.get(old_id)
            if old is None:
                messages.append(f"{record_id} supersedes {old_id}, but {old_id} does not exist.")
                continue
            superseded_by = old.get("relations", {}).get("superseded_by")
            if old["record_status"] == "active" and superseded_by is None:
                messages.append(
                    f"{record_id} supersedes {old_id}, but {old_id} is still active: a "
                    f"supersession was interrupted. Finish it by marking {old_id} superseded "
                    f"by {record_id}, then run `knowledge-automata views`."
                )
            elif superseded_by != record_id:
                messages.append(
                    f"{record_id} supersedes {old_id}, but {old_id} is "
                    f"{old['record_status']} and names {superseded_by!r} as its replacement."
                )
        new_id = relations.get("superseded_by")
        if new_id is None:
            continue
        if record["record_status"] == "active":
            messages.append(
                f"{record_id} names {new_id} in relations.superseded_by but is still active: "
                f"set {record_id}'s record_status to superseded, then run "
                "`knowledge-automata views`."
            )
        new = by_id.get(new_id)
        if new is None:
            messages.append(f"{record_id} is superseded by {new_id}, but {new_id} does not exist.")
        elif record_id not in new.get("relations", {}).get("supersedes", []):
            messages.append(
                f"{record_id} is superseded by {new_id}, but {new_id} does not supersede "
                f"{record_id}."
            )
    return messages
