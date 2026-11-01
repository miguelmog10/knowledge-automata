"""The Governor (orchestrator): which items in an artifact belong in which register (ADR-0018).

The Governor reads an accepted artifact once and returns, for each item, the register it
belongs to and one to five evidence quotes. Its system prompt is built from each register's
definition. Code checks the reply with ``validate_work_orders`` and retries once with the
errors (``agents/checked_chat.py``, shared with the Registrars), then builds the work
orders: sorted by where they first appear, numbered, and labelled from verified quotes.
This module never writes files and never routes or drafts; the pipeline does.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath

from knowledge_automata.agents.checked_chat import checked_chat
from knowledge_automata.agents.checked_chat import retry_version as _retry_version
from knowledge_automata.agents.registrar import check_artifact, user_message
from knowledge_automata.core.prompts import ERRORS_PLACEHOLDER, Prompt, load_prompt
from knowledge_automata.core.registers import RegisterSpec
from knowledge_automata.core.schemas import governor_schema
from knowledge_automata.core.validation import validate_work_orders
from knowledge_automata.core.work_orders import WorkOrder, build_work_orders
from knowledge_automata.llm import ChatModel, Usage

REGISTERS_PLACEHOLDER = "{registers}"


def _definition_version(spec: RegisterSpec) -> str | None:
    return PurePosixPath(spec.definition).name if spec.definition is not None else None


@dataclass(frozen=True)
class Governor:
    agent: str  # used in CallContext and events: "governor"
    prompt: Prompt
    retry_prompt: Prompt
    registers: tuple[tuple[RegisterSpec, Prompt], ...]  # each spec with its loaded definition
    max_attempts: int = 2

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError(f"max_attempts must be at least 1, got {self.max_attempts}")
        if ERRORS_PLACEHOLDER not in self.retry_prompt.text:
            raise ValueError(f"The retry prompt must contain {ERRORS_PLACEHOLDER}")
        if REGISTERS_PLACEHOLDER not in self.prompt.text:
            raise ValueError(f"The Governor prompt must contain {REGISTERS_PLACEHOLDER}")
        if not self.registers:
            raise ValueError("The Governor needs at least one register")
        names = [spec.name for spec, _ in self.registers]
        if len(set(names)) != len(names):
            raise ValueError(f"Each register may be listed once: {names}")
        for spec, definition in self.registers:
            if spec.definition is None:
                raise ValueError(f"Register {spec.name!r} has no definition")
            if definition.version != _definition_version(spec):
                raise ValueError(
                    f"Register {spec.name!r} names definition {spec.definition!r}, "
                    f"but was given {definition.version!r}"
                )

    @property
    def specs(self) -> tuple[RegisterSpec, ...]:
        return tuple(spec for spec, _ in self.registers)

    @property
    def definition_versions(self) -> tuple[str, ...]:
        return tuple(definition.version for _, definition in self.registers)

    @property
    def retry_version(self) -> str:
        return _retry_version(self.prompt, self.retry_prompt)

    def system_text(self) -> str:
        """The prompt with ``{registers}`` replaced by one block per register, in order."""
        blocks = "\n\n".join(
            f"### {spec.name}\n\n{definition.text.strip()}" for spec, definition in self.registers
        )
        # str.replace, not str.format: definitions may contain braces.
        return self.prompt.text.replace(REGISTERS_PLACEHOLDER, blocks)


def load_register_definitions(
    specs: Iterable[RegisterSpec],
) -> tuple[tuple[RegisterSpec, Prompt], ...]:
    """Pair each register with its definition prompt, loaded from ``prompts/``."""
    pairs = []
    for spec in specs:
        if spec.definition is None:
            raise ValueError(f"Register {spec.name!r} has no definition")
        pairs.append((spec, load_prompt(spec.definition)))
    return tuple(pairs)


@dataclass(frozen=True)
class GovernorOutcome:
    work_orders: tuple[WorkOrder, ...] | None  # sorted and numbered; None when rejected
    errors: tuple[str, ...]  # errors of the last attempt; empty when accepted
    attempts: int
    model: str | None  # model that produced the accepted reply
    prompt_version: str  # of the accepted attempt, or of the last attempt
    definitions: tuple[str, ...]  # definition versions, in register order
    usage: tuple[Usage, ...]  # one per billed call, including unusable responses
    error_type: str | None = None  # exception class name when the last response was unusable

    @property
    def accepted(self) -> bool:
        return self.work_orders is not None


def find_work_orders(
    governor: Governor, llm: ChatModel, artifact_text: str, *, artifact_id: str
) -> GovernorOutcome:
    """Find the work orders in an artifact, with at most ``max_attempts`` calls.

    An accepted reply with no items gives no work orders, which is a valid answer.
    ``LLMResponseError`` counts as a failed attempt; every other ``LLMError`` propagates
    unchanged.
    """
    check_artifact(artifact_text)
    specs = governor.specs
    reply = checked_chat(
        llm,
        agent=governor.agent,
        artifact_id=artifact_id,
        prompt=Prompt(governor.prompt.version, governor.system_text()),
        retry_prompt=governor.retry_prompt,
        user=user_message(artifact_text),
        schema=governor_schema(specs),
        check=lambda data: validate_work_orders(data, specs, artifact_text),
        max_attempts=governor.max_attempts,
    )
    work_orders = (
        build_work_orders(reply.data["items"], artifact_text) if reply.data is not None else None
    )
    return GovernorOutcome(
        work_orders=work_orders,
        errors=reply.errors,
        attempts=reply.attempts,
        model=reply.model,
        prompt_version=reply.prompt_version,
        definitions=governor.definition_versions,
        usage=reply.usage,
        error_type=reply.error_type,
    )
