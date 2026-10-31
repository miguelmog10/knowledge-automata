"""The stand-in for the Governor (orchestrator): intake, recording, release and views.

The Sensor (intake and input guardrail) decides; this module reads and writes the files:
artifact copies, Artifact Ledger entries, records and views. ``record_decision`` runs steps
4 and 5 of the data flow for one artifact the Ledger allows: the Decision Registrar drafts,
the Comparator (reconciliation) classifies the draft against the active decisions, and code
applies the write rule (ADR-0017).

Write order when recording: the new record, then the record it supersedes or revises, then
views, then the Ledger. An interruption leaves the Ledger behind the records, never ahead,
and the next run detects it; so does a supersession that stopped halfway.
"""

import dataclasses
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from knowledge_automata.agents import sensor
from knowledge_automata.agents.comparator import (
    Comparator,
    ComparatorSettings,
    ComparisonOutcome,
    compare,
)
from knowledge_automata.agents.registrar import (
    ArtifactRefusedError,
    DraftOutcome,
    Registrar,
    draft_record,
)
from knowledge_automata.core import ledger
from knowledge_automata.core.prompts import load_prompt
from knowledge_automata.core.records import new_record
from knowledge_automata.core.validation import revision_errors, validate_record
from knowledge_automata.core.write_rules import (
    apply_reaffirmation,
    apply_supersession,
    apply_update,
    check_supersession_links,
)
from knowledge_automata.domains.project_management.decision_log_view import (
    INDEX,
    OWNED,
    render_decision_log,
)
from knowledge_automata.domains.project_management.registers import DECISION_LOG
from knowledge_automata.llm import LanguageModel, LLMConfigError, LLMError, LLMSettings
from knowledge_automata.llm.settings import Thinking
from knowledge_automata.storage import artifact_files
from knowledge_automata.storage.ledger_store import ARTIFACT_ID, LedgerStore
from knowledge_automata.storage.record_store import RecordStore, RecordStoreError
from knowledge_automata.views.markdown import (
    VIEWS_FOLDER,
    ViewDifferences,
    check_views,
    write_views,
)

DEFAULT_MEMORY = Path("runtime/memory")
RECORDABLE_STATUSES = frozenset({"accepted", "failed", "processed"})
RERUN_REASON = "Rerun: the earlier run recorded nothing"

# Thinking cost about 6x the billed output tokens for the same validation result in the
# handoff 003 smoke check; revisited with the sample project's evaluation set (ADR-0014).
DECISION_REGISTRAR_THINKING: Thinking = "disabled"


class InputError(Exception):
    """Input the user must fix: bad arguments, an unreadable file, or an artifact the
    Ledger does not allow to be recorded."""


def decision_registrar() -> Registrar:
    return Registrar(
        agent="decision-registrar",
        spec=DECISION_LOG,
        prompt=load_prompt("project-management/decision-registrar.v1"),
        retry_prompt=load_prompt("core/registrar-retry.v1"),
    )


def decision_comparator() -> Comparator:
    return Comparator(
        agent="comparator",
        spec=DECISION_LOG,
        prompt=load_prompt("project-management/decision-comparator.v1"),
        retry_prompt=load_prompt("core/comparator-retry.v1"),
    )


def decision_registrar_settings(settings: LLMSettings) -> LLMSettings:
    """Apply the thinking default unless ``KA_CHAT_THINKING`` is set.

    One model client serves the Decision Registrar and the Comparator, so this is the
    single place that sets the default for both.
    """
    if settings.chat_thinking is None:
        return dataclasses.replace(settings, chat_thinking=DECISION_REGISTRAR_THINKING)
    return settings


@dataclass(frozen=True)
class IngestOutcome:
    status: str  # accepted, quarantined, rejected or duplicate
    entry: dict[str, Any]  # the new entry, or the existing one for a duplicate

    @property
    def duplicate(self) -> bool:
        return self.status == "duplicate"


