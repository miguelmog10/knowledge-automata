"""The shared Registrar (specialist record keeper) drafting loop (ADR-0014).

A Registrar is a register spec plus a versioned prompt. One loop serves every Registrar:
draft with one call, check the draft with ``validate_draft``, retry once with the errors,
then accept or reject (``agents/checked_chat.py``, shared with the Governor). This module
never writes files and never builds the envelope.
"""

import json
import re
from dataclasses import dataclass
from typing import Any

from knowledge_automata.agents.checked_chat import checked_chat
from knowledge_automata.agents.checked_chat import retry_version as _retry_version
from knowledge_automata.core.prompts import ERRORS_PLACEHOLDER, Prompt, retry_system_text
from knowledge_automata.core.registers import RegisterSpec
from knowledge_automata.core.schemas import draft_schema
from knowledge_automata.core.validation import validate_draft
from knowledge_automata.core.work_orders import WorkOrder
from knowledge_automata.llm import ChatModel, Usage

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
        return _retry_version(self.prompt, self.retry_prompt)


@dataclass(frozen=True)
class DraftOutcome:
    draft: dict[str, Any] | None  # the accepted draft; None when rejected
    errors: tuple[str, ...]  # errors of the last attempt; empty when accepted
    attempts: int
    model: str | None  # model that produced the accepted draft
    prompt_version: str  # of the accepted attempt, or of the last attempt
    usage: tuple[Usage, ...]  # one per billed call, including unusable responses
    error_type: str | None = None  # exception class name when the last response was unusable

    @property
    def accepted(self) -> bool:
        return self.draft is not None


def user_message(artifact_text: str, work_order: WorkOrder | None = None) -> str:
    """The user message: the artifact between delimiter lines, then the work order if any.

    The work order is one JSON object between ``<work-order>`` lines, with every ``<``
    escaped as ``\\u003c`` (as in the Comparator) so no quote inside it can close the tag.
    """
    message = "<artifact>\n" + artifact_text + "\n</artifact>"
    if work_order is None:
        return message
    payload = {"register": work_order.register, "evidence": list(work_order.evidence)}
    body = json.dumps(payload, ensure_ascii=False, indent=2).replace("<", "\\u003c")
    return message + "\n\n<work-order>\n" + body + "\n</work-order>"


def retry_system_message(registrar: Registrar, errors: tuple[str, ...]) -> str:
    """The Registrar prompt, a blank line, then the retry prompt listing the errors."""
    return retry_system_text(registrar.prompt, registrar.retry_prompt, errors)


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
    registrar: Registrar,
    llm: ChatModel,
    artifact_text: str,
    *,
    artifact_id: str,
    work_order: WorkOrder | None = None,
) -> DraftOutcome:
    """Draft one record from an artifact, with at most ``max_attempts`` calls.

    With a ``work_order`` (ADR-0018), the user message carries it after the artifact and
    the draft must quote something that matches one of its quotes. ``LLMResponseError``
    counts as a failed attempt; every other ``LLMError`` propagates unchanged (the SDK
    already retried what can be retried).
    """
    check_artifact(artifact_text)
    if work_order is not None and work_order.register != registrar.spec.name:
        raise ValueError(
            f"Work order {work_order.number} is for {work_order.register!r}, "
            f"not {registrar.spec.name!r}"
        )
    quotes = None if work_order is None else work_order.evidence
    reply = checked_chat(
        llm,
        agent=registrar.agent,
        artifact_id=artifact_id,
        prompt=registrar.prompt,
        retry_prompt=registrar.retry_prompt,
        user=user_message(artifact_text, work_order),
        schema=draft_schema(registrar.spec),
        check=lambda draft: validate_draft(draft, registrar.spec, artifact_text, quotes),
        max_attempts=registrar.max_attempts,
    )
    return DraftOutcome(
        draft=reply.data,
        errors=reply.errors,
        attempts=reply.attempts,
        model=reply.model,
        prompt_version=reply.prompt_version,
        usage=reply.usage,
        error_type=reply.error_type,
    )
