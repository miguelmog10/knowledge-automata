"""The ``knowledge-automata`` command line.

Exit codes: 0 success; 1 record rejected, or views differ under ``--check``; 2 usage,
configuration or file problem; 3 provider error. Output never includes the settings, the
API key, prompts or artifact text.
"""

import argparse
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from knowledge_automata import pipeline
from knowledge_automata.llm import (
    ChatModel,
    LLMConfigError,
    LLMError,
    LLMRateLimitError,
    LLMSettings,
    Usage,
    build_llm,
)
from knowledge_automata.storage.record_store import RecordStoreError
from knowledge_automata.views.markdown import VIEWS_FOLDER, ViewDifferences

EXIT_OK = 0
EXIT_REJECTED = 1
EXIT_USAGE = 2
EXIT_PROVIDER = 3


def utc_now() -> datetime:
    return datetime.now(UTC)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="knowledge-automata",
        description="Institutional memory for groups that make decisions together.",
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    record = commands.add_parser(
        "record-decision",
        help="Record the most significant decision in one artifact.",
        description=(
            "Draft one decision record from an artifact with the Decision Registrar, "
            "validate it, store it and regenerate the decision log views. Until the "
            "Artifact Ledger exists, the artifact ID and date are passed by hand."
        ),
    )
    record.add_argument("artifact", type=Path, metavar="ARTIFACT", help="artifact file")
    record.add_argument("--artifact-id", required=True, help="for example ART-0001")
    record.add_argument("--artifact-date", help="artifact date as YYYY-MM-DD")
    _memory_argument(record)

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
    build: Callable[[LLMSettings], ChatModel] = build_llm,
    clock: Callable[[], datetime] = utc_now,
) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exit_:
        return exit_.code if isinstance(exit_.code, int) else EXIT_USAGE
    try:
        if args.command == "record-decision":
            return _record_decision(args, build, clock)
        return _views(args)
    except (pipeline.InputError, RecordStoreError) as error:
        return _fail(str(error), EXIT_USAGE)
    except OSError as error:
        return _fail(_describe_os_error(error), EXIT_USAGE)
    except LLMConfigError as error:
        return _fail(str(error), EXIT_USAGE)
    except LLMRateLimitError as error:
        hint = " The limit resets next month." if error.monthly_cap else ""
        return _fail(f"Provider error (LLMRateLimitError): {error}{hint}", EXIT_PROVIDER)
    except LLMError as error:
        return _fail(f"Provider error ({type(error).__name__}): {error}", EXIT_PROVIDER)


def _record_decision(
    args: argparse.Namespace,
    build: Callable[[LLMSettings], ChatModel],
    clock: Callable[[], datetime],
) -> int:
    # Checked before building the LLM, so bad arguments never need an API key.
    pipeline.validate_artifact_arguments(args.artifact_id, args.artifact_date)
    settings = pipeline.decision_registrar_settings(LLMSettings.from_env())
    llm = build(settings)
    result = pipeline.record_decision(
        artifact_path=args.artifact,
        artifact_id=args.artifact_id,
        artifact_date=args.artifact_date,
        memory=args.memory,
        llm=llm,
        now=clock(),
    )
    draft = result.draft
    attempts = f"{draft.attempts} attempt{'s' if draft.attempts != 1 else ''}"
    if result.run_id:
        print(f"Run ID: {result.run_id}")

    if not result.accepted:
        _print(
            f"Rejected the draft from {args.artifact_id} after {attempts} "
            f"(prompt {draft.prompt_version}, thinking {settings.chat_thinking}); "
            "nothing was written. Errors of the last attempt:",
            sys.stderr,
        )
        for error in draft.errors:
            _print(f"- {error}", sys.stderr)
        print(_billed(draft.usage))
        return EXIT_REJECTED

    print(
        f"Recorded {result.record_id} from {args.artifact_id} in {attempts} "
        f"(model {draft.model}, prompt {draft.prompt_version}, "
        f"thinking {settings.chat_thinking})"
    )
    print(_billed(draft.usage))
    print(f"Record: {result.record_path.as_posix()}")
    print(f"Index: {result.index_path.as_posix()}")
    return EXIT_OK


def _views(args: argparse.Namespace) -> int:
    memory: Path = args.memory
    if not memory.is_dir():
        return _fail(f"Memory folder not found: {memory}", EXIT_USAGE)
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


def _billed(usage: Sequence[Usage]) -> str:
    def total(name: str) -> str:
        values = [getattr(item, name) for item in usage if getattr(item, name) is not None]
        return f"{sum(values):,}" if values else "not reported"

    return f"Billed tokens: {total('input_tokens')} input, {total('output_tokens')} output"


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
