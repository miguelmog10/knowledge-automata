"""The stand-in for the Governor (orchestrator): intake, recording, release and views.

The Sensor (intake and input guardrail) decides; this module reads and writes the files:
artifact copies, Artifact Ledger entries, records and views. ``record_decision`` runs step
4 of the data flow (the Decision Registrar) for one artifact the Ledger has accepted. There
is no Comparator (reconciliation) yet, so every record is ``new``.

Write order when recording: record, then views, then the Ledger. An interruption leaves the
Ledger behind the records, never ahead, and the next run detects it.
"""

import dataclasses
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from knowledge_automata.agents import sensor
from knowledge_automata.agents.registrar import (
    ArtifactRefusedError,
    DraftOutcome,
    Registrar,
    draft_record,
)
from knowledge_automata.core import ledger
from knowledge_automata.core.prompts import load_prompt
from knowledge_automata.core.records import new_record
from knowledge_automata.domains.project_management.decision_log_view import (
    INDEX,
    OWNED,
    render_decision_log,
)
from knowledge_automata.domains.project_management.registers import DECISION_LOG
from knowledge_automata.llm import ChatModel, LLMConfigError, LLMError, LLMSettings
from knowledge_automata.llm.settings import Thinking
from knowledge_automata.storage import artifact_files
from knowledge_automata.storage.ledger_store import ARTIFACT_ID, LedgerStore
from knowledge_automata.storage.record_store import RecordStore
from knowledge_automata.views.markdown import (
    VIEWS_FOLDER,
    ViewDifferences,
    check_views,
    write_views,
)

DEFAULT_MEMORY = Path("runtime/memory")
RECORDABLE_STATUSES = frozenset({"accepted", "failed"})

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


def decision_registrar_settings(settings: LLMSettings) -> LLMSettings:
    """Apply the Decision Registrar's thinking default unless ``KA_CHAT_THINKING`` is set."""
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


@dataclass(frozen=True)
class RecordOutcome:
    run_id: str
    draft: DraftOutcome  # attempts, usage, model, prompt version, and errors when rejected
    entry: dict[str, Any]  # the Ledger entry after the processed transition
    record_id: str | None = None
    record_path: Path | None = None
    index_path: Path | None = None

    @property
    def accepted(self) -> bool:
        return self.record_id is not None


def recordable_entry(artifact_id: str, memory: Path) -> dict[str, Any]:
    """Return the artifact's Ledger entry if it may be recorded, or raise ``InputError``.

    Only ``accepted`` and ``failed`` artifacts may be recorded. Reads only, so the CLI can
    call it before building the LLM. Raises ``LedgerEntryNotFoundError`` for an unknown ID.
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
    if status not in RECORDABLE_STATUSES:
        raise InputError(f"{artifact_id} is already {status} ({_results(entry)}); {nothing_sent}.")

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
    *, artifact_id: str, memory: Path, llm: ChatModel, now: datetime
) -> RecordOutcome:
    """Draft, validate and store one decision record from one Ledger artifact.

    On an accepted draft: the record, the views, then the ``processed`` transition listing
    the record. On a rejected draft: ``processed`` listing the rejected draft, and nothing
    in the register. On a provider error other than ``LLMConfigError``: the ``failed``
    transition, then the error is raised again. Raises ``InputError`` before any call when
    the Ledger does not allow the artifact to be recorded. ``OSError`` propagates.
    """
    run_id = getattr(llm, "run_id", None)
    if not run_id:
        raise ValueError("record_decision needs an LLM with a run_id, such as ObservedLLM")
    entry = recordable_entry(artifact_id, memory)
    text = read_artifact_text(memory, entry)
    ledger_store = LedgerStore(memory)

    try:
        outcome = draft_record(decision_registrar(), llm, text, artifact_id=artifact_id)
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
            run_id=run_id,
            error_type=type(error).__name__,
        )
        ledger_store.save_transition(entry, failed)
        raise

    processed = ledger.transition(entry, to="processed", by="pipeline", at=now, run_id=run_id)
    if not outcome.accepted:
        rejected: dict[str, Any] = {
            "register": DECISION_LOG.name,
            "attempts": outcome.attempts,
            "prompt_version": outcome.prompt_version,
            "error_paths": ledger.error_paths(outcome.errors),
        }
        if outcome.error_type is not None:
            rejected["error_type"] = outcome.error_type
        processed = ledger.with_results(processed, produced=[], rejected=[rejected])
        ledger_store.save_transition(entry, processed)
        return RecordOutcome(run_id=run_id, draft=outcome, entry=processed)

    store = RecordStore(memory)
    record_id = store.next_id(DECISION_LOG)
    record = new_record(
        spec=DECISION_LOG,
        record_id=record_id,
        content=outcome.draft["content"],
        quotes=outcome.draft["evidence"],
        artifact_id=artifact_id,
        artifact_date=entry.get("artifact_date"),
        model=outcome.model,
        prompt_version=outcome.prompt_version,
        now=now,
    )
    path = store.save_new(record, DECISION_LOG)
    write_decision_log_views(memory)
    produced = {
        "register": record["register"],
        "record_id": record_id,
        "model": outcome.model,
        "prompt_version": outcome.prompt_version,
        "schema_version": record["schema_version"],
    }
    processed = ledger.with_results(processed, produced=[produced], rejected=[])
    ledger_store.save_transition(entry, processed)
    return RecordOutcome(
        run_id=run_id,
        draft=outcome,
        entry=processed,
        record_id=record_id,
        record_path=path,
        index_path=memory / VIEWS_FOLDER / INDEX,
    )
