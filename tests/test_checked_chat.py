import pytest

from knowledge_automata.agents.checked_chat import checked_chat, retry_version
from knowledge_automata.core.prompts import Prompt
from knowledge_automata.core.validation import ValidationResult
from knowledge_automata.llm import CallContext, LLMAuthError, LLMResponseError
from knowledge_automata.llm.fake import FakeLLM

PROMPT = Prompt("test-agent.v1", "Answer with an object.\n")
RETRY = Prompt("test-retry.v1", "## Rejected\n\n{errors}\n")
GOOD, BAD = {"answer": "yes"}, {"answer": "no"}


def check(data):
    return ValidationResult(() if data == GOOD else ("$.answer: must be 'yes'",))


def run(fake, max_attempts=2):
    return checked_chat(
        fake,
        agent="test-agent",
        artifact_id="ART-0001",
        prompt=PROMPT,
        retry_prompt=RETRY,
        user="<artifact>\nx\n</artifact>",
        schema={"type": "object"},
        check=check,
        max_attempts=max_attempts,
    )


def test_accepted_on_the_first_attempt():
    fake = FakeLLM([GOOD])
    reply = run(fake)
    assert reply.accepted and reply.data == GOOD and reply.attempts == 1
    assert reply.prompt_version == "test-agent.v1" and reply.model == "fake-chat"
    assert fake.calls[0].inputs["system"] == PROMPT.text


def test_retry_cites_both_versions_and_lists_the_errors():
    fake = FakeLLM([BAD, GOOD])
    reply = run(fake)
    assert reply.accepted and reply.attempts == 2
    assert reply.prompt_version == retry_version(PROMPT, RETRY) == "test-agent.v1+test-retry.v1"
    assert [call.context for call in fake.calls] == [
        CallContext("test-agent", "ART-0001", "test-agent.v1"),
        CallContext("test-agent", "ART-0001", "test-agent.v1+test-retry.v1"),
    ]
    assert fake.calls[1].inputs["system"] == (
        "Answer with an object.\n\n## Rejected\n\n- $.answer: must be 'yes'\n"
    )


def test_rejected_after_max_attempts_with_the_last_errors():
    fake = FakeLLM([BAD])
    reply = run(fake, max_attempts=1)
    assert not reply.accepted and reply.data is None and reply.model is None
    assert reply.attempts == 1 and reply.errors == ("$.answer: must be 'yes'",)
    assert len(fake.calls) == 1


def test_unusable_response_counts_as_an_attempt():
    reply = run(FakeLLM([LLMResponseError("not JSON"), LLMResponseError("truncated")]))
    assert not reply.accepted and reply.attempts == 2
    assert reply.errors == ("truncated",) and reply.error_type == "LLMResponseError"


def test_other_provider_errors_propagate():
    fake = FakeLLM([LLMAuthError("bad key"), GOOD])
    with pytest.raises(LLMAuthError):
        run(fake)
    assert len(fake.calls) == 1
