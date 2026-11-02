"""The pipeline: intake, processing through the Governor (orchestrator), release and views.

The Sensor (intake and input guardrail) and the agents decide; this module reads and writes
the files: artifact copies, Artifact Ledger entries, work orders files, records and views.
``process_artifact`` runs steps 4 and 5 of the data flow for one artifact the Ledger
allows (ADR-0018): the Governor finds the work orders, and for each order routed to a
register with a Registrar, the Registrar drafts, the Comparator (reconciliation) classifies
the draft against the active records, and code applies the write rule (ADR-0017).

Write order: the work orders file once the Governor's reply is accepted; then, for each
order, the records (the new record before the record it supersedes or revises), the views,
then the order's result in the work orders file; the Ledger once, at the end. An
interruption leaves the Ledger behind the work orders file and the file behind the
records, never ahead; the next run continues from the file, rebuilds a Ledger left behind,
and stops before any call when a record changed without its order's result.
"""

import dataclasses
import uuid
from collections.abc import Callable, Mapping
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
from knowledge_automata.agents.governor import (
    MAX_ITEMS_VARIABLE,
    Governor,
    GovernorOutcome,
    GovernorSettings,
    find_work_orders,
    load_register_definitions,
)
from knowledge_automata.agents.registrar import (
    ArtifactRefusedError,
    DraftOutcome,
    Registrar,
    check_artifact,
    draft_record,
)
from knowledge_automata.core import ledger
from knowledge_automata.core import work_orders as orders_file
from knowledge_automata.core.prompts import load_prompt
from knowledge_automata.core.records import new_record
from knowledge_automata.core.registers import RegisterSpec
from knowledge_automata.core.validation import revision_errors, validate_record
from knowledge_automata.core.work_orders import WorkOrder
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
from knowledge_automata.domains.project_management.registers import DECISION_LOG, REGISTERS
from knowledge_automata.llm import LanguageModel, LLMConfigError, LLMError, LLMSettings
from knowledge_automata.llm.settings import Thinking
from knowledge_automata.storage import artifact_files
from knowledge_automata.storage.ledger_store import ARTIFACT_ID, LedgerStore
from knowledge_automata.storage.record_store import RecordStore, RecordStoreError
from knowledge_automata.storage.work_order_store import WorkOrderStore
from knowledge_automata.views.markdown import (
    VIEWS_FOLDER,
    ViewDifferences,
    check_views,
    write_views,
)

DEFAULT_MEMORY = Path("runtime/memory")
PROCESSABLE_STATUSES = frozenset({"accepted", "failed", "processed"})
RERUN_REASON = "Rerun: the earlier run recorded nothing"
REBUILD_REASON = "Rebuilt from the work orders file"
NOTHING_SENT = "nothing was sent to the model"

# Command A+ is a reasoning model: with thinking disabled it wrote its reasoning as prose
# before the JSON, and most replies were rejected (handoff 006, Addendum A; ADR-0014).
# Sent explicitly rather than left to the provider's default.
CHAT_THINKING_DEFAULT: Thinking = "enabled"


class InputError(Exception):
    """Input the user must fix: bad arguments, an unreadable file, or an artifact the
    Ledger does not allow to be processed."""


def governor() -> Governor:
    return Governor(
        agent="governor",
        prompt=load_prompt("core/governor.v1"),
        retry_prompt=load_prompt("core/governor-retry.v1"),
        registers=load_register_definitions(REGISTERS),
    )


def decision_registrar() -> Registrar:
    return Registrar(
        agent="decision-registrar",
        spec=DECISION_LOG,
        prompt=load_prompt("project-management/decision-registrar.v2"),
        retry_prompt=load_prompt("core/registrar-retry.v1"),
        takes_work_order=True,
    )


# The registers with a Registrar; the Governor's orders for any other are not routed.
REGISTRARS: dict[str, Callable[[], Registrar]] = {DECISION_LOG.name: decision_registrar}
REGISTER_NAMES: tuple[str, ...] = tuple(spec.name for spec in REGISTERS)


def decision_comparator() -> Comparator:
    return Comparator(
        agent="comparator",
        spec=DECISION_LOG,
        prompt=load_prompt("project-management/decision-comparator.v1"),
        retry_prompt=load_prompt("core/comparator-retry.v1"),
    )


