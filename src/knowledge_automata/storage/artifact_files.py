"""Read-only copies of artifacts inside a memory folder (ADR-0015).

Layout: ``<memory>/artifacts/<ID>-<slug><ext>``. A copy holds the original bytes,
unchanged. It is created once and never overwritten or modified. ``OSError`` from the file
system is not caught here; callers report it with the path.
"""

import re
from pathlib import Path

from knowledge_automata.core.ledger import ARTIFACTS_FOLDER

_FILE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*", re.ASCII)


class ArtifactPathError(ValueError):
    """A stored path that does not name a file directly inside ``artifacts/``."""


def resolve(memory: Path, stored: str) -> Path:
    """Return the file a ``stored_path`` points at, refusing anything outside ``artifacts/``."""
    folder, _, name = stored.partition("/")
    if folder != ARTIFACTS_FOLDER or not _FILE_NAME.fullmatch(name):
        raise ArtifactPathError(f"Not a path inside {ARTIFACTS_FOLDER}/: {stored!r}")
    return Path(memory) / ARTIFACTS_FOLDER / name


def write_copy(memory: Path, stored: str, raw: bytes) -> Path:
    """Create the copy with exactly ``raw``; raises ``FileExistsError`` if it exists."""
    path = resolve(memory, stored)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as file:
            file.write(raw)
    except FileExistsError:
        raise
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def read_copy(memory: Path, stored: str) -> bytes:
    """Return the bytes of the copy at ``stored``."""
    return resolve(memory, stored).read_bytes()
