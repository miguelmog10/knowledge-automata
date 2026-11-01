"""The ``knowledge-automata`` command line.

Exit codes: 0 success; 1 the Governor's reply, a draft or a comparison rejected, artifact
held, quarantined or rejected, release refused, or views differ under ``--check``; 2 usage,
configuration or file problem; 3 provider error. Output never includes the settings, the
API key, prompts or artifact text (the title excepted). ``process`` prints the Comparator's
reason, which is model output, so the reader sees why a draft was classified as it was,
and each work order's label, which is verified artifact text (ADR-0018). Output is UTF-8.
"""

import argparse
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from knowledge_automata import pipeline
from knowledge_automata.agents import sensor
from knowledge_automata.agents.comparator import ComparatorConfigError, ComparatorSettings
from knowledge_automata.agents.governor import GovernorConfigError, GovernorSettings
from knowledge_automata.core.ledger import LedgerError
from knowledge_automata.llm import (
    LanguageModel,
    LLMConfigError,
    LLMError,
    LLMRateLimitError,
    LLMSettings,
    Usage,
    build_llm,
)
from knowledge_automata.storage.artifact_files import ArtifactPathError
from knowledge_automata.storage.ledger_store import LedgerStore, LedgerStoreError
from knowledge_automata.storage.record_store import RecordStoreError
from knowledge_automata.storage.work_order_store import WorkOrderStoreError
from knowledge_automata.views.markdown import VIEWS_FOLDER, ViewDifferences

EXIT_OK = 0
EXIT_REJECTED = 1
EXIT_USAGE = 2
EXIT_PROVIDER = 3

