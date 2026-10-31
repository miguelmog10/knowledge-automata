import json
from collections import deque

import cohere
import httpx
import pytest

from knowledge_automata.core.schemas import draft_schema
from knowledge_automata.domains.project_management.registers import DECISION_LOG
from knowledge_automata.llm import (
    CallContext,
    LLMAuthError,
    LLMConfigError,
    LLMRateLimitError,
    LLMRequestError,
    LLMResponseError,
    LLMSettings,
    LLMUnavailableError,
    Usage,
    cohere_adapter,
)
from knowledge_automata.llm.cohere_adapter import EMBED_BATCH_SIZE, CohereAdapter
from knowledge_automata.llm.provider_schema import to_cohere_schema
from knowledge_automata.pipeline import record_decision_settings

KEY = "test-KEY-not-real-0123456789"
PROMPT_SENTINEL = "PROMPT-SENTINEL-7f3a"
CONTEXT = CallContext(agent="test-agent", artifact_id="ART-0001")
SCHEMA = {
    "type": "object",
    "properties": {"color": {"type": "string", "enum": ["vermilion"], "x-note": "dropped"}},
    "required": ["color"],
}


class FakeCohereAPI:
    """Answers the real SDK's HTTP requests from a script, through httpx.MockTransport."""

    def __init__(self, *responses):
        self.responses = deque(responses)
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        item = self.responses.popleft()
        if callable(item):
            item = item(request)
        if isinstance(item, Exception):
            raise item
        status, body = item
        return httpx.Response(status, json=body)

    def bodies(self) -> list[dict]:
        return [json.loads(request.content) for request in self.requests]


def adapter_for(api: FakeCohereAPI, *, max_retries=0, **settings_kwargs) -> CohereAdapter:
    settings = LLMSettings(api_key=KEY, max_retries=max_retries, **settings_kwargs)
    client = cohere.ClientV2(
        api_key=KEY,
        max_retries=max_retries,
        httpx_client=httpx.Client(transport=httpx.MockTransport(api.handler)),
    )
    return CohereAdapter(settings, client=client)


def chat_body(text, *, finish_reason="COMPLETE", thinking=None, billed=(12.0, 5.0)):
    content = [{"type": "thinking", "thinking": thinking}] if thinking else []
    content.append({"type": "text", "text": text})
    return {
        "id": "chat-1",
        "finish_reason": finish_reason,
        "message": {"role": "assistant", "content": content},
        "usage": {
            "billed_units": {"input_tokens": billed[0], "output_tokens": billed[1]},
            "tokens": {"input_tokens": 300, "output_tokens": 9},
        },
    }


def embed_body(request):
    texts = json.loads(request.content)["texts"]
    # Each vector encodes its text, so the test can check the output order.
    return 200, {
        "id": f"embed-{texts[0]}",
        "response_type": "embeddings_by_type",
        "embeddings": {"float": [[float(text.split("-")[1]), 0.5] for text in texts]},
        "texts": texts,
        "meta": {
            "api_version": {"version": "2"},
            "billed_units": {"input_tokens": len(texts)},
            "tokens": {"input_tokens": 2 * len(texts)},
        },
    }


def call_chat(adapter, schema=SCHEMA):
    return adapter.chat_json(
        system="Return JSON.", user=f"Notes: {PROMPT_SENTINEL}", schema=schema, context=CONTEXT
    )


# Chat


def test_chat_request_has_separate_messages_model_temperature_and_schema():
    api = FakeCohereAPI((200, chat_body('{"color": "vermilion"}')))
    call_chat(adapter_for(api))
    (request,) = api.requests
    body = json.loads(request.content)
    assert request.url.path == "/v2/chat"
    assert body["model"] == "command-a-plus-05-2026"
    assert body["messages"] == [
        {"role": "system", "content": "Return JSON."},
        {"role": "user", "content": f"Notes: {PROMPT_SENTINEL}"},
    ]
    assert body["temperature"] == 0
    assert body["response_format"] == {
        "type": "json_object",
        "json_schema": to_cohere_schema(SCHEMA),
    }
    assert "thinking" not in body