def agent_chat_settings(settings: LLMSettings) -> LLMSettings:
    """Apply the thinking default unless ``KA_CHAT_THINKING`` is set.

    One model client serves the Governor, the Registrars and the Comparator, so this is
    the single place that sets the default for every agent.
    """
    if settings.chat_thinking is None:
        return dataclasses.replace(settings, chat_thinking=CHAT_THINKING_DEFAULT)
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
    """The Operator's release of a quarantined or held artifact.

    A ``held`` artifact becomes ``accepted`` by ``operator`` with no Sensor check and no
    read of its copy (its bytes were already accepted); the next ``process`` runs its saved
    work orders. For a quarantined artifact the Sensor reruns its checks and decides.

    Raises ``SensorInputError`` for a missing reason, ``InputError`` for an entry that is
    neither quarantined nor held, and ``LedgerEntryNotFoundError`` for an unknown ID, before
    the copy is read.
    """
    reason = sensor.check_reason(reason)
    store = LedgerStore(memory)
    entry = store.load(artifact_id)
    if entry["status"] == "held":
        released = ledger.transition(entry, to="accepted", by="operator", at=now, reason=reason)
        store.save_transition(entry, released)
        return sensor.ReleaseOutcome(True, released)
    if entry["status"] != "quarantined":
        raise InputError(
            f"{artifact_id} is {entry['status']}; only a quarantined or held artifact can be "
            "released"
        )
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


def decision_log_index(memory: Path) -> Path:
    return memory / VIEWS_FOLDER / INDEX


def check_decision_log_views(memory: Path) -> ViewDifferences:
    """Compare the committed decision log views with the generator's output."""
    return check_views(memory / VIEWS_FOLDER, render_views(memory), OWNED)


def supersession_link_problems(memory: Path) -> list[str]:
    """Messages for inconsistent supersession links in the decision log."""
    return check_supersession_links(RecordStore(memory).load_all(DECISION_LOG))


@dataclass(frozen=True)
class Written:
    """The records one work order wrote. ``record_id`` is the record created or revised
    (for a supersession, the new record); ``related_id`` the record it superseded."""

    change: str
    record_id: str
    related_id: str | None
    revision: int  # of record_id after the change
    schema_version: str
    sources_added: int
    filled: tuple[str, ...]  # update: empty fields filled from the draft
    ignored: tuple[str, ...]  # update: fields kept although the draft's value differs
    path: Path

    @property
    def record_ids(self) -> tuple[str, ...]:
        """Every record written, the new or revised one first."""
        return tuple(item for item in (self.record_id, self.related_id) if item)


@dataclass(frozen=True)
class OrderOutcome:
    """One work order in a run: what it did, or why it did not run.

    ``state`` is the order's state in the work orders file before the run. An order that
    ran was ``pending`` or ``rejected``; one that did not is ``recorded`` (by an earlier
    run), ``not-routed``, or ``rejected`` (left for a rerun, because the Ledger said
    ``accepted``).
    """

    number: int
    register: str
    label: str  # verified artifact text (ADR-0018)
    state: str
    draft: DraftOutcome | None = None  # None when the order did not run
    active_records: int = 0  # active records when the Comparator ran
    comparison: ComparisonOutcome | None = None  # None when not compared
    written: Written | None = None  # None unless recorded in this run
    earlier: Mapping[str, Any] | None = None  # the produced item of an earlier run

    @property
    def ran(self) -> bool:
        return self.draft is not None

    @property
    def recorded(self) -> bool:
        return self.written is not None

    @property
    def rejected_stage(self) -> str | None:
        """``draft`` or ``comparison`` when the order ran and recorded nothing, else None."""
        if self.draft is None or self.recorded:
            return None
        return "draft" if not self.draft.accepted else "comparison"


@dataclass(frozen=True)
class ProcessPlan:
    """What ``process_artifact`` will do, decided from the files alone (3.7).

    ``action`` is ``governor`` (call the Governor, then run the orders), ``orders`` (run
    the saved work orders), ``hold`` (mark the artifact ``held`` again, no call) or
    ``rebuild`` (write the Ledger from the work orders file, no call).
    """

    entry: dict[str, Any]
    action: str
    file: dict[str, Any] | None = None
    orders: tuple[dict[str, Any], ...] = ()

    @property
    def needs_llm(self) -> bool:
        return self.action in {"governor", "orders"}

    @property
    def rerun(self) -> bool:
        return self.entry["status"] == "processed"


