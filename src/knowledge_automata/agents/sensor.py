"""The Sensor (intake and input guardrail): deterministic checks on arriving artifacts.

Every artifact enters the Artifact Ledger through the Sensor (ADR-0006, ADR-0015). It
hashes the file, runs its checks in a fixed order and builds the Ledger entry with the
outcome; it also decides whether a quarantined artifact can be released by the Operator
(human in the loop). Everything is code: no LLM call. Like every agent it touches no
files; the pipeline reads the file, finds duplicates and stores the copy and the entry.

The file's text is untrusted data. Only the title (a heading or the file name) is taken
from it; reasons are written by code.
"""

import hashlib
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from knowledge_automata.agents.registrar import CLOSING_TAG
from knowledge_automata.core.ledger import ARTIFACTS_FOLDER, new_entry, transition

MAX_BYTES_VARIABLE = "KA_SENSOR_MAX_BYTES"
DEFAULT_MAX_BYTES = 100_000
MAX_TITLE = 200
MAX_SLUG = 60
MAX_SOURCE_NAME = 255
MAX_REASON = 500
MEDIA_TYPES = {".md": "text/markdown", ".markdown": "text/markdown", ".txt": "text/plain"}

_BOM = b"\xef\xbb\xbf"
_NOT_SLUG = re.compile(r"[^a-z0-9]+")
_ID_PREFIX = re.compile(r"^art-[0-9]+-")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", re.ASCII)


class SensorConfigError(Exception):
    """A Sensor setting in the environment is invalid."""


class SensorInputError(Exception):
    """Input the user must fix: a bad argument, a file name or a status that does not fit."""


def max_bytes_from_env(env: Mapping[str, str] = os.environ) -> int:
    """Return ``KA_SENSOR_MAX_BYTES``, a positive whole number; unset or empty is the default."""
    raw = env.get(MAX_BYTES_VARIABLE, "").strip()
    if not raw:
        return DEFAULT_MAX_BYTES
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value < 1:
        raise SensorConfigError(
            f"{MAX_BYTES_VARIABLE} must be a positive whole number, got {raw!r}"
        )
    return value


def content_hash(raw: bytes) -> str:
    """SHA-256 of the bytes without a leading UTF-8 BOM and with line endings as LF."""
    if raw.startswith(_BOM):
        raw = raw[len(_BOM) :]
    raw = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def media_type(name: str) -> str | None:
    """Return the media type for a supported extension (any case), otherwise ``None``."""
    return MEDIA_TYPES.get(Path(name).suffix.lower())


def decode(raw: bytes) -> str | None:
    """Return the text as UTF-8 without a BOM, or ``None`` if it does not decode."""
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def title(name: str, text: str | None, media: str | None) -> str:
    """The first ``# `` heading of a Markdown file, otherwise the file name stem."""
    if media == "text/markdown" and text is not None:
        for line in normalize_newlines(text).split("\n"):
            if line.startswith("# ") and line[2:].strip():
                return line[2:].strip()[:MAX_TITLE]
    return (Path(name).stem or name)[:MAX_TITLE]


def slug(name: str) -> str:
    """Lowercase stem, runs outside ``a-z0-9`` as ``-``, no repeated ``art-<digits>-`` prefix."""
    value = _NOT_SLUG.sub("-", Path(name).stem.lower()).strip("-")
    value = _ID_PREFIX.sub("", value)
    value = value[:MAX_SLUG].strip("-")
    return value or "artifact"


def copy_name(artifact_id: str, name: str) -> str:
    """The copy's file name: ``<ID>-<slug><extension, lowercased>``."""
    return f"{artifact_id}-{slug(name)}{Path(name).suffix.lower()}"


def check_artifact_date(artifact_date: str | None) -> None:
    if artifact_date is None:
        return
    try:
        if not _DATE.fullmatch(artifact_date):
            raise ValueError
        date.fromisoformat(artifact_date)
    except ValueError:
        raise SensorInputError(
            f"--artifact-date must be a real date as YYYY-MM-DD, got {artifact_date!r}"
        ) from None