def test_chat_uses_the_configured_schema_field_and_thinking():
    api = FakeCohereAPI((200, chat_body('{"color": "vermilion"}')))
    settings = LLMSettings(api_key=KEY, max_retries=0, chat_thinking="disabled")
    client = cohere.ClientV2(
        api_key=KEY,
        max_retries=0,
        httpx_client=httpx.Client(transport=httpx.MockTransport(api.handler)),
    )
    CohereAdapter(settings, client=client, schema_field="schema").chat_json(
        system="s", user="u", schema=SCHEMA, context=CONTEXT
    )
    body = api.bodies()[0]
    assert body["response_format"] == {"type": "json_object", "schema": to_cohere_schema(SCHEMA)}
    assert body["thinking"] == {"type": "disabled"}


def test_the_record_decision_default_sends_thinking_enabled_explicitly():
    api = FakeCohereAPI((200, chat_body('{"color": "vermilion"}')))
    settings = record_decision_settings(LLMSettings(api_key=KEY, max_retries=0))
    client = cohere.ClientV2(
        api_key=KEY,
        max_retries=0,
        httpx_client=httpx.Client(transport=httpx.MockTransport(api.handler)),
    )
    CohereAdapter(settings, client=client).chat_json(
        system="s", user="u", schema=SCHEMA, context=CONTEXT
    )
    assert api.bodies()[0]["thinking"] == {"type": "enabled"}


def test_chat_accepts_the_real_decision_draft_schema():
    api = FakeCohereAPI((200, chat_body('{"content": {}}')))
    call_chat(adapter_for(api), schema=draft_schema(DECISION_LOG))
    sent = api.bodies()[0]["response_format"]["json_schema"]
    assert sent == to_cohere_schema(draft_schema(DECISION_LOG))


def test_chat_returns_the_parsed_object_with_billed_usage():
    api = FakeCohereAPI((200, chat_body('{"color": "vermilion"}', thinking="Sky... vermilion.")))
    result = call_chat(adapter_for(api))
    assert result.data == {"color": "vermilion"}
    assert result.model == "command-a-plus-05-2026"
    assert result.usage == Usage(
        input_tokens=12, output_tokens=5, raw_input_tokens=300, raw_output_tokens=9
    )
    assert result.request_id == "chat-1"
    assert result.finish_reason == "COMPLETE"


def test_chat_without_raw_tokens_or_id_leaves_them_unset():
    body = chat_body('{"color": "vermilion"}')
    del body["id"], body["usage"]["tokens"]
    result = call_chat(adapter_for(FakeCohereAPI((200, body))))
    assert result.usage == Usage(input_tokens=12, output_tokens=5)
    assert result.request_id is None


def test_billed_units_are_rounded_up_to_whole_units():
    api = FakeCohereAPI((200, chat_body('{"color": "vermilion"}', billed=(12.2, 5.0))))
    usage = call_chat(adapter_for(api)).usage
    assert (usage.input_tokens, usage.output_tokens) == (13, 5)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (chat_body(f'{{"color": "{PROMPT_SENTINEL}'), "not valid JSON"),
        (chat_body('["vermilion"]'), "JSON array, not an object"),
        (chat_body('{"color": "verm', finish_reason="MAX_TOKENS"), "truncated"),
        (chat_body("{}", finish_reason="ERROR"), "did not complete"),
        ({**chat_body("{}"), "message": {"role": "assistant", "content": []}}, "no text content"),
    ],
)
def test_unusable_chat_responses_raise_with_billed_usage(body, message):
    api = FakeCohereAPI((200, body))
    with pytest.raises(LLMResponseError, match=message) as excinfo:
        call_chat(adapter_for(api))
    assert excinfo.value.usage == Usage(
        input_tokens=12, output_tokens=5, raw_input_tokens=300, raw_output_tokens=9
    )
    assert excinfo.value.request_id == "chat-1"
    assert excinfo.value.finish_reason == body["finish_reason"]
    assert PROMPT_SENTINEL not in str(excinfo.value)


