"""Validators for records, Registrar drafts, Comparator results and Ledger entries (ADR-0011).

Validators never raise for invalid data: they return a ``ValidationResult`` whose error
messages start with the JSON path of the problem. They raise only for programming errors,
such as a missing schema file.
"""

import functools
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from knowledge_automata.core.evidence import QuoteCheck, check_evidence
from knowledge_automata.core.ledger import CHECK_OUTCOMES, STORED_COPY_STATUSES, TRANSITIONS
from knowledge_automata.core.registers import RegisterSpec
from knowledge_automata.core.schemas import (
    LEDGER_ENTRY_SCHEMA,
    LLM_EVENT_SCHEMA,
    RECONCILIATION_SCHEMA,
    RECORD_SCHEMA,
    draft_schema,
    load_schema,
    major_version,
    schema_version,
)

# RFC 3339 shape; datetime.fromisoformat alone also accepts forms such as
# "2026-10-25 11:43" or "20261025T1143".
_RFC3339_DATE_TIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$", re.ASCII
)

FORMAT_CHECKER = FormatChecker()


@FORMAT_CHECKER.checks("date-time")
def is_date_time(instance: object) -> bool:
    """RFC 3339 date-time with a timezone; replaces jsonschema's optional checker."""
    if not isinstance(instance, str):
        return True
    if not _RFC3339_DATE_TIME.match(instance):
        return False
    try:
        value = datetime.fromisoformat(instance.upper().replace("Z", "+00:00"))
    except ValueError:
        return False
    return value.tzinfo is not None