_USAGE_ERRORS = (
    pipeline.InputError,
    RecordStoreError,
    LedgerStoreError,
    LedgerError,
    WorkOrderStoreError,
    ArtifactPathError,
    sensor.SensorInputError,
    sensor.SensorConfigError,
    LLMConfigError,
    ComparatorConfigError,
    GovernorConfigError,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def _write_utf8() -> None:
    """Write output as UTF-8, like every other file the project writes.

    On Windows, Python encodes piped output as cp1252, so printing model output (the
    Comparator's reason) could crash after a run had already written its records.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="knowledge-automata",
        description="Institutional memory for groups that make decisions together.",
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    ingest = commands.add_parser(
        "ingest",
        help="Check one artifact file and add it to the Artifact Ledger.",
        description=(
            "Run the Sensor's intake checks on one file. An accepted or quarantined file is "
            "copied into the memory folder, unchanged; every new file gets a Ledger entry. "
            "A file whose content is already in the Ledger is not added again."
        ),
    )
    ingest.add_argument(
        "file", type=Path, metavar="FILE", help="artifact file (.md, .markdown or .txt)"
    )
    ingest.add_argument("--artifact-date", help="artifact date as YYYY-MM-DD")
    _memory_argument(ingest)

    process = commands.add_parser(
        "process",
        help="Find what one artifact holds for the registers and record it.",
        description=(
            "The Governor (orchestrator) finds the items in an accepted artifact that belong "
            "in a register and saves them as work orders. For each order for a register with "
            "a Registrar, the Registrar drafts a record, the Comparator compares it with the "
            "active records, and code applies the change (new, update, reaffirmation or "
            "supersession) and regenerates the views. The artifact's Ledger entry is updated "
            "last. An interrupted run continues from the saved work orders."
        ),
    )
    process.add_argument("artifact_id", metavar="ARTIFACT_ID", help="for example ART-0001")
    _memory_argument(process)

    release = commands.add_parser(
        "release",
        help="Release a quarantined or held artifact after review.",
        description=(
            "The Operator's manual release. A quarantined artifact: rerun the Sensor's "
            "checks on the stored copy without the size limit and, if they pass, mark it "
            "accepted. A held artifact (more work orders than KA_GOVERNOR_MAX_ITEMS): mark it "
            "accepted, so that process runs all its saved work orders."
        ),
    )
    release.add_argument("artifact_id", metavar="ARTIFACT_ID", help="for example ART-0005")
    release.add_argument("--reason", required=True, help="why it is released (1 to 500 chars)")
    _memory_argument(release)

    ledger = commands.add_parser(
        "ledger",
        help="List the artifacts in the Artifact Ledger.",
        description="List every Ledger entry: ID, status, title and the last check or reason.",
    )
    _memory_argument(ledger)

    views = commands.add_parser(
        "views",
        help="Regenerate the Markdown views from the stored records.",
        description="Regenerate the Markdown views from the stored records.",
    )
    _memory_argument(views)
    views.add_argument(
        "--check",
        action="store_true",
        help="write nothing; exit 1 if the views differ from the records",
    )
    return parser


def _memory_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--memory",
        type=Path,
        default=pipeline.DEFAULT_MEMORY,
        metavar="DIR",
        help=f"memory folder (default: {pipeline.DEFAULT_MEMORY.as_posix()})",
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    build: Callable[[LLMSettings], LanguageModel] = build_llm,
    clock: Callable[[], datetime] = utc_now,
) -> int:
    _write_utf8()
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exit_:
        return exit_.code if isinstance(exit_.code, int) else EXIT_USAGE
    try:
        if args.command == "ingest":
            return _ingest(args, clock)
        if args.command == "process":
            return _process(args, build, clock)
        if args.command == "release":
            return _release(args, clock)
        if args.command == "ledger":
            return _ledger(args)
        return _views(args)
    except _USAGE_ERRORS as error:
        return _fail(str(error), EXIT_USAGE)
    except OSError as error:
        return _fail(_describe_os_error(error), EXIT_USAGE)
    except LLMRateLimitError as error:
        hint = " The limit resets next month." if error.monthly_cap else ""
        return _fail(f"Provider error (LLMRateLimitError): {error}{hint}", EXIT_PROVIDER)
    except LLMError as error:
        return _fail(f"Provider error ({type(error).__name__}): {error}", EXIT_PROVIDER)


def _ingest(args: argparse.Namespace, clock: Callable[[], datetime]) -> int:
    outcome = pipeline.ingest_file(
        path=args.file,
        memory=args.memory,
        artifact_date=args.artifact_date,
        max_bytes=sensor.max_bytes_from_env(),
        now=clock(),
    )
    entry = outcome.entry
    if outcome.duplicate:
        print(f"Already in the Ledger as {entry['id']} ({entry['status']}); nothing was written")
        return EXIT_OK
    if outcome.status == "accepted":
        print(f"Accepted {entry['id']} ({entry['source']['name']}, {entry['size_bytes']:,} bytes)")
    else:
        last = entry["history"][-1]
        print(f"{outcome.status.capitalize()} {entry['id']} ({last['check']}: {last['reason']})")
    if entry.get("same_name_as"):
        print(f"Same file name as {', '.join(entry['same_name_as'])}")
    return EXIT_OK if outcome.status == "accepted" else EXIT_REJECTED


def _process(
    args: argparse.Namespace,
    build: Callable[[LLMSettings], LanguageModel],
    clock: Callable[[], datetime],
) -> int:
    artifact_id: str = args.artifact_id
    # Checked before building the LLM, so a refused artifact or a bad setting never needs an
    # API key and never costs a call.
    plan = pipeline.processable(artifact_id, args.memory)
    comparator_settings = ComparatorSettings.from_env()
    governor_settings = GovernorSettings.from_env()
    llm = None
    thinking = None
    if plan.needs_llm:
        settings = pipeline.agent_chat_settings(LLMSettings.from_env())
        thinking = settings.chat_thinking
        if plan.rerun:
            print(f"Rerunning {artifact_id}: its earlier run recorded nothing.")
        llm = build(settings)
    try:
        result = pipeline.process_artifact(
            artifact_id=artifact_id,
            memory=args.memory,
            llm=llm,
            now=clock(),
            comparator_settings=comparator_settings,
            governor_settings=governor_settings,
        )
    except LLMError as error:
        if not isinstance(error, LLMConfigError):
            _print(f"Run ID: {getattr(llm, 'run_id', None)}", sys.stdout)
            _print(
                f"{artifact_id} is now failed in the Ledger, with the results so far; "
                "run it again to continue.",
                sys.stderr,
            )
        raise
    print(f"Run ID: {result.run_id}")
    return _report(result, args.memory, thinking)


def _report(result: pipeline.ProcessOutcome, memory: Path, thinking: str | None) -> int:
    artifact_id = result.entry["id"]
    file = result.file
    governed = result.governor
    if result.rebuilt:
        print(
            f"Rebuilt the Ledger entry of {artifact_id} from its work orders file (run "
            f"{file['run_id']}); no call was made."
        )
        print(_summary(result))
        return EXIT_OK
    if governed is not None and not governed.accepted:
        _print(
            f"Rejected the Governor's reply for {artifact_id} after "
            f"{_attempts(governed.attempts)} (prompt {governed.prompt_version}, thinking "
            f"{thinking}); nothing was drafted and the Ledger lists the rejected reply. "
            "Errors of the last attempt:",
            sys.stderr,
        )
        for error in governed.errors:
            _print(f"- {error}", sys.stderr)
        print(_billed(result))
        return EXIT_REJECTED
    if governed is not None:
        print(_found(result, thinking))
    else:
        print(
            f"Using {_count(len(file['orders']), 'saved work order')} from run "
            f"{file['run_id']}; the Governor was not called."
        )
    if result.held:
        _print(result.entry["history"][-1]["reason"], sys.stderr)
        _print(
            f"{artifact_id} is now held; to continue, release it with "
            f"`knowledge-automata release {artifact_id} --reason TEXT`.",
            sys.stderr,
        )
        if governed is not None:
            print(_billed(result))
        return EXIT_REJECTED
    if not file["orders"]:
        print(f"The Governor found nothing to record in {artifact_id}.")
        print(_billed(result))
        return EXIT_OK
    if not result.routed:
        print(
            f"The Governor found {_count(len(file['orders']), 'work order')}, none for a "
            f"register with a Registrar ({pipeline.not_routed_summary(file)}): nothing to "
            "record yet."
        )
        print(_billed(result))
        return EXIT_OK

    total = len(result.orders)
    for order in result.orders:
        heading = f"Work order {order.number} of {total}, {order.register}"
        if order.state == "not-routed":
            print(f"{heading}: not routed (no Registrar yet)")
            continue
        print(f'{heading}: "{order.label}"')
        for line in _order_lines(order):
            print(f"  {line}")
    print(_summary(result))
    print(_billed(result))
    if any(order.recorded for order in result.orders):
        print(f"Index: {pipeline.decision_log_index(memory).as_posix()}")
    return EXIT_OK if result.ok else EXIT_REJECTED


def _found(result: pipeline.ProcessOutcome, thinking: str | None) -> str:
    governed = result.governor
    found = (
        _count(len(result.file["orders"]), "work order")
        if result.file["orders"]
        else "no work orders"
    )
    counts = [
        f"{item['count']} {item['register']}"
        + ("" if item["routed"] else " (no Registrar yet, not routed)")
        for item in result.entry["governor"]["work_orders"]
    ]
    return (
        f"Found {found} in {result.entry['id']} in {_attempts(governed.attempts)} (model "
        f"{governed.model}, prompt {governed.prompt_version}, definitions "
        f"{', '.join(governed.definitions)}, thinking {thinking})"
        + (f": {', '.join(counts)}" if counts else "")
    )


def _order_lines(order: pipeline.OrderOutcome) -> list[str]:
    """What one work order did, or why it did not run."""
    if not order.ran:
        if order.state == "recorded":
            return [f"Recorded by an earlier run: {_produced_change(order.earlier)}"]
        return ["Rejected by an earlier run, which was interrupted; the Ledger lists it"]
    draft = order.draft
    if not draft.accepted:
        return [
            f"Rejected the draft after {_attempts(draft.attempts)} (prompt "
            f"{draft.prompt_version}); the Ledger lists it. Errors of the last attempt:",
            *(f"- {error}" for error in draft.errors),
        ]
    lines = [f"Drafted in {_attempts(draft.attempts)} (prompt {draft.prompt_version})"]
    comparison = order.comparison
    if not comparison.compared:
        lines.append("No active decisions to compare with: recorded as new without a comparison")
    else:
        candidates = ", ".join(
            f"{candidate.record_id} ({candidate.score:.2f})" for candidate in comparison.candidates
        )
        lines.append(
            f"Compared with {_count(order.active_records, 'active decision')}; "
            f"candidates: {candidates}"
        )
        if not comparison.accepted:
            return [
                *lines,
                f"Rejected the comparison after {_attempts(comparison.attempts)} (prompt "
                f"{comparison.prompt_version}); the Ledger lists it. Errors of the last "
                "attempt:",
                *(f"- {error}" for error in comparison.errors),
            ]
        target = f" of {comparison.target_id}" if comparison.target_id else ""
        lines.append(
            f"Classified as {comparison.classification}{target} in "
            f"{_attempts(comparison.attempts)} (prompt {comparison.prompt_version}): "
            + " ".join(comparison.reason.split())
        )
    return lines + _change_lines(order.written)


def _produced_change(item: Mapping[str, Any]) -> str:
    change = f"{item.get('change', 'new')} {item['record_id']}"
    if "related_id" in item:
        change += f", superseding {item['related_id']}"
    return change


def _change_lines(written: pipeline.Written) -> list[str]:
    record_id = written.record_id
    if written.change == "new":
        return [f"Recorded {record_id} as a new decision"]
    if written.change == "supersession":
        return [f"Recorded {record_id}, superseding {written.related_id} (now superseded)"]
    if written.change == "reaffirmation":
        added = _count(written.sources_added, "source")
        return [f"Reaffirmed {record_id} (revision {written.revision}): added {added}"]
    filled = f"filled {', '.join(written.filled)}" if written.filled else "no empty fields filled"
    lines = [f"Updated {record_id} to revision {written.revision}: {filled}"]
    if written.ignored:
        lines.append(
            f"Kept the existing {', '.join(written.ignored)} in {record_id} (the draft's "
            "wording differs; a change of substance would be a supersession)"
        )
    return lines


def _summary(result: pipeline.ProcessOutcome) -> str:
    return (
        f"Recorded {result.count('recorded')} of "
        f"{_count(result.routed, 'routed work order')}; {result.count('rejected')} rejected; "
        f"{result.count('not-routed')} not routed"
    )


def _attempts(count: int) -> str:
    return _count(count, "attempt")


def _count(count: int, noun: str) -> str:
    return f"{count} {noun}{'s' if count != 1 else ''}"


def _release(args: argparse.Namespace, clock: Callable[[], datetime]) -> int:
    outcome = pipeline.release_artifact(
        artifact_id=args.artifact_id, memory=args.memory, reason=args.reason, now=clock()
    )
    if not outcome.released:
        return _fail(
            f"{args.artifact_id} is still quarantined ({outcome.check}: {outcome.reason}); "
            "nothing was written",
            EXIT_REJECTED,
        )
    if outcome.entry["history"][-2]["status"] == "held":
        print(
            f"Released {args.artifact_id}: it is now accepted; process {args.artifact_id} "
            "runs its saved work orders"
        )
        return EXIT_OK
    print(f"Released {args.artifact_id}: it is now accepted")
    return EXIT_OK


def _ledger(args: argparse.Namespace) -> int:
    memory: Path = args.memory
    if not memory.is_dir():
        return _fail(f"Memory folder not found: {memory}", EXIT_USAGE)
    entries = LedgerStore(memory).load_all()
    if not entries:
        print(f"The Ledger in {memory.as_posix()} is empty.")
    for entry in entries:
        print(_ledger_line(entry))
    return EXIT_OK


def _ledger_line(entry: Mapping[str, Any]) -> str:
    last = entry["history"][-1]
    details = [
        f"{last['check']}: {last['reason']}" if "check" in last else last.get("reason"),
        last.get("error_type"),
    ]
    line = f"{entry['id']}  {entry['status']:<11}  {entry['title']}"
    return line + "".join(f"  ({detail})" for detail in details + _changes(entry) if detail)


def _changes(entry: Mapping[str, Any]) -> list[str]:
    """One detail per produced record, for example ``update DEC-0002``, then the work
    orders not routed, for example ``1 risk-register not routed``."""
    changes = [_produced_change(item) for item in entry.get("produced", [])]
    for item in entry.get("governor", {}).get("work_orders", []):
        if not item["routed"]:
            changes.append(f"{item['count']} {item['register']} not routed")
    return changes


def _views(args: argparse.Namespace) -> int:
    memory: Path = args.memory
    if not memory.is_dir():
        return _fail(f"Memory folder not found: {memory}", EXIT_USAGE)
    problems = pipeline.supersession_link_problems(memory)
    if problems:
        _print("The decision log has an inconsistent supersession link:", sys.stderr)
        for problem in problems:
            _print(f"- {problem}", sys.stderr)
        return _fail("No view was written or checked.", EXIT_USAGE)
    views_dir = (memory / VIEWS_FOLDER).as_posix()
    if args.check:
        differences = pipeline.check_decision_log_views(memory)
        if differences.ok:
            print(f"Views in {views_dir} match the records.")
            return EXIT_OK
        _print(f"Views in {views_dir} differ from the records:", sys.stderr)
        _print_differences(differences, sys.stderr)
        _print("Run `knowledge-automata views` to regenerate them.", sys.stderr)
        return EXIT_REJECTED

    differences = pipeline.write_decision_log_views(memory)
    if differences.ok:
        print(f"Views in {views_dir} are already up to date.")
    else:
        print(f"Updated views in {views_dir}:")
        _print_differences(differences, sys.stdout, ("written", "rewritten", "deleted"))
    return EXIT_OK


def _print_differences(
    differences: ViewDifferences,
    stream: TextIO,
    labels: tuple[str, str, str] = ("missing", "changed", "extra"),
) -> None:
    groups = (differences.missing, differences.changed, differences.extra)
    for label, paths in zip(labels, groups, strict=True):
        for path in paths:
            _print(f"- {label}: {path}", stream)


def _billed(result: pipeline.ProcessOutcome) -> str:
    """Billed units per stage that ran, added up over every work order; "not reported"
    when the provider reports none."""

    def total(usage: Sequence[Usage], name: str, label: str) -> str:
        values = [getattr(item, name) for item in usage if getattr(item, name) is not None]
        return f"{label} {sum(values):,}" if values else f"{label} not reported"

    def chat(usage: Sequence[Usage]) -> str:
        return (
            total(usage, "input_tokens", "input tokens")
            + ", "
            + total(usage, "output_tokens", "output tokens")
        )

    def reported(usage: Sequence[Usage], units: Sequence[tuple[str, str]]) -> str:
        """Only the units the provider reports: Rerank v5 bills input tokens, older
        models search units (tool feedback, 2026-10-25)."""
        present = [
            total(usage, name, label)
            for name, label in units
            if any(getattr(item, name) is not None for item in usage)
        ]
        return ", ".join(present) or "not reported"

    stages = []
    if result.governor is not None:
        stages.append(("governor", chat(result.governor.usage)))
    drafts = [order.draft for order in result.orders if order.draft is not None]
    if drafts:
        stages.append(("drafts", chat([usage for draft in drafts for usage in draft.usage])))
    comparisons = [
        order.comparison
        for order in result.orders
        if order.comparison is not None and order.comparison.compared
    ]
    if comparisons:
        stages += [
            ("comparisons", chat([u for c in comparisons for u in c.chat_usage])),
            (
                "embed",
                total(
                    [u for c in comparisons for u in c.embed_usage], "input_tokens", "input tokens"
                ),
            ),
            (
                "rerank",
                reported(
                    [u for c in comparisons for u in c.rerank_usage],
                    [("input_tokens", "input tokens"), ("search_units", "search units")],
                ),
            ),
        ]
    if not stages:
        return "Billed: nothing (no call was made)"
    return "Billed: " + "; ".join(f"{stage} ({units})" for stage, units in stages)


def _describe_os_error(error: OSError) -> str:
    reason = error.strerror or str(error)
    if error.filename is not None:
        return f"Cannot access {error.filename}: {reason}"
    return f"File system error: {reason}"


def _print(message: str, stream: TextIO) -> None:
    print(message, file=stream)


def _fail(message: str, code: int) -> int:
    _print(message, sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
