import math

import pytest

from knowledge_automata.llm import CallContext, LLMUnavailableError, Usage
from knowledge_automata.llm.fake import EMBED_DIMENSIONS, FakeLLM

CONTEXT = CallContext(agent="test-agent", artifact_id="ART-0001")


def chat(fake, user="notes"):
    return fake.chat_json(system="sys", user=user, schema={"type": "object"}, context=CONTEXT)


def test_chat_returns_scripted_responses_in_order_and_records_calls():
    fake = FakeLLM([{"n": 1}, {"n": 2}])
    assert chat(fake, "first").data == {"n": 1}
    second = chat(fake, "second")
    assert second.data == {"n": 2}
    assert second.model == "fake-chat"
    assert second.finish_reason == "COMPLETE"
    assert [call.inputs["user"] for call in fake.calls] == ["first", "second"]
    assert all(call.operation == "chat" and call.context == CONTEXT for call in fake.calls)


def test_chat_raises_scripted_exceptions():
    fake = FakeLLM([LLMUnavailableError("down"), {"ok": True}])
    with pytest.raises(LLMUnavailableError):
        chat(fake)
    assert chat(fake).data == {"ok": True}


def test_chat_fails_loudly_when_the_script_runs_out():
    with pytest.raises(AssertionError, match="ran out of scripted chat responses at chat call 1"):
        chat(FakeLLM())


def test_chat_responses_are_copied():
    scripted = {"items": [1]}
    fake = FakeLLM([scripted, scripted])
    chat(fake).data["items"].append(2)
    assert chat(fake).data == {"items": [1]}


def test_chat_usage_is_deterministic():
    fake = FakeLLM([{"a": 1}])
    assert chat(fake, "12345678").usage == Usage(input_tokens=1 + 2, output_tokens=2)


def test_scripted_responses_must_be_dicts_or_exceptions():
    with pytest.raises(TypeError):
        FakeLLM(["not a dict"])


def test_embed_is_deterministic_normalized_and_ordered():
    fake = FakeLLM()
    first = fake.embed(["alpha", "beta"], input_type="document", context=CONTEXT)
    again = fake.embed(["beta"], input_type="query", context=CONTEXT)
    assert len(first.vectors) == 2
    assert all(len(vector) == EMBED_DIMENSIONS for vector in first.vectors)
    assert all(math.isclose(sum(x * x for x in v), 1.0) for v in first.vectors)
    assert first.vectors[0] != first.vectors[1]
    assert again.vectors[0] == first.vectors[1]
    assert first.model == "fake-embed"
    assert first.usage == Usage(input_tokens=2 + 1)


def test_embed_rejects_unknown_input_types():
    with pytest.raises(ValueError):
        FakeLLM().embed(["a"], input_type="classification", context=CONTEXT)


def test_rerank_orders_by_word_overlap_then_index():
    fake = FakeLLM()
    documents = ["budget approved", "risk register", "the budget was approved today", "risk"]
    result = fake.rerank("Budget approved", documents, top_n=3, context=CONTEXT)
    assert [r.index for r in result.results] == [0, 2, 1]
    assert result.results[0].score == 1.0
    assert result.model == "fake-rerank"
    assert result.usage == Usage(search_units=1)
    assert fake.calls[-1].inputs["top_n"] == 3


def test_rerank_validates_top_n():
    with pytest.raises(ValueError):
        FakeLLM().rerank("q", ["a"], top_n=0, context=CONTEXT)