@dataclass(frozen=True)
class ValidationResult:
    """``ok`` is true when there are no errors. Drafts also report each quote check."""

    errors: tuple[str, ...] = ()
    evidence: tuple[QuoteCheck, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors


@functools.cache
def _schema_validator(relative_path: str) -> Draft202012Validator:
    return Draft202012Validator(load_schema(relative_path), format_checker=FORMAT_CHECKER)


@functools.cache
def _draft_validator(spec: RegisterSpec) -> Draft202012Validator:
    return Draft202012Validator(draft_schema(spec), format_checker=FORMAT_CHECKER)


def _schema_errors(validator: Draft202012Validator, instance: Any, path: str = "$") -> list[str]:
    errors = sorted(validator.iter_errors(instance), key=lambda error: error.json_path)
    return [f"{path}{error.json_path[1:]}: {error.message}" for error in errors]


def _semantic_errors(spec: RegisterSpec, content: Mapping[str, Any]) -> list[str]:
    return [f"$.content: {message}" for check in spec.semantic_checks for message in check(content)]


def _content_errors(spec: RegisterSpec, content: Any) -> list[str]:
    errors = _schema_errors(_schema_validator(spec.content_schema), content, "$.content")
    if errors:
        return errors
    return _semantic_errors(spec, content)


def _id_errors(path: str, record_id: Any, spec: RegisterSpec) -> list[str]:
    if isinstance(record_id, str) and not record_id.startswith(f"{spec.id_prefix}-"):
        return [f"{path}: {record_id!r} does not start with {spec.id_prefix + '-'!r}"]
    return []


def _history_errors(record: Mapping[str, Any]) -> list[str]:
    history = record.get("history")
    if not isinstance(history, list) or not all(isinstance(entry, dict) for entry in history):
        return []
    errors = []
    revisions = [entry.get("revision") for entry in history]
    if revisions != list(range(1, len(history) + 1)):
        errors.append(f"$.history: revisions must increase by one from 1, got {revisions}")
    if history and record.get("revision") != revisions[-1]:
        errors.append(
            f"$.revision: {record.get('revision')!r} does not match the last history "
            f"revision {revisions[-1]!r}"
        )
    return errors


def _self_reference_errors(record: Mapping[str, Any]) -> list[str]:
    record_id = record.get("id")
    relations = record.get("relations")
    errors = []
    if isinstance(relations, dict):
        supersedes = relations.get("supersedes")
        if isinstance(supersedes, list) and record_id in supersedes:
            errors.append("$.relations.supersedes: a record cannot supersede itself")
        if relations.get("superseded_by") == record_id:
            errors.append("$.relations.superseded_by: a record cannot be superseded by itself")
    history = record.get("history")
    if isinstance(history, list):
        for index, entry in enumerate(history):
            if isinstance(entry, dict) and entry.get("related_id") == record_id:
                errors.append(f"$.history[{index}].related_id: points at the record itself")
    return errors


def validate_record(record: Any, spec: RegisterSpec) -> ValidationResult:
    """Validate a stored record: envelope, register, schema version, content and history."""
    errors = _schema_errors(_schema_validator(RECORD_SCHEMA), record)
    if not isinstance(record, dict):
        return ValidationResult(tuple(errors))

    register = record.get("register")
    if isinstance(register, str) and register != spec.name:
        errors.append(f"$.register: {register!r} does not match register {spec.name!r}")
    errors.extend(_id_errors("$.id", record.get("id"), spec))

    version = record.get("schema_version")
    expected = schema_version(spec)
    if isinstance(version, str) and re.fullmatch(r"[0-9]+\.[0-9]+", version):
        if major_version(version) != major_version(expected):
            errors.append(
                f"$.schema_version: major version of {version!r} does not match the "
                f"content schema version {expected!r}"
            )

    if "content" in record:
        errors.extend(_content_errors(spec, record["content"]))
    errors.extend(_history_errors(record))
    errors.extend(_self_reference_errors(record))
    return ValidationResult(tuple(errors))


def _evidence_errors(
    quotes: Iterable[tuple[int, str]], artifact_text: str
) -> tuple[list[str], tuple[QuoteCheck, ...]]:
    indexed = list(quotes)
    checks = tuple(check_evidence([quote for _, quote in indexed], artifact_text))
    errors = [
        f"$.evidence[{index}]: {check.reason}: {check.quote!r}"
        for (index, _), check in zip(indexed, checks, strict=True)
        if not check.passed
    ]
    return errors, checks


def validate_draft(draft: Any, spec: RegisterSpec, artifact_text: str) -> ValidationResult:
    """Validate a Registrar draft: schema, semantic checks and evidence quotes.

    One failed quote rejects the draft; the result names every failed quote.
    """
    errors = _schema_errors(_draft_validator(spec), draft)
    if not isinstance(draft, dict):
        return ValidationResult(tuple(errors))

    content_is_valid = not any(error.startswith("$.content") for error in errors)
    if content_is_valid and "content" in draft:
        errors.extend(_semantic_errors(spec, draft["content"]))

    checks: tuple[QuoteCheck, ...] = ()
    evidence = draft.get("evidence")
    if isinstance(evidence, list):
        quotes = [(index, quote) for index, quote in enumerate(evidence) if isinstance(quote, str)]
        evidence_errors, checks = _evidence_errors(quotes, artifact_text)
        errors.extend(evidence_errors)
    return ValidationResult(tuple(errors), checks)


def validate_reconciliation(
    result: Any, spec: RegisterSpec, candidates: Mapping[str, Mapping[str, Any]]
) -> ValidationResult:
    """Validate a Comparator result against the candidates it was shown.

    ``candidates`` maps each candidate record ID to its current record.
    """
    errors = _schema_errors(_schema_validator(RECONCILIATION_SCHEMA), result)
    if errors:
        return ValidationResult(tuple(errors))

    classification = result["classification"]
    target_id = result.get("target_id")
    if classification not in spec.allowed_classifications:
        errors.append(
            f"$.classification: {classification!r} is not allowed in register {spec.name!r}"
        )

    if classification == "new":
        if target_id is not None:
            errors.append("$.target_id: must be omitted when classification is 'new'")
        return ValidationResult(tuple(errors))

    if target_id is None:
        errors.append(f"$.target_id: required when classification is {classification!r}")
        return ValidationResult(tuple(errors))
    errors.extend(_id_errors("$.target_id", target_id, spec))
    if target_id not in candidates:
        errors.append(f"$.target_id: {target_id!r} was not one of the candidates")
    else:
        status = candidates[target_id].get("record_status")
        if status != "active":
            errors.append(
                f"$.target_id: {target_id!r} has record_status {status!r}; "
                f"only active records can be the target of {classification!r}"
            )
    return ValidationResult(tuple(errors))


def validate_llm_event(event: Any) -> ValidationResult:
    """Validate one LLM event log line against ``core/llm-event.v1.json`` (ADR-0012)."""
    return ValidationResult(tuple(_schema_errors(_schema_validator(LLM_EVENT_SCHEMA), event)))


def _ledger_history_errors(history: list[dict[str, Any]]) -> list[str]:
    errors = []
    previous: str | None = None
    for index, step in enumerate(history):
        path = f"$.history[{index}]"
        status, by = step["status"], step["by"]
        owners = TRANSITIONS.get((previous, status))
        if owners is None:
            errors.append(f"{path}.status: cannot change from {previous!r} to {status!r}")
        elif by not in owners:
            errors.append(f"{path}.by: {by!r} cannot change from {previous!r} to {status!r}")
        if index and step["at"] < history[index - 1]["at"]:
            errors.append(f"{path}.at: earlier than the previous history entry")

        decided_by_check = by == "sensor" and status in ("rejected", "quarantined")
        check = step.get("check")
        if decided_by_check and check is None:
            errors.append(f"{path}: a Sensor {status!r} entry needs the check that decided it")
        elif check is not None and not decided_by_check:
            errors.append(
                f"{path}.check: only Sensor 'rejected' and 'quarantined' entries have one"
            )
        elif check is not None and CHECK_OUTCOMES[check] != status:
            errors.append(
                f"{path}.check: {check!r} leads to {CHECK_OUTCOMES[check]!r}, not {status!r}"
            )
        if by == "operator" and "reason" not in step:
            errors.append(f"{path}: an Operator entry needs a reason")

        ran = status in ("processed", "failed")
        if ran and "run_id" not in step:
            errors.append(f"{path}: a {status!r} entry needs a run_id")
        elif not ran and "run_id" in step:
            errors.append(f"{path}.run_id: only 'processed' and 'failed' entries have one")
        if status == "failed" and "error_type" not in step:
            errors.append(f"{path}: a 'failed' entry needs an error_type")
        elif status != "failed" and "error_type" in step:
            errors.append(f"{path}.error_type: only 'failed' entries have one")
        previous = status
    return errors


def _sequence(artifact_id: str) -> int:
    return int(artifact_id.split("-", 1)[1])


def validate_ledger_entry(entry: Any) -> ValidationResult:
    """Validate a stored Artifact Ledger entry: schema, history path and status rules (ADR-0015).

    The history must be a valid path through the transition table, starting with
    ``received`` by ``sensor``, and the entry's fields must agree with its last status.
    """
    errors = _schema_errors(_schema_validator(LEDGER_ENTRY_SCHEMA), entry)
    if errors:
        return ValidationResult(tuple(errors))

    history = entry["history"]
    status = entry["status"]
    errors.extend(_ledger_history_errors(history))
    if status != history[-1]["status"]:
        errors.append(f"$.status: {status!r} does not match the last history entry")
    if entry["updated_at"] != history[-1]["at"]:
        errors.append("$.updated_at: does not match the last history entry's time")
    if entry["created_at"] != history[0]["at"]:
        errors.append("$.created_at: does not match the first history entry's time")
    if status == "received":
        errors.append("$.status: an entry is stored only after the Sensor's checks")

    has_copy = status in STORED_COPY_STATUSES
    if has_copy and "stored_path" not in entry:
        errors.append(f"$: a {status!r} entry needs a stored_path")
    elif not has_copy and "stored_path" in entry:
        errors.append(f"$.stored_path: a {status!r} entry has no stored copy")

    unsupported = any(step.get("check") == "unsupported-format" for step in history)
    if unsupported and "media_type" in entry:
        errors.append("$.media_type: must be absent when the format is unsupported")
    elif not unsupported and "media_type" not in entry:
        errors.append("$: media_type is required unless the format is unsupported")

    if status != "processed":
        for field in ("produced", "rejected"):
            if entry[field]:
                errors.append(f"$.{field}: must be empty unless the status is 'processed'")

    same_name_as = entry.get("same_name_as")
    if same_name_as is not None:
        sequences = [_sequence(artifact_id) for artifact_id in same_name_as]
        if sequences != sorted(sequences):
            errors.append("$.same_name_as: IDs must be in ascending order")
        if max(sequences) >= _sequence(entry["id"]):
            errors.append("$.same_name_as: may list only earlier entries")
    return ValidationResult(tuple(errors))