def ingest_file(
    *, path: Path, memory: Path, artifact_date: str | None, max_bytes: int, now: datetime
) -> IngestOutcome:
    """Run the Sensor on one file and store its Ledger entry, and its copy when kept.

    An exact duplicate of an entry that is not ``rejected`` writes nothing. Bad arguments
    and an unreadable file raise before anything is written. The copy is written before the
    entry, so an entry never points at a missing file.
    """
    sensor.check_artifact_date(artifact_date)
    sensor.check_source_name(path.name)
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise InputError(f"Cannot read {path}: {error.strerror or error}") from None

    store = LedgerStore(memory)
    existing = store.find_by_hash(sensor.content_hash(raw))
    if existing is not None:
        return IngestOutcome("duplicate", existing)

    entry = sensor.assess(
        raw=raw,
        name=path.name,
        artifact_id=store.next_id(),
        artifact_date=artifact_date,
        same_name_as=store.ids_with_name(path.name),
        max_bytes=max_bytes,
        now=now,
    )
    if "stored_path" in entry:
        artifact_files.write_copy(memory, entry["stored_path"], raw)
    store.save_new(entry)
    return IngestOutcome(entry["status"], entry)


def release_artifact(
    *, artifact_id: str, memory: Path, reason: str, now: datetime
) -> sensor.ReleaseOutcome:
    """The Operator's release of a quarantined artifact (the Sensor decides; this stores it).

    Raises ``SensorInputError`` for a missing reason or an entry that is not quarantined,
    and ``LedgerEntryNotFoundError`` for an unknown ID, before the copy is read.
    """
    sensor.check_reason(reason)
    store = LedgerStore(memory)
    entry = store.load(artifact_id)
    sensor.check_releasable(entry)
    raw = artifact_files.read_copy(memory, entry["stored_path"])
    outcome = sensor.release(entry, raw, reason=reason, now=now)
    if outcome.released:
        store.save_transition(entry, outcome.entry)
    return outcome


def artifact_links(memory: Path) -> dict[str, str]:
    """Map artifact IDs to their stored copies (relative to the memory folder) via the Ledger."""
    return {
        entry["id"]: entry["stored_path"]
        for entry in LedgerStore(memory).load_all()
        if "stored_path" in entry
    }


def render_views(memory: Path) -> dict[str, str]:
    records = RecordStore(memory).load_all(DECISION_LOG)
    return render_decision_log(records, artifact_links(memory))


def write_decision_log_views(memory: Path) -> ViewDifferences:
    """Regenerate the decision log views from the stored records."""
    return write_views(memory / VIEWS_FOLDER, render_views(memory), OWNED)


def check_decision_log_views(memory: Path) -> ViewDifferences:
    """Compare the committed decision log views with the generator's output."""
    return check_views(memory / VIEWS_FOLDER, render_views(memory), OWNED)


def supersession_link_problems(memory: Path) -> list[str]:
    """Messages for supersession links in the decision log that do not point back."""
    return check_supersession_links(RecordStore(memory).load_all(DECISION_LOG))


@dataclass(frozen=True)
class RecordOutcome:
    """What ``record_decision`` did. ``record_id`` is the record created or revised (for a
    supersession, the new record); ``related_id`` the record it superseded."""

    run_id: str
    draft: DraftOutcome  # attempts, usage, model, prompt version, and errors when rejected
    entry: dict[str, Any]  # the Ledger entry after the processed transition
    rerun: bool = False  # the entry was processed before and had recorded nothing
    active_records: int = 0  # active decisions when the Comparator ran
    comparison: ComparisonOutcome | None = None  # None when the draft was rejected
    change: str | None = None  # new, update, reaffirmation or supersession
    record_id: str | None = None
    related_id: str | None = None
    revision: int | None = None  # of record_id after the change
    sources_added: int = 0
    filled: tuple[str, ...] = ()  # update: empty fields filled from the draft
    ignored: tuple[str, ...] = ()  # update: fields kept although the draft's value differs
    record_path: Path | None = None
    index_path: Path | None = None

    @property
    def accepted(self) -> bool:
        return self.record_id is not None

    @property
    def rejected_stage(self) -> str | None:
        """``draft`` or ``comparison`` when nothing was recorded, else None."""
        if self.accepted:
            return None
        return "draft" if not self.draft.accepted else "comparison"

    @property
    def record_ids(self) -> tuple[str, ...]:
        """Every record written, the new or revised one first."""
        return tuple(item for item in (self.record_id, self.related_id) if item)


