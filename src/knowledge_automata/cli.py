"""The ``knowledge-automata`` command line.

Exit codes: 0 success; 1 draft or comparison rejected, artifact quarantined or rejected,
release refused, or views differ under ``--check``; 2 usage, configuration or file problem;
3 provider error. Output never includes the settings, the API key, prompts or artifact text
(the title excepted). ``record-decision`` prints the Comparator's reason, which is model
output, so the reader sees why a draft was classified as it was.
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
    ArtifactPathError,
    sensor.SensorInputError,
    sensor.SensorConfigError,
    LLMConfigError,
    ComparatorConfigError,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


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

    record = commands.add_parser(
        "record-decision",
        help="Record the most significant decision in one artifact.",
        description=(
            "Draft one decision from an accepted artifact with the Decision Registrar, "
            "compare it with the active decisions (Comparator), apply the change (new, "
            "update, reaffirmation or supersession), regenerate the decision log views and "
            "update the artifact's Ledger entry."
        ),
    )
    record.add_argument("artifact_id", metavar="ARTIFACT_ID", help="for example ART-0001")
    _memory_argument(record)

    release = commands.add_parser(
        "release",
        help="Release a quarantined artifact after review.",
        description=(
            "The Operator's manual release: rerun the Sensor's checks on the stored copy "
            "without the size limit and, if they pass, mark the artifact accepted."
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
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exit_:
        return exit_.code if isinstance(exit_.code, int) else EXIT_USAGE
    try:
        if args.command == "ingest":
            return _ingest(args, clock)
        if args.command == "record-decision":
            return _record_decision(args, build, clock)
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


def _record_decision(
    args: argparse.Namespace,
    build: Callable[[LLMSettings], LanguageModel],
    clock: Callable[[], datetime],
) -> int:
    artifact_id: str = args.artifact_id
    # Checked before building the LLM, so a refused artifact or a bad setting never needs an
    # API key and never costs a call.
    entry = pipeline.recordable_entry(artifact_id, args.memory)
    comparator_settings = ComparatorSettings.from_env()
    settings = pipeline.record_decision_settings(LLMSettings.from_env())
    if entry["status"] == "processed":
        print(f"Rerunning {artifact_id}: its earlier run recorded nothing.")
    llm = build(settings)
    try:
        result = pipeline.record_decision(
            artifact_id=artifact_id,
            memory=args.memory,
            llm=llm,
            now=clock(),
            comparator_settings=comparator_settings,
        )
    except LLMError as error:
        if not isinstance(error, LLMConfigError):
            _print(f"Run ID: {getattr(llm, 'run_id', None)}", sys.stdout)
            _print(f"{artifact_id} is now failed in the Ledger; run it again to retry.", sys.stderr)
        raise
    draft = result.draft
    print(f"Run ID: {result.run_id}")

    if not draft.accepted:
        _print(
            f"Rejected the draft from {artifact_id} after {_attempts(draft.attempts)} "
            f"(prompt {draft.prompt_version}, thinking {settings.chat_thinking}); "
            "no record was written and the Ledger lists the rejected draft. "
            "Errors of the last attempt:",
            sys.stderr,
        )
        for error in draft.errors:
            _print(f"- {error}", sys.stderr)
        print(_billed(result))
        return EXIT_REJECTED

    print(
        f"Drafted a decision from {artifact_id} in {_attempts(draft.attempts)} "
        f"(model {draft.model}, prompt {draft.prompt_version}, "
        f"thinking {settings.chat_thinking})"
    )
    comparison = result.comparison
    if not comparison.compared:
        print("No active decisions to compare with: recorded as new without a comparison.")
    else:
        candidates = ", ".join(
            f"{candidate.record_id} ({candidate.score:.2f})" for candidate in comparison.candidates
        )
        print(
            f"Compared with {_count(result.active_records, 'active decision')}; "
            f"candidates: {candidates}"
        )
        if not comparison.accepted:
            _print(
                f"Rejected the comparison for {artifact_id} after "
                f"{_attempts(comparison.attempts)} (prompt {comparison.prompt_version}); "
                "no record was written and the Ledger lists the rejected draft. "
                "Errors of the last attempt:",
                sys.stderr,
            )
            for error in comparison.errors:
                _print(f"- {error}", sys.stderr)
            print(_billed(result))
            return EXIT_REJECTED
        target = f" of {comparison.target_id}" if comparison.target_id else ""
        print(
            f"Classified as {comparison.classification}{target} in "
            f"{_attempts(comparison.attempts)} (prompt {comparison.prompt_version}): "
            + " ".join(comparison.reason.split())
        )

    for line in _change_lines(result):
        print(line)
    print(_billed(result))
    print(f"Record: {result.record_path.as_posix()}")
    print(f"Index: {result.index_path.as_posix()}")
    return EXIT_OK


def _change_lines(result: pipeline.RecordOutcome) -> list[str]:
    record_id = result.record_id
    if result.change == "new":
        return [f"Recorded {record_id} as a new decision"]
    if result.change == "supersession":
        return [f"Recorded {record_id}, superseding {result.related_id} (now superseded)"]
    if result.change == "reaffirmation":
        added = _count(result.sources_added, "source")
        return [f"Reaffirmed {record_id} (revision {result.revision}): added {added}"]
    filled = f"filled {', '.join(result.filled)}" if result.filled else "no empty fields filled"
    lines = [f"Updated {record_id} to revision {result.revision}: {filled}"]
    if result.ignored:
        lines.append(
            f"Kept the existing {', '.join(result.ignored)} in {record_id} (the draft's "
            "wording differs; a change of substance would be a supersession)"
        )
    return lines


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
    """One detail per produced record, for example ``update DEC-0002``."""
    changes = []
    for item in entry.get("produced", []):
        change = f"{item.get('change', 'new')} {item['record_id']}"
        if "related_id" in item:
            change += f", superseding {item['related_id']}"
        changes.append(change)
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


def _billed(result: pipeline.RecordOutcome) -> str:
    """Billed units per stage that ran; "not reported" when the provider reports none."""

    def total(usage: Sequence[Usage], name: str, label: str) -> str:
        values = [getattr(item, name) for item in usage if getattr(item, name) is not None]
        return f"{label} {sum(values):,}" if values else f"{label} not reported"

    def reported(usage: Sequence[Usage], units: Sequence[tuple[str, str]]) -> str:
        """Only the units the provider reports: Rerank v5 bills input tokens, older
        models search units (tool feedback, 2026-10-25)."""
        present = [
            total(usage, name, label)
            for name, label in units
            if any(getattr(item, name) is not None for item in usage)
        ]
        return ", ".join(present) or "not reported"

    stages = [
        (
            "draft",
            total(result.draft.usage, "input_tokens", "input tokens")
            + ", "
            + total(result.draft.usage, "output_tokens", "output tokens"),
        )
    ]
    comparison = result.comparison
    if comparison is not None and comparison.compared:
        stages += [
            (
                "comparison",
                total(comparison.chat_usage, "input_tokens", "input tokens")
                + ", "
                + total(comparison.chat_usage, "output_tokens", "output tokens"),
            ),
            ("embed", total(comparison.embed_usage, "input_tokens", "input tokens")),
            (
                "rerank",
                reported(
                    comparison.rerank_usage,
                    [("input_tokens", "input tokens"), ("search_units", "search units")],
                ),
            ),
        ]
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