@dataclass(frozen=True)
class ProcessOutcome:
    """What ``process_artifact`` did."""

    run_id: str
    plan: ProcessPlan
    entry: dict[str, Any]  # the Ledger entry after the run
    file: dict[str, Any] | None  # the work orders file after the run; None when rejected
    governor: GovernorOutcome | None = None  # None when the Governor was not called
    orders: tuple[OrderOutcome, ...] = ()  # every order in the file, in order number

    @property
    def held(self) -> bool:
        return self.entry["status"] == "held"

    @property
    def rebuilt(self) -> bool:
        return self.plan.action == "rebuild"

    @property
    def saved(self) -> bool:
        """The work orders came from a saved file; the Governor was not called."""
        return self.plan.file is not None

    @property
    def governor_rejected(self) -> bool:
        return self.governor is not None and not self.governor.accepted

    def count(self, state: str) -> int:
        """Orders in ``state`` in the work orders file after the run."""
        if self.file is None:
            return 0
        return sum(1 for order in self.file["orders"] if order["state"] == state)

    @property
    def routed(self) -> int:
        return 0 if self.file is None else len(orders_file.routed_orders(self.file))

    @property
    def ok(self) -> bool:
        """Nothing was held or rejected: no routed order is left ``rejected`` in the file,
        including one an interrupted earlier run rejected."""
        if self.held or self.governor_rejected:
            return False
        return self.count("rejected") == 0


def processable(artifact_id: str, memory: Path) -> ProcessPlan:
    """Decide what ``process_artifact`` will do, or raise ``InputError`` (3.7).

    ``accepted`` and ``failed`` artifacts may be processed. A ``processed`` one that
    recorded nothing may be processed again if the Governor was rejected (no work orders
    file), if a routed order is ``pending`` or ``rejected``, or if the Ledger is behind the
    work orders file. Before any call: the decision log's supersession links must be whole,
    and the records must agree with the work orders file (or, without one, the Ledger must
    list no Governor run and the records cite nothing from the artifact). Reads only, so
    the CLI can call it before building the LLM. Raises ``LedgerEntryNotFoundError`` for an
    unknown ID.
    """
    if not ARTIFACT_ID.fullmatch(artifact_id):
        raise InputError(f"The artifact ID must look like ART-0001, got {artifact_id!r}")
    entry = LedgerStore(memory).load(artifact_id)
    status = entry["status"]
    if status == "quarantined":
        raise InputError(
            f"{artifact_id} is quarantined ({_last_check(entry)}); {NOTHING_SENT}. Release it "
            f"with `knowledge-automata release {artifact_id} --reason TEXT`, or fix the file "
            "and ingest it again."
        )
    if status == "rejected":
        raise InputError(
            f"{artifact_id} was rejected by the Sensor ({_last_check(entry)}); {NOTHING_SENT}. "
            "Fix the file and ingest it again."
        )
    if status == "held":
        raise InputError(
            f"{artifact_id} is held ({entry['history'][-1]['reason']}); {NOTHING_SENT}. "
            f"Review the artifact, then release it with `knowledge-automata release "
            f"{artifact_id} --reason TEXT`."
        )
    if status not in PROCESSABLE_STATUSES or (status == "processed" and entry["produced"]):
        raise InputError(f"{artifact_id} is already {status} ({_results(entry)}); {NOTHING_SENT}.")

    problems = supersession_link_problems(memory)
    if problems:
        raise InputError(
            "The decision log has an inconsistent supersession link; "
            f"{NOTHING_SENT}.\n" + "\n".join(f"- {problem}" for problem in problems)
        )

    work_orders = WorkOrderStore(memory)
    file = work_orders.load(artifact_id)
    if file is None:
        return _plan_without_file(entry, memory, work_orders.path(artifact_id))

    store = RecordStore(memory)
    records = [record for spec in _routed_specs() for record in store.load_all(spec)]
    problems = orders_file.history_count_problems(file, records, artifact_id)
    if problems:
        raise InputError(
            f"The work orders file of {artifact_id} is behind the records, for example after "
            f"an interrupted run; {NOTHING_SENT}. Correct the records or the file "
            f"({work_orders.path(artifact_id).as_posix()}) by hand:\n"
            + "\n".join(f"- {problem}" for problem in problems)
        )
    if orders_file.needs_hold(file, entry["history"]):
        return ProcessPlan(entry, "hold", file)
    orders = orders_file.orders_to_run(file, status)
    if orders:
        return ProcessPlan(entry, "orders", file, tuple(orders))
    if status != "processed" or orders_file.ledger_is_behind(entry, file, REGISTER_NAMES):
        return ProcessPlan(entry, "rebuild", file)
    raise InputError(
        f"{artifact_id} is already processed: {_nothing_routed(file, artifact_id)}; "
        f"{NOTHING_SENT}. Reprocessing it needs its own design."
    )