def recordable_entry(artifact_id: str, memory: Path) -> dict[str, Any]:
    """Return the artifact's Ledger entry if it may be recorded, or raise ``InputError``.

    ``accepted`` and ``failed`` artifacts may be recorded, and ``processed`` ones that
    recorded nothing (a rerun). The decision log's supersession links must be whole. Reads
    only, so the CLI can call it before building the LLM. Raises ``LedgerEntryNotFoundError``
    for an unknown ID.
    """
    if not ARTIFACT_ID.fullmatch(artifact_id):
        raise InputError(f"The artifact ID must look like ART-0001, got {artifact_id!r}")
    entry = LedgerStore(memory).load(artifact_id)
    status = entry["status"]
    nothing_sent = "nothing was sent to the model"
    if status == "quarantined":
        raise InputError(
            f"{artifact_id} is quarantined ({_last_check(entry)}); {nothing_sent}. Release it "
            f"with `knowledge-automata release {artifact_id} --reason TEXT`, or fix the file "
            "and ingest it again."
        )
    if status == "rejected":
        raise InputError(
            f"{artifact_id} was rejected by the Sensor ({_last_check(entry)}); {nothing_sent}. "
            "Fix the file and ingest it again."
        )
    if status not in RECORDABLE_STATUSES or (status == "processed" and entry["produced"]):
        raise InputError(f"{artifact_id} is already {status} ({_results(entry)}); {nothing_sent}.")

    problems = supersession_link_problems(memory)
    if problems:
        raise InputError(
            "The decision log has a supersession link that does not point back; "
            f"{nothing_sent}.\n" + "\n".join(f"- {problem}" for problem in problems)
        )

    cited = RecordStore(memory).ids_citing(DECISION_LOG, artifact_id)
    if cited:
        raise InputError(
            f"{artifact_id} is {status} in the Ledger but already recorded in "
            f"{', '.join(cited)}: the Ledger is behind the records, for example after an "
            f"interrupted run. {nothing_sent.capitalize()}; correct the Ledger entry by hand."
        )
    return entry


def _last_check(entry: dict[str, Any]) -> str:
    return entry["history"][-1].get("check", "no check recorded")


def _results(entry: dict[str, Any]) -> str:
    produced = [item["record_id"] for item in entry["produced"]]
    if produced:
        return f"recorded in {', '.join(produced)}"
    if entry["rejected"]:
        return "its draft was rejected"
    return "nothing was recorded"


def read_artifact_text(memory: Path, entry: dict[str, Any]) -> str:
    """The stored copy as text: UTF-8 without a BOM, line endings as LF.

    Evidence quotes are checked against this text. A copy whose hash no longer matches the
    Ledger is refused, because copies are read-only.
    """
    raw = artifact_files.read_copy(memory, entry["stored_path"])
    where = f"The stored copy of {entry['id']} ({entry['stored_path']})"
    if sensor.content_hash(raw) != entry["content_hash"]:
        raise InputError(
            f"{where} no longer matches its hash in the Ledger; nothing was sent to the model. "
            "Artifact copies are read-only: restore the file or ingest the new version."
        )
    text = sensor.decode(raw)
    if text is None:
        raise InputError(f"{where} is not valid UTF-8; nothing was sent to the model.")
    return sensor.normalize_newlines(text)