# Embed


def test_embed_splits_into_batches_and_keeps_order():
    texts = [f"text-{i}" for i in range(200)]
    api = FakeCohereAPI(embed_body, embed_body, embed_body)
    result = adapter_for(api).embed(texts, input_type="document", context=CONTEXT)
    bodies = api.bodies()
    assert [len(body["texts"]) for body in bodies] == [EMBED_BATCH_SIZE, EMBED_BATCH_SIZE, 8]
    assert all(request.url.path == "/v2/embed" for request in api.requests)
    assert all(body["embedding_types"] == ["float"] for body in bodies)
    assert all(body["model"] == "embed-v5.0-fast" for body in bodies)
    assert [vector[0] for vector in result.vectors] == [float(i) for i in range(200)]
    assert result.usage == Usage(input_tokens=200, raw_input_tokens=400)
    # One request per batch, so the IDs of all batches are kept, in order.
    assert result.request_id == "embed-text-0,embed-text-96,embed-text-192"


@pytest.mark.parametrize(
    ("input_type", "cohere_type"), [("document", "search_document"), ("query", "search_query")]
)
def test_embed_maps_input_types(input_type, cohere_type):
    api = FakeCohereAPI(embed_body)
    adapter_for(api).embed(["text-1"], input_type=input_type, context=CONTEXT)
    assert api.bodies()[0]["input_type"] == cohere_type


def test_embed_rejects_unknown_input_types_and_skips_empty_input():
    api = FakeCohereAPI()
    adapter = adapter_for(api)
    with pytest.raises(ValueError):
        adapter.embed(["a"], input_type="clustering", context=CONTEXT)
    assert adapter.embed([], input_type="query", context=CONTEXT).vectors == []
    assert api.requests == []


def test_embed_rejects_a_vector_count_mismatch():
    def short(request):
        status, body = embed_body(request)
        body["embeddings"]["float"].pop()
        return status, body

    with pytest.raises(LLMResponseError, match="1 embeddings for 2 texts") as excinfo:
        adapter_for(FakeCohereAPI(short)).embed(
            ["text-1", "text-2"], input_type="query", context=CONTEXT
        )
    assert excinfo.value.finish_reason is None


# Rerank


def rerank_body(results, search_units=1):
    return {
        "id": "rerank-1",
        "results": results,
        "meta": {"billed_units": {"search_units": search_units}, "tokens": {"input_tokens": 7}},
    }


def test_rerank_returns_best_first_with_indices():
    unsorted = [{"index": 0, "relevance_score": 0.2}, {"index": 2, "relevance_score": 0.9}]
    api = FakeCohereAPI((200, rerank_body(unsorted)))
    result = adapter_for(api).rerank("q", ["a", "b", "c"], top_n=2, context=CONTEXT)
    assert [(r.index, r.score) for r in result.results] == [(2, 0.9), (0, 0.2)]
    assert result.model == "rerank-v5.0-pro"
    assert result.usage == Usage(search_units=1, raw_input_tokens=7)
    assert result.request_id == "rerank-1"
    body = api.bodies()[0]
    assert api.requests[0].url.path == "/v2/rerank"
    assert (body["query"], body["documents"], body["top_n"]) == ("q", ["a", "b", "c"], 2)


def test_rerank_caps_top_n_at_the_number_of_documents():
    api = FakeCohereAPI((200, rerank_body([{"index": 0, "relevance_score": 0.5}])))
    adapter_for(api).rerank("q", ["only"], top_n=10, context=CONTEXT)
    assert api.bodies()[0]["top_n"] == 1


