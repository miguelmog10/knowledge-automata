"""One JSON file per Artifact Ledger entry, inside a memory folder (ADR-0015).

Layout: ``<memory>/ledger/<ID>.json``, in the same deterministic format as records
(ADR-0013). Every entry is validated before it is written and when it is read. An existing
entry changes only through ``save_transition``, which appends to its history. One writing
process at a time is assumed. ``OSError`` from the file system is not caught here; callers
report it with the path.
"""

import json
import re
from pathlib import Path
from typing import Any

from knowledge_automata.core.ledger import SCHEMA_VERSION
from knowledge_automata.core.schemas import major_version
from knowledge_automata.core.validation import validate_ledger_entry
from knowledge_automata.storage.json_files import write_json_atomic

LEDGER_FOLDER = "ledger"
ARTIFACT_ID = re.compile(r"ART-[0-9]{4,}", re.ASCII)
_ENTRY_FILE = re.compile(r"ART-([0-9]{4,})\.json", re.ASCII)

# The only fields a status change may touch; everything else describes what arrived.
_CHANGING_FIELDS = frozenset({"status", "updated_at", "produced", "rejected", "history"})


class LedgerStoreError(Exception):
    """An entry cannot be written, or a stored file is not a valid Ledger entry."""


class LedgerEntryNotFoundError(LedgerStoreError):
    """No Ledger entry has the requested ID."""


def _invalid(prefix: str, errors: tuple[str, ...]) -> LedgerStoreError:
    return LedgerStoreError(prefix + "\n" + "\n".join(f"- {error}" for error in errors))


class LedgerStore:
    def __init__(self, memory: Path | str) -> None:
        self.memory = Path(memory)

    @property
    def folder(self) -> Path:
        return self.memory / LEDGER_FOLDER

    def path(self, artifact_id: str) -> Path:
        if not ARTIFACT_ID.fullmatch(artifact_id):
            raise LedgerStoreError(f"Not an artifact ID: {artifact_id!r} (expected ART-0001)")
        return self.folder / f"{artifact_id}.json"

    def _files(self) -> list[tuple[int, Path]]:
        """Return ``(sequence, path)`` for every entry file, sorted by sequence."""
        if not self.folder.is_dir():
            return []
        files = []
        for path in self.folder.iterdir():
            match = _ENTRY_FILE.fullmatch(path.name)
            if match is None or not path.is_file():
                raise LedgerStoreError(
                    f"Unexpected entry in Ledger folder {self.folder}: {path.name!r} "
                    "(expected ART-<digits>.json files only)"
                )
            files.append((int(match.group(1)), path))
        return sorted(files)

    def next_id(self) -> str:
        """Return the highest existing sequence plus one, at least four digits."""
        files = self._files()
        sequence = files[-1][0] + 1 if files else 1
        return f"ART-{sequence:04d}"

    def _read(self, path: Path) -> dict[str, Any]:
        try:
            with path.open(encoding="utf-8") as file:
                entry = json.load(file)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise LedgerStoreError(f"{path} is not valid UTF-8 JSON: {error}") from None
        result = validate_ledger_entry(entry)
        if not result.ok:
            raise _invalid(f"{path} is not a valid Ledger entry:", result.errors)
        if entry["id"] != path.stem:
            raise LedgerStoreError(f"{path} holds entry {entry['id']!r}, not {path.stem!r}")
        return entry

    def load(self, artifact_id: str) -> dict[str, Any]:
        path = self.path(artifact_id)
        if not path.is_file():
            raise LedgerEntryNotFoundError(f"{artifact_id} is not in the Ledger ({self.folder})")
        return self._read(path)

    def load_all(self) -> list[dict[str, Any]]:
        """Return every entry, sorted by ID, each validated."""
        return [self._read(path) for _, path in self._files()]

    def save_new(self, entry: dict[str, Any]) -> Path:
        """Validate and write a new entry; never overwrite an existing file."""
        result = validate_ledger_entry(entry)
        if not result.ok:
            raise _invalid(
                f"Ledger entry {entry.get('id')!r} is invalid and was not written:", result.errors
            )
        path = self.path(entry["id"])
        try:
            write_json_atomic(path, entry, overwrite=False)
        except FileExistsError:
            raise LedgerStoreError(
                f"Ledger entry already exists, not overwritten: {path}"
            ) from None
        return path

    def save_transition(self, old: dict[str, Any], new: dict[str, Any]) -> Path:
        """Replace ``old`` with ``new``, a later state of the same entry.

        Refused unless the stored file still equals ``old`` (no lost update), ``old`` lists
        no records yet, ``new`` keeps ``old``'s history and rejected drafts unchanged and adds
        to the history, and only status fields change. ``schema_version`` may change only to
        the current version of the same major.
        """
        result = validate_ledger_entry(new)
        if not result.ok:
            raise _invalid(
                f"Ledger entry {new.get('id')!r} is invalid and was not written:", result.errors
            )
        artifact_id = old["id"]
        if new["id"] != artifact_id:
            raise LedgerStoreError(f"Cannot replace {artifact_id} with {new['id']}")
        if self.load(artifact_id) != old:
            raise LedgerStoreError(
                f"{artifact_id} changed in the Ledger since it was read; nothing was written"
            )
        old_history, new_history = old["history"], new["history"]
        if len(new_history) <= len(old_history) or new_history[: len(old_history)] != old_history:
            raise LedgerStoreError(
                f"{artifact_id}: the new history must keep the old one unchanged and add to it"
            )
        if old["status"] == "processed" and old["produced"]:
            raise LedgerStoreError(
                f"{artifact_id} already lists records; reprocessing it is not supported"
            )
        if new["rejected"][: len(old["rejected"])] != old["rejected"]:
            raise LedgerStoreError(
                f"{artifact_id}: the new rejected list must keep the old one unchanged"
            )
        changed = {
            key
            for key in old.keys() | new.keys()
            if key not in _CHANGING_FIELDS and old.get(key) != new.get(key)
        }
        if new["schema_version"] == SCHEMA_VERSION and major_version(
            old["schema_version"]
        ) == major_version(SCHEMA_VERSION):
            changed.discard("schema_version")
        if changed:
            raise LedgerStoreError(
                f"{artifact_id}: a status change cannot change {', '.join(sorted(changed))}"
            )
        path = self.path(artifact_id)
        write_json_atomic(path, new, overwrite=True)
        return path

    def find_by_hash(self, content_hash: str) -> dict[str, Any] | None:
        """Return the first entry, by ID, with this hash and a status other than ``rejected``."""
        for entry in self.load_all():
            if entry["content_hash"] == content_hash and entry["status"] != "rejected":
                return entry
        return None

    def ids_with_name(self, name: str) -> list[str]:
        """Return the IDs of entries whose source name is exactly ``name``, any status."""
        return [entry["id"] for entry in self.load_all() if entry["source"]["name"] == name]