def record_decision(
    *,
    artifact_id: str,
    memory: Path,
    llm: LanguageModel,
    now: datetime,
    comparator_settings: ComparatorSettings,
) -> RecordOutcome:
    """Draft, compare and store one decision from one Ledger artifact (handoff 006, 3.1).

    On an accepted classification: the write rule's records, the views, then the
    ``processed`` transition listing the record and the change. On a rejected draft or
    comparison: ``processed`` listing it with its stage, and nothing in the register. On a
    provider error other than ``LLMConfigError``, at any stage: the ``failed`` transition,
    then the error is raised again. Raises ``InputError`` before any call when the Ledger or
    the register does not allow the artifact to be recorded. ``OSError`` propagates.
    """
    run_id = getattr(llm, "run_id", None)
    if not run_id:
        raise ValueError("record_decision needs an LLM with a run_id, such as ObservedLLM")
    entry = recordable_entry(artifact_id, memory)
    text = read_artifact_text(memory, entry)
    rerun = entry["status"] == "processed"
    reason = RERUN_REASON if rerun else None
    artifact_date = entry.get("artifact_date")
    ledger_store = LedgerStore(memory)
    store = RecordStore(memory)
    active: list[dict[str, Any]] = []
    comparison: ComparisonOutcome | None = None

    try:
        draft = draft_record(decision_registrar(), llm, text, artifact_id=artifact_id)
        if draft.accepted:
            active = store.load_active(DECISION_LOG)
            comparison = compare(
                decision_comparator(),
                llm,
                draft=draft.draft,
                active_records=active,
                artifact_id=artifact_id,
                artifact_date=artifact_date,
                settings=comparator_settings,
            )
    except ArtifactRefusedError as error:
        raise InputError(f"{artifact_id} was refused: {error}") from None
    except LLMConfigError:
        raise
    except LLMError as error:
        failed = ledger.transition(
            entry,
            to="failed",
            by="pipeline",
            at=now,
            reason=reason,
            run_id=run_id,
            error_type=type(error).__name__,
        )
        ledger_store.save_transition(entry, failed)
        raise

    processed = ledger.transition(
        entry, to="processed", by="pipeline", at=now, reason=reason, run_id=run_id
    )
    outcome = RecordOutcome(
        run_id=run_id,
        draft=draft,
        entry=processed,
        rerun=rerun,
        active_records=len(active),
        comparison=comparison,
    )
    if comparison is None or not comparison.accepted:
        rejected = _rejected_item(draft, comparison, run_id)
        processed = ledger.with_results(
            processed, produced=[], rejected=[*entry["rejected"], rejected]
        )
        ledger_store.save_transition(entry, processed)
        return dataclasses.replace(outcome, entry=processed)

    written = _apply_write_rule(
        store,
        draft,
        comparison,
        {record["id"]: record for record in active},
        artifact_id=artifact_id,
        artifact_date=artifact_date,
        now=now,
    )
    write_decision_log_views(memory)
    processed = ledger.with_results(
        processed,
        produced=[_produced_item(draft, comparison, written)],
        rejected=entry["rejected"],
    )
    ledger_store.save_transition(entry, processed)
    return dataclasses.replace(
        outcome,
        entry=processed,
        change=written.change,
        record_id=written.record_id,
        related_id=written.related_id,
        revision=written.revision,
        sources_added=written.sources_added,
        filled=written.filled,
        ignored=written.ignored,
        record_path=written.path,
        index_path=memory / VIEWS_FOLDER / INDEX,
    )


