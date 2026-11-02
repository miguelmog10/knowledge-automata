"""Register specifications: what code needs to know about one register (ADR-0011)."""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

SemanticCheck = Callable[[Mapping[str, Any]], list[str]]
"""Takes schema-valid content and returns error messages (an empty list when it passes)."""

CLASSIFICATIONS: frozenset[str] = frozenset({"new", "update", "reaffirmation", "supersession"})
"""Every classification the Comparator (reconciliation) can return."""

_ID_PREFIX = re.compile(r"^[A-Z]{3}$")
_REGISTER_NAME = re.compile(r"^[a-z][a-z0-9-]*$")


@dataclass(frozen=True)
class RegisterSpec:
    """One register, for example the decision log.

    ``content_schema`` is a path relative to ``schemas/``, for example
    ``project-management/decision.v1.json``. ``definition`` names the prompt file that says
    what belongs in the register, relative to ``prompts/`` and without the extension, for
    example ``project-management/definitions/decision-log.v1`` (ADR-0018).
    """

    name: str
    id_prefix: str
    content_schema: str
    allowed_classifications: frozenset[str]
    semantic_checks: tuple[SemanticCheck, ...] = ()
    definition: str | None = None

    def __post_init__(self) -> None:
        if not _REGISTER_NAME.match(self.name):
            raise ValueError(f"Invalid register name: {self.name!r}")
        if not _ID_PREFIX.match(self.id_prefix):
            raise ValueError(f"ID prefix must be three capital letters: {self.id_prefix!r}")
        unknown = self.allowed_classifications - CLASSIFICATIONS
        if unknown:
            raise ValueError(f"Unknown classifications: {sorted(unknown)}")
        if "new" not in self.allowed_classifications:
            raise ValueError("Every register must allow the 'new' classification")
