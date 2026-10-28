"""Loading the JSON Schema files in ``schemas/`` and building draft schemas (ADR-0011).

The schema files are the single source of truth. In a wheel they are packaged as
``knowledge_automata/schemas``; in a source checkout or editable install they are read
from the repository's ``schemas/`` folder.
"""

import copy
import functools
import json
from importlib import resources
from pathlib import Path, PurePosixPath
from typing import Any

from knowledge_automata.core.registers import RegisterSpec

DRAFT_SCHEMA = "core/draft.v1.json"
LEDGER_ENTRY_SCHEMA = "core/ledger-entry.v1.json"
LLM_EVENT_SCHEMA = "core/llm-event.v1.json"
RECONCILIATION_SCHEMA = "core/reconciliation.v1.json"
RECORD_SCHEMA = "core/record.v1.json"


@functools.cache
def schemas_root() -> Path:
    """Return the folder that holds the schema files."""
    packaged = resources.files("knowledge_automata") / "schemas"
    if packaged.is_dir():
        return Path(str(packaged))
    # Source checkout or editable install: src/knowledge_automata/core/schemas.py -> repo root.
    checkout = Path(__file__).resolve().parents[3] / "schemas"
    if checkout.is_dir():
        return checkout
    raise FileNotFoundError("Schema files not found in the package or the source checkout")


def list_schemas() -> list[str]:
    """Return the relative path of every schema file, sorted, with ``/`` separators."""
    root = schemas_root()
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*.json"))


@functools.cache
def _load(relative_path: str) -> dict[str, Any]:
    path = PurePosixPath(relative_path)
    if not path.parts or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Schema path must be relative to schemas/: {relative_path!r}")
    with schemas_root().joinpath(*path.parts).open(encoding="utf-8") as file:
        return json.load(file)


def load_schema(relative_path: str) -> dict[str, Any]:
    """Return a schema by its path relative to ``schemas/``.

    Files are read once and cached; each call returns a deep copy, so callers may modify it.
    """
    return copy.deepcopy(_load(relative_path))


def draft_schema(spec: RegisterSpec) -> dict[str, Any]:
    """Return the Registrar draft schema with the register's content schema inlined.

    The content schema is inlined rather than referenced, because LLM providers may not
    resolve ``$ref``.
    """
    schema = load_schema(DRAFT_SCHEMA)
    schema["properties"]["content"] = load_schema(spec.content_schema)
    return schema


def schema_version(spec: RegisterSpec) -> str:
    """Return the ``MAJOR.MINOR`` version of the register's content schema."""
    return _load(spec.content_schema)["x-version"]


def major_version(version: str) -> int:
    """Return the major part of a ``MAJOR.MINOR`` version string."""
    return int(version.split(".", 1)[0])
