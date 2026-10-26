"""Loading the versioned prompt files in ``prompts/`` (ADR-0014).

Prompt files are immutable once a record cites them: a change is a new version file. In a
wheel they are packaged as ``knowledge_automata/prompts``; in a source checkout or editable
install they are read from the repository's ``prompts/`` folder.
"""

import functools
from dataclasses import dataclass
from importlib import resources
from pathlib import Path, PurePosixPath

PROMPT_SUFFIX = ".md"


@dataclass(frozen=True)
class Prompt:
    """One prompt file. ``version`` is the file stem, for example ``decision-registrar.v1``."""

    version: str
    text: str


@functools.cache
def prompts_root() -> Path:
    """Return the folder that holds the prompt files."""
    packaged = resources.files("knowledge_automata") / "prompts"
    if packaged.is_dir():
        return Path(str(packaged))
    # Source checkout or editable install: src/knowledge_automata/core/prompts.py -> repo root.
    checkout = Path(__file__).resolve().parents[3] / "prompts"
    if checkout.is_dir():
        return checkout
    raise FileNotFoundError("Prompt files not found in the package or the source checkout")


def list_prompts() -> list[str]:
    """Return the name of every prompt file (relative, ``/`` separators, no extension)."""
    root = prompts_root()
    return sorted(
        path.relative_to(root).with_suffix("").as_posix()
        for path in root.rglob(f"*{PROMPT_SUFFIX}")
    )


def load_prompt(name: str) -> Prompt:
    """Return a prompt by its path relative to ``prompts/``, without the extension.

    For example ``project-management/decision-registrar.v1``. Line endings are read as LF.
    """
    path = PurePosixPath(name)
    if not path.parts or path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError(f"Prompt name must be relative to prompts/: {name!r}")
    file = prompts_root().joinpath(*path.parts).with_name(path.name + PROMPT_SUFFIX)
    if not file.is_file():
        raise FileNotFoundError(f"Prompt not found: {name!r}")
    return Prompt(version=path.name, text=file.read_text(encoding="utf-8"))
