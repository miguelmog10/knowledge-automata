"""Deterministic JSON files shared by every store (ADR-0013).

Content is UTF-8 with LF line endings, two-space indentation, keys in the order given (the
callers order them like their schema) and a trailing newline, so diffs show only real
changes. Writes go to a temporary file in the same folder, then ``os.replace``, so a reader
never sees a half-written file. One writing process at a time is assumed.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def format_json(data: Any) -> str:
    """Return the deterministic file content for ``data``."""
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def write_json_atomic(path: Path, data: Any, *, overwrite: bool) -> None:
    """Write ``data`` to ``path`` through a temporary file, creating the folder if needed.

    With ``overwrite=False`` an existing file raises ``FileExistsError`` and is left alone.
    No temporary file is left behind when writing fails.
    """
    if not overwrite and path.exists():
        raise FileExistsError(17, "File already exists, not overwritten", str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.stem}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
            file.write(format_json(data))
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
