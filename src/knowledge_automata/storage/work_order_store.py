"""One work orders file per artifact, inside a memory folder (ADR-0018).

Layout: ``<memory>/work-orders/<ID>.json``, in the same deterministic format as records
(ADR-0013). Every file is validated before it is written and when it is read. A file is
written once, when the Governor's (orchestrator's) reply is accepted, then changes only
through ``save_progress``, one order's result at a time. One writing process at a time is
assumed. ``OSError`` from the file system is not caught here; callers report it with the
path.
"""

import json
from pathlib import Path
from typing import Any

from knowledge_automata.core.validation import validate_work_orders_file
from knowledge_automata.storage.json_files import write_json_atomic
from knowledge_automata.storage.ledger_store import ARTIFACT_ID

WORK_ORDERS_FOLDER = "work-orders"
_CHANGING_FIELDS = frozenset({"updated_at", "orders"})
_CHANGING_ORDER_FIELDS = frozenset({"state", "produced", "rejected"})


class WorkOrderStoreError(Exception):
    """A work orders file cannot be written, or a stored file is not valid."""


def _invalid(prefix: str, errors: tuple[str, ...]) -> WorkOrderStoreError:
    return WorkOrderStoreError(prefix + "\n" + "\n".join(f"- {error}" for error in errors))


def _order_change_problem(old: dict[str, Any], new: dict[str, Any]) -> str | None:
    number = old["number"]
    changed = sorted(
        key
        for key in old.keys() | new.keys()
        if key not in _CHANGING_ORDER_FIELDS and old.get(key) != new.get(key)
    )
    if changed:
        return f"work order {number}: cannot change {', '.join(changed)}"
    if old == new:
        return None
    if old["state"] not in {"pending", "rejected"}:
        return f"work order {number} is {old['state']}; it never changes"
    if new["state"] not in {"recorded", "rejected"}:
        return f"work order {number}: cannot go from {old['state']} to {new['state']}"
    old_rejected, new_rejected = old["rejected"], new["rejected"]
    if new_rejected[: len(old_rejected)] != old_rejected:
        return f"work order {number}: the new rejected list must keep the old one unchanged"
    return None


class WorkOrderStore:
    def __init__(self, memory: Path | str) -> None:
        self.memory = Path(memory)

    @property
    def folder(self) -> Path:
        return self.memory / WORK_ORDERS_FOLDER

    def path(self, artifact_id: str) -> Path:
        if not ARTIFACT_ID.fullmatch(artifact_id):
            raise WorkOrderStoreError(f"Not an artifact ID: {artifact_id!r} (expected ART-0001)")
        return self.folder / f"{artifact_id}.json"

    def exists(self, artifact_id: str) -> bool:
        return self.path(artifact_id).is_file()

    def load(self, artifact_id: str) -> dict[str, Any] | None:
        """Return the artifact's validated work orders file, or ``None`` if it has none."""
        path = self.path(artifact_id)
        if not path.is_file():
            return None
        try:
            with path.open(encoding="utf-8") as file:
                data = json.load(file)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise WorkOrderStoreError(f"{path} is not valid UTF-8 JSON: {error}") from None
        result = validate_work_orders_file(data)
        if not result.ok:
            raise _invalid(f"{path} is not a valid work orders file:", result.errors)
        if data["artifact_id"] != artifact_id:
            raise WorkOrderStoreError(
                f"{path} holds the work orders of {data['artifact_id']!r}, not {artifact_id!r}"
            )
        return data

    def save_new(self, data: dict[str, Any]) -> Path:
        """Validate and write a new file; never overwrite an existing one."""
        self._validate(data)
        path = self.path(data["artifact_id"])
        try:
            write_json_atomic(path, data, overwrite=False)
        except FileExistsError:
            raise WorkOrderStoreError(
                f"Work orders file already exists, not overwritten: {path}"
            ) from None
        return path

    def save_progress(self, old: dict[str, Any], new: dict[str, Any]) -> Path:
        """Replace ``old`` with ``new``, the same file with more order results.

        Refused unless the stored file still equals ``old`` (no lost update) and the only
        changes are ``updated_at`` and orders going from ``pending`` or ``rejected`` to
        ``recorded`` or ``rejected``, each keeping its earlier rejected items at the start
        of its list. ``recorded`` and ``not-routed`` orders never change.
        """
        self._validate(new)
        artifact_id = old["artifact_id"]
        if new["artifact_id"] != artifact_id:
            raise WorkOrderStoreError(
                f"Cannot replace the work orders of {artifact_id} with {new['artifact_id']}'s"
            )
        if self.load(artifact_id) != old:
            raise WorkOrderStoreError(
                f"The work orders file of {artifact_id} changed since it was read; "
                "nothing was written"
            )
        changed = sorted(
            key
            for key in old.keys() | new.keys()
            if key not in _CHANGING_FIELDS and old.get(key) != new.get(key)
        )
        if changed:
            raise WorkOrderStoreError(
                f"{artifact_id}: a work orders file cannot change {', '.join(changed)}"
            )
        if len(new["orders"]) != len(old["orders"]):
            raise WorkOrderStoreError(f"{artifact_id}: work orders cannot be added or removed")
        for old_order, new_order in zip(old["orders"], new["orders"], strict=True):
            problem = _order_change_problem(old_order, new_order)
            if problem is not None:
                raise WorkOrderStoreError(f"{artifact_id}: {problem}")
        path = self.path(artifact_id)
        write_json_atomic(path, new, overwrite=True)
        return path

    def _validate(self, data: dict[str, Any]) -> None:
        result = validate_work_orders_file(data)
        if not result.ok:
            raise _invalid(
                f"The work orders file of {data.get('artifact_id')!r} is invalid and was not "
                "written:",
                result.errors,
            )