def _rejected_item(
    draft: DraftOutcome, comparison: ComparisonOutcome | None, run_id: str
) -> dict[str, Any]:
    """The Ledger's ``rejected`` item: error paths only, never the messages (model text)."""
    stage, failed = ("draft", draft) if comparison is None else ("comparison", comparison)
    item: dict[str, Any] = {
        "register": DECISION_LOG.name,
        "stage": stage,
        "run_id": run_id,
        "attempts": failed.attempts,
        "prompt_version": failed.prompt_version,
        "error_paths": ledger.error_paths(failed.errors),
    }
    if failed.error_type is not None:
        item["error_type"] = failed.error_type
    return item


@dataclass(frozen=True)
class _Written:
    change: str
    record_id: str  # created or revised; for a supersession, the new record
    related_id: str | None  # the superseded record
    revision: int
    schema_version: str
    sources_added: int
    filled: tuple[str, ...]
    ignored: tuple[str, ...]
    path: Path


def _apply_write_rule(
    store: RecordStore,
    draft: DraftOutcome,
    comparison: ComparisonOutcome,
    active: dict[str, dict[str, Any]],
    *,
    artifact_id: str,
    artifact_date: str | None,
    now: datetime,
) -> _Written:
    """Write the records for the classification.

    A supersession writes the new record first, then marks the old one (handoff 006, 3.5).
    """
    change = comparison.classification
    provenance = {
        "artifact_id": artifact_id,
        "artifact_date": artifact_date,
        "model": draft.model,
        "prompt_version": draft.prompt_version,
        "now": now,
    }
    quotes = draft.draft["evidence"]
    filled: list[str] = []
    ignored: list[str] = []
    related_id = None
    if change == "new":
        record = new_record(
            spec=DECISION_LOG,
            record_id=store.next_id(DECISION_LOG),
            content=draft.draft["content"],
            quotes=quotes,
            **provenance,
        )
        path = store.save_new(record, DECISION_LOG)
    elif change == "supersession":
        target = active[comparison.target_id]
        record, superseded = apply_supersession(
            DECISION_LOG, target, store.next_id(DECISION_LOG), draft.draft, **provenance
        )
        # Check the old record's revision before writing the new one, so a refusal by
        # save_revision cannot leave a half-done supersession behind.
        errors = [
            *validate_record(superseded, DECISION_LOG).errors,
            *revision_errors(target, superseded),
        ]
        if errors:
            raise RecordStoreError(
                f"{target['id']} cannot be marked superseded, so nothing was written:\n"
                + "\n".join(f"- {error}" for error in errors)
            )
        path = store.save_new(record, DECISION_LOG)
        store.save_revision(target, superseded, DECISION_LOG)
        related_id = target["id"]
    else:
        target = active[comparison.target_id]
        if change == "update":
            record, filled, ignored = apply_update(DECISION_LOG, target, draft.draft, **provenance)
        else:
            record = apply_reaffirmation(DECISION_LOG, target, quotes, **provenance)
        path = store.save_revision(target, record, DECISION_LOG)
    return _Written(
        change=change,
        record_id=record["id"],
        related_id=related_id,
        revision=record["revision"],
        schema_version=record["schema_version"],
        sources_added=len(quotes),
        filled=tuple(filled),
        ignored=tuple(ignored),
        path=path,
    )


def _produced_item(
    draft: DraftOutcome, comparison: ComparisonOutcome, written: _Written
) -> dict[str, Any]:
    """The Ledger's ``produced`` item (handoff 006, 5.3); no ``comparison`` without one."""
    item: dict[str, Any] = {
        "register": DECISION_LOG.name,
        "record_id": written.record_id,
        "change": written.change,
        "model": draft.model,
        "prompt_version": draft.prompt_version,
        "schema_version": written.schema_version,
    }
    if written.related_id is not None:
        item["related_id"] = written.related_id
    if comparison.compared:
        item["comparison"] = {
            "model": comparison.model,
            "prompt_version": comparison.prompt_version,
            "attempts": comparison.attempts,
            "candidates": [
                {"record_id": candidate.record_id, "score": candidate.score}
                for candidate in comparison.candidates
            ],
        }
    return item
