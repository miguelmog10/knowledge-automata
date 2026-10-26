"""Generated Markdown views (ADR-0005, ADR-0013).

Views are generated from the JSON records and never edited by hand. Rendering is
deterministic: the same records always produce the same bytes. Paths in this module are
relative to the memory folder or to its ``views/`` folder, with ``/`` separators.
"""

import posixpath
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

VIEWS_FOLDER = "views"

_SPECIAL = re.compile(r"([\\`*_\[\]<>|])")


def escape(text: str) -> str:
    """Escape Markdown syntax in LLM text; line breaks are normalized to LF and kept."""
    return _SPECIAL.sub(r"\\\1", text.replace("\r\n", "\n").replace("\r", "\n"))


def inline(text: str) -> str:
    """Escape text for one line (a heading, a table cell or a list item)."""
    return " ".join(escape(text).split("\n"))


def blockquote(text: str) -> str:
    """Escape text as a quote: one ``> `` line per line."""
    return "\n".join(f"> {line}" if line else ">" for line in escape(text).split("\n"))


def table_row(cells: Iterable[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def relative_link(from_file: str, to_file: str) -> str:
    """Return a relative link from one file to another, both relative to the same root."""
    target = posixpath.relpath(to_file, posixpath.dirname(from_file) or ".")
    return quote(target, safe="/-._~")


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n")


@dataclass(frozen=True)
class ViewDifferences:
    """Owned view files that are missing, differ from the generator's output, or are extra."""

    missing: tuple[str, ...] = ()
    changed: tuple[str, ...] = ()
    extra: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not (self.missing or self.changed or self.extra)


def _is_owned(path: str, owned: Sequence[str]) -> bool:
    return any(path.startswith(entry) if entry.endswith("/") else path == entry for entry in owned)


def _owned_on_disk(views_dir: Path, owned: Sequence[str]) -> set[str]:
    found = set()
    for entry in owned:
        target = views_dir / entry
        if entry.endswith("/"):
            if target.is_dir():
                found |= {
                    path.relative_to(views_dir).as_posix()
                    for path in target.rglob("*.md")
                    if path.is_file()
                }
        elif target.is_file():
            found.add(entry)
    return found


def check_views(views_dir: Path, files: Mapping[str, str], owned: Sequence[str]) -> ViewDifferences:
    """Compare the generator's ``files`` with the owned files on disk, ignoring CRLF vs LF.

    ``owned`` lists file paths, and folders ending with ``/``, that the generator owns.
    """
    for path in files:
        if not _is_owned(path, owned):
            raise ValueError(f"Generated view {path!r} is not owned by the generator")
    missing, changed = [], []
    for path, content in sorted(files.items()):
        target = views_dir / path
        if not target.is_file():
            missing.append(path)
            continue
        try:
            current = normalize_newlines(target.read_bytes().decode("utf-8"))
        except UnicodeDecodeError:
            current = None
        if current != content:
            changed.append(path)
    extra = sorted(_owned_on_disk(views_dir, owned) - set(files))
    return ViewDifferences(tuple(missing), tuple(changed), tuple(extra))


def write_views(views_dir: Path, files: Mapping[str, str], owned: Sequence[str]) -> ViewDifferences:
    """Write missing and changed files (UTF-8, LF) and delete stale owned ``.md`` files.

    Returns what was different before writing.
    """
    differences = check_views(views_dir, files, owned)
    for path in differences.missing + differences.changed:
        target = views_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8", newline="\n") as file:
            file.write(files[path])
    for path in differences.extra:
        (views_dir / path).unlink()
    return differences