def _plan_without_file(entry: dict[str, Any], memory: Path, path: Path) -> ProcessPlan:
    artifact_id = entry["id"]
    # A Governor run left results in the Ledger, so its work orders file must exist; a new
    # Governor call could find different orders and record the same items twice.
    governed = (
        entry["produced"]
        or "governor" in entry
        or any("work_order" in item for item in entry["rejected"])
    )
    if governed:
        raise InputError(
            f"The Ledger entry of {artifact_id} lists results of a Governor run, but its work "
            f"orders file ({path.as_posix()}) is missing; {NOTHING_SENT}. Restore the file."
        )
    store = RecordStore(memory)
    cited = [
        record_id for spec in _routed_specs() for record_id in store.ids_citing(spec, artifact_id)
    ]
    if cited:
        raise InputError(
            f"{artifact_id} is {entry['status']} in the Ledger but already recorded in "
            f"{', '.join(cited)}: the Ledger is behind the records, for example after an "
            f"interrupted run. {NOTHING_SENT.capitalize()}; correct the Ledger entry by hand."
        )
    return ProcessPlan(entry, "governor")


def _routed_specs() -> list[RegisterSpec]:
    return [spec for spec in REGISTERS if spec.name in REGISTRARS]


def not_routed_summary(file: Mapping[str, Any]) -> str:
    """For example ``1 risk-register, not routed``; empty when every order is routed."""
    block = orders_file.ledger_governor_block(file, REGISTER_NAMES)
    counts = [
        f"{item['count']} {item['register']}" for item in block["work_orders"] if not item["routed"]
    ]
    return f"{', '.join(counts)}, not routed" if counts else ""


def _nothing_routed(file: Mapping[str, Any], artifact_id: str) -> str:
    if not file["orders"]:
        return f"the Governor found nothing to record in {artifact_id}"
    return (
        f"{artifact_id} has no work orders for a register with a Registrar "
        f"({not_routed_summary(file)})"
    )


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
            f"{where} no longer matches its hash in the Ledger; {NOTHING_SENT}. "
            "Artifact copies are read-only: restore the file or ingest the new version."
        )
    text = sensor.decode(raw)
    if text is None:
        raise InputError(f"{where} is not valid UTF-8; {NOTHING_SENT}.")
    return sensor.normalize_newlines(text)


def held_reason(file: Mapping[str, Any]) -> str:
    """The ``held`` reason, judged by the file's own ``max_items``."""
    routed = len(orders_file.routed_orders(file))
    return (
        f"The Governor found {routed} work orders for registers with a Registrar, more than "
        f"{MAX_ITEMS_VARIABLE} ({file['max_items']}); nothing was drafted. Review the "
        "artifact, then release it."
    )