def test_rerank_rejects_bad_indices_and_bad_top_n():
    api = FakeCohereAPI((200, rerank_body([{"index": 5, "relevance_score": 0.5}])))
    adapter = adapter_for(api)
    with pytest.raises(LLMResponseError, match="valid index"):
        adapter.rerank("q", ["a"], top_n=1, context=CONTEXT)
    with pytest.raises(ValueError):
        adapter.rerank("q", ["a"], top_n=0, context=CONTEXT)
    assert adapter.rerank("q", [], top_n=3, context=CONTEXT).results == []


# Errors


PER_MINUTE = "You are using a Trial key, which is limited to 40 API calls / minute."
MONTHLY = "You are using a Trial key, which is limited to 1000 API calls / month."


@pytest.mark.parametrize(
    ("response", "error", "message"),
    [
        ((401, {"message": "invalid api token"}), LLMAuthError, "HTTP 401"),
        ((403, {"message": "forbidden"}), LLMAuthError, "HTTP 403"),
        ((498, {"message": "invalid token"}), LLMAuthError, "HTTP 498"),
        ((400, {"message": "invalid json schema: bad"}), LLMRequestError, "invalid json schema"),
        ((404, {"message": "model not found"}), LLMRequestError, "model not found"),
        ((422, {"message": "unprocessable"}), LLMRequestError, "HTTP 422"),
        ((429, {"message": PER_MINUTE}), LLMRateLimitError, "rate limit"),
        ((429, {"message": MONTHLY}), LLMRateLimitError, "monthly call cap"),
        ((402, {"message": "Maximum billing reached"}), LLMRateLimitError, "billing limit"),
        ((408, {"message": "timeout"}), LLMUnavailableError, "HTTP 408"),
        ((500, {"message": "internal"}), LLMUnavailableError, "HTTP 500"),
        ((503, "Service Unavailable"), LLMUnavailableError, "HTTP 503"),
        (httpx.ReadTimeout("timed out"), LLMUnavailableError, "did not respond within 60"),
        (httpx.ConnectError("refused"), LLMUnavailableError, "Could not reach Cohere"),
    ],
)
def test_provider_errors_map_to_project_exceptions(response, error, message):
    api = FakeCohereAPI(response)
    with pytest.raises(error, match=message) as excinfo:
        call_chat(adapter_for(api))
    text = str(excinfo.value)
    assert KEY not in text
    assert PROMPT_SENTINEL not in text
    assert excinfo.value.__cause__ is None
    if isinstance(excinfo.value, LLMRateLimitError):
        assert excinfo.value.monthly_cap == (message != "rate limit")


def test_provider_messages_never_echo_the_key():
    api = FakeCohereAPI((400, {"message": f"bad header {KEY}"}))
    with pytest.raises(LLMRequestError) as excinfo:
        call_chat(adapter_for(api))
    assert KEY not in str(excinfo.value)
    assert "[redacted]" in str(excinfo.value)


def test_retries_are_the_sdks_and_bounded_by_settings(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    ok = FakeCohereAPI((429, {"message": PER_MINUTE}), (503, {}), (200, chat_body('{"a": 1}')))
    assert call_chat(adapter_for(ok, max_retries=2)).data == {"a": 1}
    assert len(ok.requests) == 3

    failing = FakeCohereAPI((500, {}), (500, {}), (500, {}), (200, chat_body("{}")))
    with pytest.raises(LLMUnavailableError, match="after 2 retries"):
        call_chat(adapter_for(failing, max_retries=2))
    assert len(failing.requests) == 3


# Building the real client


def test_default_client_gets_the_key_timeout_and_retries(monkeypatch):
    built = {}
    monkeypatch.setattr(cohere_adapter.cohere, "ClientV2", lambda **kwargs: built.update(kwargs))
    settings = LLMSettings(api_key=KEY, timeout_seconds=12.5, max_retries=4)
    CohereAdapter(settings)
    assert built == {"api_key": KEY, "timeout": 12.5, "max_retries": 4}


def test_missing_key_raises_when_the_adapter_is_built():
    with pytest.raises(LLMConfigError, match="uv run --env-file .env"):
        CohereAdapter(LLMSettings.from_env({}))
