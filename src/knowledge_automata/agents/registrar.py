"""The shared Registrar (specialist record keeper) drafting loop (ADR-0014).

A Registrar is a register spec plus a versioned prompt. One loop serves every Registrar:
draft with one call, check the draft with ``validate_draft``, retry once with the errors,
then accept or reject. This module never writes files and never builds the envelope.
"""

import re
from dataclasses import dataclass
from typing import Any

from knowledge_automata.core.prompts import Prompt
from knowledge_automata.core.registers import RegisterSpec
from knowledge_automata.core.schemas import draft_schema
from knowledge_automata.core.validation import validate_draft
from knowledge_automata.llm import CallContext, ChatModel, LLMResponseError, Usage

ERRORS_PLACEHOLDER = "{errors}"
CLOSING_TAG = re.compile(r"</artifact", re.IGNORECASE)


class ArtifactRefusedError(ValueError):
    """The artifact cannot be sent to a Registrar: empty, or it could close the delimiter."""


@dataclass(frozen=True)
class Registrar:
    agent: str  # used in CallContext and events, for example "decision-registrar"
    spec: RegisterSpec
    prompt: Prompt
    retry_prompt: Prompt
    max_attempts: int = 2

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError(f"max_attempts must be at least 1, got {self.max_attempts}")
        if ERRORS_PLACEHOLDER not in self.retry_prompt.text:
            raise ValueError(f"The retry prompt must contain {ERRORS_PLACEHOLDER}")

    @property
    def retry_version(self) -> str:
        return f"{self.prompt.version}+{self.retry_prompt.version}"


@dataclass(frozen=True)
class DraftOutcome:
    draft: dict[str, Any] | None  # the accepted draft; None when rejected
    errors: tuple[str, ...]  # errors of the last attempt; empty when accepted
    attempts: int
    model: str | None  # model that produced the accepted draft
    prompt_version: str  # of the accepted attempt, or of the last attempt
    usage: tuple[Usage, ...]  # one per billed call, including unusable responses

    @property
    def accepted(self) -> bool:
        return self.draft is not None


def user_message(artifact_text: str) -> str:
    """The user message: only the artifact, between delimiter lines."""
    return "<artifact>\n" + artifact_text + "\n</artifact>"


def retry_system_message(registrar: Registrar, errors: tuple[str, ...]) -> str:
    """The Registrar prompt, a blank line, then the retry prompt listing the errors."""
    listed = "\n".join(f"- {error}" for error in errors)
    # str.replace, not str.format: error messages contain braces.
    retry = registrar.retry_prompt.text.replace(ERRORS_PLACEHOLDER, listed)
    return registrar.prompt.text.rstrip("\n") + "\n\n" + retry


def check_artifact(artifact_text: str) -> None:
    """Raise ``ArtifactRefusedError`` if the artifact cannot be sent to a Registrar."""
    if not artifact_text.strip():
        raise ArtifactRefusedError("The artifact is empty")
    if CLOSING_TAG.search(artifact_text):
        raise ArtifactRefusedError(
            "The artifact contains '</artifact', which could close the artifact delimiter "
            "early; it was not sent to the model"
        )


def draft_record(
    registrar: Registrar, llm: ChatModel, artifact_text: str, *, artifact_id: str
) -> DraftOutcome:
    """Draft one record from an artifact, with at most ``max_attempts`` calls.

    ``LLMResponseError`` counts as a failed attempt; every other ``LLMError`` propagates
    unchanged (the SDK already retried what can be retried).
    """
    check_artifact(artifact_text)
    schema = draft_schema(registrar.spec)
    user = user_message(artifact_text)
    usage: list[Usage] = []
    errors: tuple[str, ...] = ()
    version = registrar.prompt.version

    for attempt in range(1, registrar.max_attempts + 1):
        if attempt == 1:
            system, version = registrar.prompt.text, registrar.prompt.version
        else:
            system, version = retry_system_message(registrar, errors), registrar.retry_version
        context = CallContext(registrar.agent, artifact_id, version)
        try:
            result = llm.chat_json(system=system, user=user, schema=schema, context=context)
        except LLMResponseError as error:
            if error.usage is not None:
                usage.append(error.usage)
            errors = (str(error),)
            continue
        usage.append(result.usage)
        validation = validate_draft(result.data, registrar.spec, artifact_text)
        if validation.ok:
            return DraftOutcome(
                draft=result.data,
                errors=(),
                attempts=attempt,
                model=result.model,
                prompt_version=version,
                usage=tuple(usage),
            )
        errors = validation.errors

    return DraftOutcome(
        draft=None,
        errors=errors,
        attempts=registrar.max_attempts,
        model=None,
        prompt_version=version,
        usage=tuple(usage),
    )