def process_artifact(
    *,
    artifact_id: str,
    memory: Path,
    llm: LanguageModel | None,
    now: datetime,
    comparator_settings: ComparatorSettings,
    governor_settings: GovernorSettings,
) -> ProcessOutcome:
    """Process one Ledger artifact through the Governor (handoff 007, 3.1 and 3.5 to 3.7).

    Without a work orders file the Governor reads the artifact: a rejected reply makes the
    entry ``processed`` with a Governor-stage rejected item; an accepted one is saved as
    the work orders file, and more routed orders than ``governor_settings.max_items`` make
    the entry ``held``. Then each order to run is drafted, compared and written, and its
    result saved in the file. The Ledger is written once, at the end: ``processed``, its
    lists rebuilt from the file. A provider error other than ``LLMConfigError`` makes the
    entry ``failed`` with the results so far, then is raised again. Raises ``InputError``
    before any call when the files do not allow the artifact to be processed.

    ``llm`` may be None when ``processable`` says no call is needed; such a run gets a new
    run ID. ``OSError`` propagates.
    """
    plan = processable(artifact_id, memory)
    if plan.needs_llm and llm is None:
        raise ValueError(f"Processing {artifact_id} needs an LLM")
    run_id = getattr(llm, "run_id", None) if llm is not None else str(uuid.uuid4())
    if not run_id:
        raise ValueError("process_artifact needs an LLM with a run_id, such as ObservedLLM")
    run = _Run(plan, memory, now, run_id)
    if plan.action == "hold":
        return run.hold(plan.file)
    if plan.action == "rebuild":
        return run.finish(plan.file, reason=REBUILD_REASON)

    text = read_artifact_text(memory, plan.entry)
    try:
        check_artifact(text)
    except ArtifactRefusedError as error:
        raise InputError(f"{artifact_id} was refused: {error}") from None
    governed = None
    file = plan.file
    if file is None:
        governed = run.guard(
            lambda: find_work_orders(governor(), llm, text, artifact_id=artifact_id)
        )
        if not governed.accepted:
            return run.governor_rejected(governed)
        file = orders_file.new_file(
            artifact_id=artifact_id,
            run_id=run_id,
            model=governed.model,
            prompt_version=governed.prompt_version,
            attempts=governed.attempts,
            definitions=governed.definitions,
            work_orders=governed.work_orders,
            routed=REGISTRARS.keys(),
            max_items=governor_settings.max_items,
            now=now,
        )
        WorkOrderStore(memory).save_new(file)
        if orders_file.needs_hold(file, plan.entry["history"]):
            return run.hold(file, governed)
        to_run = orders_file.orders_to_run(file, plan.entry["status"])
    else:
        to_run = list(plan.orders)

    ran: dict[int, OrderOutcome] = {}
    for order in to_run:
        file, ran[order["number"]] = run.order(file, order, llm, text, comparator_settings)
    return run.finish(file, governed=governed, ran=ran)


