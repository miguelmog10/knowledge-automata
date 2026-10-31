"""One JSON file per record, inside a memory folder (ADR-0013).

Layout: ``<memory>/registers/<register>/<ID>.json``. Every record is validated before it
is written and when it is read. A new record is written once with ``save_new``; an
existing record changes only through ``save_revision``, one revision at a time. One
writing process at a time is assumed. ``OSError`` from the file system is not caught
here; callers report it with the path.
"""

import json
import re
from pathlib import Path
from typing import Any

from knowledge_automata.core.registers import RegisterSpec
from knowledge_automata.core.validation import revision_errors, validate_record
from knowledge_automata.storage.json_files import write_json_atomic

REGISTERS_FOLDER = "registers"


class RecordStoreError(Exception):
    """A record cannot be written, or a stored file is not a valid record."""


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
        write_json_atomic(path, record, overwrite=False)
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

    def load_active(self, spec: RegisterSpec) -> list[dict[str, Any]]:
        """Return the register's ``active`` records, sorted by ID, each validated."""
        return [record for record in self.load_all(spec) if record["record_status"] == "active"]

    def save_revision(self, old: dict[str, Any], new: dict[str, Any], spec: RegisterSpec) -> Path:
        """Replace ``old`` with ``new``, its next revision (ADR-0013 amendment).

        Refused unless ``new`` is valid, the stored file still equals ``old`` (no lost
        update) and ``new`` follows ``revision_errors``' rules. Nothing is written on refusal.
        """
        result = validate_record(new, spec)
        if not result.ok:
            raise RecordStoreError(
                f"Record {new.get('id')!r} is invalid and was not written:\n"
                + "\n".join(f"- {error}" for error in result.errors)
            )
        path = self.register_dir(spec) / f"{old['id']}.json"
        if not path.is_file() or self.load(path, spec) != old:
            raise RecordStoreError(
                f"{old['id']} changed in the register since it was read; nothing was written"
            )
        errors = revision_errors(old, new)
        if errors:
            raise RecordStoreError(
                f"Record {old['id']}: not the next revision, nothing was written:\n"
                + "\n".join(f"- {error}" for error in errors)
            )
        write_json_atomic(path, new, overwrite=True)
        return path

    def ids_citing(self, spec: RegisterSpec, artifact_id: str) -> list[str]:
        """Return the IDs of records with at least one source from ``artifact_id``."""
        return [
            record["id"]
            for record in self.load_all(spec)
            if any(source["artifact_id"] == artifact_id for source in record["sources"])
        ]