def check_source_name(name: str) -> None:
    """The Ledger keeps the file name only: 1 to 255 characters, no slashes."""
    if not name or len(name) > MAX_SOURCE_NAME or "/" in name or "\\" in name:
        raise SensorInputError(
            f"The file name must be 1 to {MAX_SOURCE_NAME} characters without slashes: {name!r}"
        )


@dataclass(frozen=True)
class CheckResult:
    status: str  # accepted, quarantined or rejected
    check: str | None = None
    reason: str | None = None
    text: str | None = None  # the decoded text, when it decodes


def run_checks(raw: bytes, name: str, *, max_bytes: int | None) -> CheckResult:
    """Run checks 3 to 8 in order; the first that fails decides. ``None`` skips the size."""
    if media_type(name) is None:
        return CheckResult(
            "rejected", "unsupported-format", "Only .md, .markdown and .txt files are supported"
        )
    if not raw:
        return CheckResult("rejected", "empty", "The file is empty")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        return CheckResult(
            "quarantined", "encoding", f"Not valid UTF-8 text (first bad byte at {error.start:,})"
        )
    if not text.strip():
        return CheckResult("rejected", "empty", "The file holds only whitespace", text)
    if max_bytes is not None and len(raw) > max_bytes:
        return CheckResult(
            "quarantined",
            "oversized",
            f"{len(raw):,} bytes; the limit is {max_bytes:,} ({MAX_BYTES_VARIABLE})",
            text,
        )
    if CLOSING_TAG.search(text):
        return CheckResult(
            "quarantined",
            "delimiter",
            "Contains '</artifact', which could close the artifact delimiter early",
            text,
        )
    return CheckResult("accepted", text=text)


def assess(
    *,
    raw: bytes,
    name: str,
    artifact_id: str,
    artifact_date: str | None,
    same_name_as: Sequence[str],
    max_bytes: int,
    now: datetime,
) -> dict[str, Any]:
    """Return the new Ledger entry for a file that is not a duplicate: ``received``, then
    the outcome of the checks, both by ``sensor`` at ``now``.

    ``stored_path`` is set when a copy must be kept (accepted and quarantined).
    """
    check_artifact_date(artifact_date)
    check_source_name(name)
    result = run_checks(raw, name, max_bytes=max_bytes)
    media = media_type(name)
    kept = result.status != "rejected"
    entry = new_entry(
        artifact_id=artifact_id,
        title=title(name, result.text, media),
        source_name=name,
        size_bytes=len(raw),
        content_hash=content_hash(raw),
        at=now,
        artifact_date=artifact_date,
        media_type=media,
        stored_path=f"{ARTIFACTS_FOLDER}/{copy_name(artifact_id, name)}" if kept else None,
        same_name_as=same_name_as,
    )
    return transition(
        entry, to=result.status, by="sensor", at=now, check=result.check, reason=result.reason
    )


def check_reason(reason: str) -> str:
    """Return the Operator's reason without surrounding whitespace, 1 to 500 characters."""
    reason = reason.strip()
    if not reason or len(reason) > MAX_REASON:
        raise SensorInputError(f"--reason must be 1 to {MAX_REASON} characters")
    return reason


def check_releasable(entry: Mapping[str, Any]) -> None:
    if entry["status"] != "quarantined":
        raise SensorInputError(
            f"{entry['id']} is {entry['status']}; only a quarantined artifact can be released"
        )


@dataclass(frozen=True)
class ReleaseOutcome:
    released: bool
    entry: dict[str, Any]  # the accepted entry, or the unchanged one when a check still fails
    check: str | None = None
    reason: str | None = None


def release(entry: Mapping[str, Any], raw: bytes, *, reason: str, now: datetime) -> ReleaseOutcome:
    """The Operator's manual release of a quarantined artifact, given its stored copy.

    Reruns checks 3 to 8 without the size limit. If they pass, the entry moves to
    ``accepted`` by ``operator`` with ``reason``; otherwise it is returned unchanged with
    the check that still fails.
    """
    reason = check_reason(reason)
    check_releasable(entry)
    result = run_checks(raw, entry["stored_path"], max_bytes=None)
    if result.status != "accepted":
        return ReleaseOutcome(False, dict(entry), result.check, result.reason)
    released = transition(entry, to="accepted", by="operator", at=now, reason=reason)
    return ReleaseOutcome(True, released)
