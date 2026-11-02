"""One checked chat call with one retry, shared by the agents (ADR-0014, ADR-0018).

Call the model with the prompt, check the reply with code, and when the check fails or the
response is unusable, call again with the errors added from the versioned retry prompt.
The first attempt cites the prompt's version; every later attempt cites
``<prompt>+<retry prompt>``. ``LLMResponseError`` counts as a failed attempt; every other
``LLMError`` propagates unchanged (the SDK already retried what can be retried).
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from knowledge_automata.core.prompts import Prompt, retry_system_text
from knowledge_automata.core.validation import ValidationResult
from knowledge_automata.llm import CallContext, ChatModel, LLMResponseError, Usage


@dataclass(frozen=True)
class CheckedReply:
    data: dict[str, Any] | None  # the accepted reply; None when rejected
    errors: tuple[str, ...]  # errors of the last attempt; empty when accepted
    attempts: int
    model: str | None  # model that produced the accepted reply
    prompt_version: str  # of the accepted attempt, or of the last attempt
    usage: tuple[Usage, ...]  # one per billed call, including unusable responses
    error_type: str | None = None  # exception class name when the last response was unusable

    @property
    def accepted(self) -> bool:
        return self.data is not None


def retry_version(prompt: Prompt, retry_prompt: Prompt) -> str:
    """The version a retry attempt cites, for example ``governor.v1+governor-retry.v1``."""
    return f"{prompt.version}+{retry_prompt.version}"


def checked_chat(
    llm: ChatModel,
    *,
    agent: str,
    artifact_id: str,
    prompt: Prompt,
    retry_prompt: Prompt,
    user: str,
    schema: Mapping[str, Any],
    check: Callable[[Any], ValidationResult],
    max_attempts: int,
) -> CheckedReply:
    """Call the model at most ``max_attempts`` times until ``check`` accepts the reply."""
    usage: list[Usage] = []
    errors: tuple[str, ...] = ()
    error_type: str | None = None
    version = prompt.version

    for attempt in range(1, max_attempts + 1):
        if attempt == 1:
            system, version = prompt.text, prompt.version
        else:
            system = retry_system_text(prompt, retry_prompt, errors)
            version = retry_version(prompt, retry_prompt)
        context = CallContext(agent, artifact_id, version)
        try:
            result = llm.chat_json(system=system, user=user, schema=schema, context=context)
        except LLMResponseError as error:
            if error.usage is not None:
                usage.append(error.usage)
            errors, error_type = (str(error),), type(error).__name__
            continue
        usage.append(result.usage)
        validation = check(result.data)
        if validation.ok:
            return CheckedReply(
                data=result.data,
                errors=(),
                attempts=attempt,
                model=result.model,
                prompt_version=version,
                usage=tuple(usage),
            )
        errors, error_type = validation.errors, None

    return CheckedReply(
        data=None,
        errors=errors,
        attempts=max_attempts,
        model=None,
        prompt_version=version,
        usage=tuple(usage),
        error_type=error_type,
    )
