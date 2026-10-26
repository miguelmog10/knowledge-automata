"""Recording one decision from one artifact: the stand-in for the Governor in this slice.

Handoff 004 runs step 4 of the data flow (the Registrar) without the Sensor (intake and
input guardrail), the Artifact Ledger, the Governor (orchestrator) or the Comparator
(reconciliation), so every record is ``new``. Until the Ledger exists, the caller passes
the artifact ID and date, rerunning on a recorded artifact is refused, and artifact files
are found by name in ``<memory>/artifacts/``. All of this is replaced by those roles.
"""

import dataclasses
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from knowledge_automata.agents.registrar import (
    ArtifactRefusedError,
    DraftOutcome,
    Registrar,
    check_artifact,
    draft_record,
)
from knowledge_automata.core.prompts import load_prompt
from knowledge_automata.core.records import new_record
from knowledge_automata.domains.project_management.decision_log_view import (
    INDEX,
    OWNED,
    render_decision_log,
)
from knowledge_automata.domains.project_management.registers import DECISION_LOG
from knowledge_automata.llm import ChatModel, LLMSettings
from knowledge_automata.llm.settings import Thinking
from knowledge_automata.storage.record_store import RecordStore
from knowledge_automata.views.markdown import (
    VIEWS_FOLDER,
    ViewDifferences,
    check_views,
    write_views,
)

DEFAULT_MEMORY = Path("runtime/memory")
ARTIFACTS_FOLDER = "artifacts"
MAX_ARTIFACT_CHARACTERS = 50_000

# Thinking cost about 6x the billed output tokens for the same validation result in the
# handoff 003 smoke check; revisited with the sample project's evaluation set (ADR-0014).
DECISION_REGISTRAR_THINKING: Thinking = "disabled"

_ARTIFACT_ID = re.compile(r"ART-[0-9]{4,}", re.ASCII)
_ARTIFACT_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", re.ASCII)
_ARTIFACT_FILE = re.compile(r"(ART-[0-9]{4,})[-.]", re.ASCII)


class InputError(Exception):
    """Input the user must fix: bad arguments, a refused artifact, or one already recorded."""


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


def scan_artifacts(memory: Path) -> dict[str, str]:
    """Map artifact IDs to files in ``<memory>/artifacts/``, relative to the memory folder.

    A file belongs to an artifact when its name starts with the ID followed by ``-`` or
    ``.``. Two files for one ID is an error. The Artifact Ledger replaces this convention.
    """
    folder = memory / ARTIFACTS_FOLDER
    if not folder.is_dir():
        return {}
    links: dict[str, str] = {}
    for path in sorted(folder.iterdir()):
        match = _ARTIFACT_FILE.match(path.name)
        if match is None or not path.is_file():
            continue
        artifact_id = match.group(1)
        relative = path.relative_to(memory).as_posix()
        if artifact_id in links:
            raise InputError(
                f"Two files in {folder} belong to {artifact_id}: "
                f"{Path(links[artifact_id]).name!r} and {path.name!r}"
            )
        links[artifact_id] = relative
    return links


def render_views(memory: Path) -> dict[str, str]:
    records = RecordStore(memory).load_all(DECISION_LOG)
    return render_decision_log(records, scan_artifacts(memory))


def write_decision_log_views(memory: Path) -> ViewDifferences:
    """Regenerate the decision log views from the stored records."""
    return write_views(memory / VIEWS_FOLDER, render_views(memory), OWNED)


def check_decision_log_views(memory: Path) -> ViewDifferences:
    """Compare the committed decision log views with the generator's output."""
    return check_views(memory / VIEWS_FOLDER, render_views(memory), OWNED)


@dataclass(frozen=True)
class RecordOutcome:
    run_id: str | None
    draft: DraftOutcome  # attempts, usage, model, prompt version, and errors when rejected
    record_id: str | None = None
    record_path: Path | None = None
    index_path: Path | None = None

    @property
    def accepted(self) -> bool:
        return self.record_id is not None


def validate_artifact_arguments(artifact_id: str, artifact_date: str | None) -> None:
    if not _ARTIFACT_ID.fullmatch(artifact_id):
        raise InputError(f"--artifact-id must look like ART-0001, got {artifact_id!r}")
    if artifact_date is not None:
        try:
            if not _ARTIFACT_DATE.fullmatch(artifact_date):
                raise ValueError
            date.fromisoformat(artifact_date)
        except ValueError:
            raise InputError(
                f"--artifact-date must be a real date as YYYY-MM-DD, got {artifact_date!r}"
            ) from None


def read_artifact(path: Path) -> str:
    """Read an artifact as UTF-8 (a BOM is tolerated), with line endings as LF."""
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise InputError(f"Cannot read the artifact {path}: {error.strerror or error}") from None
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise InputError(f"The artifact {path} is not valid UTF-8 text") from None
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        raise InputError(f"The artifact {path} is empty")
    if len(text) > MAX_ARTIFACT_CHARACTERS:
        raise InputError(
            f"The artifact {path} has {len(text):,} characters; the limit is "
            f"{MAX_ARTIFACT_CHARACTERS:,}"
        )
    try:
        check_artifact(text)
    except ArtifactRefusedError as error:
        raise InputError(f"The artifact {path} was refused: {error}") from None
    return text


def record_decision(
    *,
    artifact_path: Path,
    artifact_id: str,
    artifact_date: str | None,
    memory: Path,
    llm: ChatModel,
    now: datetime,
) -> RecordOutcome:
    """Draft, validate and store one decision record from one artifact, then the views.

    Raises ``InputError`` before any call for bad input or an artifact already recorded.
    ``OSError`` from reading or writing records and views propagates.
    """
    validate_artifact_arguments(artifact_id, artifact_date)
    text = read_artifact(artifact_path)

    store = RecordStore(memory)
    existing = store.ids_citing(DECISION_LOG, artifact_id)
    if existing:
        raise InputError(
            f"{artifact_id} is already recorded in {', '.join(existing)}; nothing was sent "
            "to the model. Rerunning an artifact needs the Artifact Ledger."
        )

    outcome = draft_record(decision_registrar(), llm, text, artifact_id=artifact_id)
    run_id = getattr(llm, "run_id", None)
    if not outcome.accepted:
        return RecordOutcome(run_id=run_id, draft=outcome)

    record_id = store.next_id(DECISION_LOG)
    record = new_record(
        spec=DECISION_LOG,
        record_id=record_id,
        content=outcome.draft["content"],
        quotes=outcome.draft["evidence"],
        artifact_id=artifact_id,
        artifact_date=artifact_date,
        model=outcome.model,
        prompt_version=outcome.prompt_version,
        now=now,
    )
    path = store.save_new(record, DECISION_LOG)
    write_decision_log_views(memory)
    return RecordOutcome(
        run_id=run_id,
        draft=outcome,
        record_id=record_id,
        record_path=path,
        index_path=memory / VIEWS_FOLDER / INDEX,
    )