class _Run:
    """One run of ``process_artifact``: the writes it makes and the outcome it returns."""

    def __init__(self, plan: ProcessPlan, memory: Path, now: datetime, run_id: str) -> None:
        self.plan = plan
        self.entry = plan.entry
        self.memory = memory
        self.now = now
        self.run_id = run_id
        self.reason = RERUN_REASON if plan.rerun else None

    def _save(self, new: dict[str, Any]) -> dict[str, Any]:
        LedgerStore(self.memory).save_transition(self.entry, new)
        return new

    def _with_file(self, new: dict[str, Any], file: Mapping[str, Any]) -> dict[str, Any]:
        produced, rejected = orders_file.rebuilt_lists(self.entry, file)
        governor_block = orders_file.ledger_governor_block(file, REGISTER_NAMES)
        return ledger.with_results(new, produced, rejected, governor=governor_block)

    def guard(self, call: Callable[[], Any], file: Mapping[str, Any] | None = None) -> Any:
        """Make the provider calls; on a provider error, ``failed`` with the results so far."""
        try:
            return call()
        except LLMConfigError:
            raise
        except LLMError as error:
            failed = ledger.transition(
                self.entry,
                to="failed",
                by="governor",
                at=self.now,
                reason=self.reason,
                run_id=self.run_id,
                error_type=type(error).__name__,
            )
            self._save(self._with_file(failed, file) if file is not None else failed)
            raise

    def governor_rejected(self, governed: GovernorOutcome) -> ProcessOutcome:
        """``processed`` listing the rejected reply; no work orders file is written."""
        item: dict[str, Any] = {
            "stage": "governor",
            "run_id": self.run_id,
            "attempts": governed.attempts,
            "prompt_version": governed.prompt_version,
            "error_paths": ledger.error_paths(governed.errors),
        }
        if governed.error_type is not None:
            item["error_type"] = governed.error_type
        processed = ledger.transition(
            self.entry,
            to="processed",
            by="governor",
            at=self.now,
            reason=self.reason,
            run_id=self.run_id,
        )
        processed = ledger.with_results(
            processed, self.entry["produced"], [*self.entry["rejected"], item]
        )
        return ProcessOutcome(self.run_id, self.plan, self._save(processed), None, governed)

    def hold(self, file: dict[str, Any], governed: GovernorOutcome | None = None) -> ProcessOutcome:
        """``held`` with the file's run ID, so a release covers this file only."""
        held = ledger.transition(
            self.entry,
            to="held",
            by="governor",
            at=self.now,
            reason=held_reason(file),
            run_id=file["run_id"],
        )
        entry = self._save(self._with_file(held, file))
        orders = self._orders(file, {})
        return ProcessOutcome(file["run_id"], self.plan, entry, file, governed, orders)

    def order(
        self,
        file: dict[str, Any],
        order: Mapping[str, Any],
        llm: LanguageModel,
        text: str,
        comparator_settings: ComparatorSettings,
    ) -> tuple[dict[str, Any], OrderOutcome]:
        """Draft, compare and write one work order: the records, then the views, then the
        order's result in the work orders file."""
        artifact_id = self.entry["id"]
        artifact_date = self.entry.get("artifact_date")
        registrar = REGISTRARS[order["register"]]()
        work_order = WorkOrder(
            order["number"], order["register"], order["label"], tuple(order["evidence"])
        )
        store = RecordStore(self.memory)
        active: list[dict[str, Any]] = []

        def draft_and_compare() -> tuple[DraftOutcome, ComparisonOutcome | None]:
            draft = draft_record(
                registrar, llm, text, artifact_id=artifact_id, work_order=work_order
            )
            if not draft.accepted:
                return draft, None
            # Loaded per order, so a record an earlier order wrote is a candidate.
            active.extend(store.load_active(registrar.spec))
            comparison = compare(
                decision_comparator(),
                llm,
                draft=draft.draft,
                active_records=active,
                artifact_id=artifact_id,
                artifact_date=artifact_date,
                settings=comparator_settings,
            )
            return draft, comparison

        draft, comparison = self.guard(draft_and_compare, file)
        outcome = OrderOutcome(
            number=order["number"],
            register=order["register"],
            label=order["label"],
            state=order["state"],
            draft=draft,
            active_records=len(active),
            comparison=comparison,
        )
        if comparison is None or not comparison.accepted:
            result = {"rejected": _rejected_item(draft, comparison, self.run_id)}
        else:
            written = _apply_write_rule(
                store,
                draft,
                comparison,
                {record["id"]: record for record in active},
                artifact_id=artifact_id,
                artifact_date=artifact_date,
                now=self.now,
            )
            write_decision_log_views(self.memory)
            result = {"produced": _produced_item(draft, comparison, written)}
            outcome = dataclasses.replace(outcome, written=written)
        new_file = orders_file.with_order_result(file, order["number"], now=self.now, **result)
        WorkOrderStore(self.memory).save_progress(file, new_file)
        return new_file, outcome

    def finish(
        self,
        file: dict[str, Any],
        *,
        reason: str | None = None,
        governed: GovernorOutcome | None = None,
        ran: Mapping[int, OrderOutcome] | None = None,
    ) -> ProcessOutcome:
        """``processed``, its lists and Governor block rebuilt from the work orders file."""
        processed = ledger.transition(
            self.entry,
            to="processed",
            by="governor",
            at=self.now,
            reason=reason or self.reason,
            run_id=self.run_id,
        )
        entry = self._save(self._with_file(processed, file))
        orders = self._orders(file, ran or {})
        return ProcessOutcome(self.run_id, self.plan, entry, file, governed, orders)

    def _orders(
        self, file: Mapping[str, Any], ran: Mapping[int, OrderOutcome]
    ) -> tuple[OrderOutcome, ...]:
        """Every order: the outcome of those that ran, the earlier state of the others."""
        before = self.plan.file or file
        return tuple(
            ran.get(order["number"])
            or OrderOutcome(
                number=order["number"],
                register=order["register"],
                label=order["label"],
                state=order["state"],
                earlier=order.get("produced"),
            )
            for order in before["orders"]
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


def _apply_write_rule(
    store: RecordStore,
    draft: DraftOutcome,
    comparison: ComparisonOutcome,
    active: dict[str, dict[str, Any]],
    *,
    artifact_id: str,
    artifact_date: str | None,
    now: datetime,
) -> Written:
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
    return Written(
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
    draft: DraftOutcome, comparison: ComparisonOutcome, written: Written
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
