"""One JSON file per record, inside a memory folder (ADR-0013).

Layout: ``<memory>/registers/<register>/<ID>.json``. Every record is validated before it
is written and when it is read. One writing process at a time is assumed. ``OSError`` from
the file system is not caught here; callers report it with the path.
"""

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from knowledge_automata.core.registers import RegisterSpec
from knowledge_automata.core.validation import validate_record

REGISTERS_FOLDER = "registers"


class RecordStoreError(Exception):
    """A record cannot be written, or a stored file is not a valid record."""


def format_record(record: dict[str, Any]) -> str:
    """Return the deterministic file content of a record: two-space indent, keys as given."""
    return json.dumps(record, indent=2, ensure_ascii=False) + "\n"


class RecordStore:
    def __init__(self, memory: Path | str) -> None:
        self.memory = Path(memory)

    def register_dir(self, spec: RegisterSpec) -> Path:
        return self.memory / REGISTERS_FOLDER / spec.name

    def _files(self, spec: RegisterSpec) -> list[tuple[int, Path]]:
        """Return ``(sequence, path)`` for every record file, sorted by sequence."""
        folder = self.register_dir(spec)
        if not folder.is_dir():
            return []
        pattern = re.compile(rf"{re.escape(spec.id_prefix)}-([0-9]{{4,}})\.json", re.ASCII)
        files = []
        for path in folder.iterdir():
            match = pattern.fullmatch(path.name)
            if match is None or not path.is_file():
                raise RecordStoreError(
                    f"Unexpected entry in register folder {folder}: {path.name!r} "
                    f"(expected {spec.id_prefix}-<digits>.json files only)"
                )
            files.append((int(match.group(1)), path))
        return sorted(files)

    def next_id(self, spec: RegisterSpec) -> str:
        """Return the highest existing sequence plus one, at least four digits."""
        files = self._files(spec)
        sequence = files[-1][0] + 1 if files else 1
        return f"{spec.id_prefix}-{sequence:04d}"

    def save_new(self, record: dict[str, Any], spec: RegisterSpec) -> Path:
        """Validate and write a new record; never overwrite an existing file."""
        result = validate_record(record, spec)
        if not result.ok:
            raise RecordStoreError(
                f"Record {record.get('id')!r} is invalid and was not written:\n"
                + "\n".join(f"- {error}" for error in result.errors)
            )
        folder = self.register_dir(spec)
        path = folder / f"{record['id']}.json"
        if path.exists():
            raise RecordStoreError(f"Record file already exists, not overwritten: {path}")
        folder.mkdir(parents=True, exist_ok=True)

        descriptor, temporary = tempfile.mkstemp(
            dir=folder, prefix=f".{record['id']}.", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
                file.write(format_record(record))
            os.replace(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
        return path

    def load(self, path: Path, spec: RegisterSpec) -> dict[str, Any]:
        try:
            with path.open(encoding="utf-8") as file:
                record = json.load(file)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise RecordStoreError(f"{path} is not valid UTF-8 JSON: {error}") from None
        result = validate_record(record, spec)
        if not result.ok:
            raise RecordStoreError(
                f"{path} is not a valid {spec.name} record:\n"
                + "\n".join(f"- {error}" for error in result.errors)
            )
        if record["id"] != path.stem:
            raise RecordStoreError(f"{path} holds record {record['id']!r}, not {path.stem!r}")
        return record

    def load_all(self, spec: RegisterSpec) -> list[dict[str, Any]]:
        """Return every record in the register, sorted by ID, each validated."""
        return [self.load(path, spec) for _, path in self._files(spec)]

    def ids_citing(self, spec: RegisterSpec, artifact_id: str) -> list[str]:
        """Return the IDs of records with at least one source from ``artifact_id``."""
        return [
            record["id"]
            for record in self.load_all(spec)
            if any(source["artifact_id"] == artifact_id for source in record["sources"])
        ]
