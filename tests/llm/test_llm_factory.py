import importlib.util
import json
import uuid
from pathlib import Path

import cohere
import httpx
import pytest

from knowledge_automata.llm import (
    CallContext,
    JsonlFileSink,
    LLMConfigError,
    LLMResponseError,
    LLMSettings,
    MemorySink,
    ObservedLLM,
    build_llm,
)
from knowledge_automata.llm.fake import FakeLLM

KEY = "test-KEY-smoke-0123456789"
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "cohere_smoke.py"


def load_smoke_script():
    spec = importlib.util.spec_from_file_location("cohere_smoke", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# build_llm


def test_build_llm_wires_the_adapter_observation_and_prices():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "id": "e",
                "response_type": "embeddings_by_type",
                "embeddings": {"float": [[0.1, 0.2]]},
                "texts": ["a"],
                "meta": {"billed_units": {"input_tokens": 1}},
            },
        )

    client = cohere.ClientV2(
        api_key=KEY,
        max_retries=0,
        httpx_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    sink = MemorySink()
    llm = build_llm(LLMSettings(api_key=KEY), sink=sink, client=client)
    assert isinstance(llm, ObservedLLM)
    assert llm.prices is not None
    llm.embed(["a"], input_type="query", context=CallContext(agent="smoke-check"))
    (event,) = sink.events
    assert (event["provider"], event["model"], event["input_tokens"]) == (
        "cohere",
        "embed-v5.0-fast",
        1,
    )


def test_build_llm_logs_to_the_configured_file_by_default(tmp_path):
    settings = LLMSettings(api_key=KEY, event_log=tmp_path / "logs" / "events.jsonl")
    llm = build_llm(settings, client=object())
    assert isinstance(llm.sink, JsonlFileSink)
    assert llm.sink.path == settings.event_log


def test_each_build_llm_gets_a_new_run_id_unless_one_is_given():
    settings = LLMSettings(api_key=KEY)
    first, second = build_llm(settings, client=object()), build_llm(settings, client=object())
    assert uuid.UUID(first.run_id).version == 4
    assert first.run_id != second.run_id
    shared = str(uuid.uuid4())
    assert build_llm(settings, client=object(), run_id=shared).run_id == shared


def test_build_llm_needs_the_key():
    with pytest.raises(LLMConfigError, match=r"\.env\.example"):
        build_llm(LLMSettings.from_env({}))


# The smoke script, run offline with the fake adapter


def fake_builder(fake, fields):
    def build(settings, *, sink, schema_field, run_id):
        fields.append((schema_field, settings.chat_thinking))
        return ObservedLLM(fake, provider="fake", sink=sink, run_id=run_id)

    return build


def test_smoke_script_runs_every_check(tmp_path, decision_draft):
    smoke = load_smoke_script()
    vermilion = {"color": "vermilion"}
    fake = FakeLLM([vermilion, vermilion, decision_draft, decision_draft])
    fields, lines = [], []
    settings = LLMSettings(api_key=KEY, event_log=tmp_path / "events.jsonl")
    failures = smoke.run(settings, build=fake_builder(fake, fields), out=lines.append)
    output = "\n".join(lines)
    assert failures == 0, output
    assert "'schema': answer {'color': 'vermilion'}, schema ENFORCED" in output
    assert "'json_schema': answer {'color': 'vermilion'}, schema ENFORCED" in output
    assert output.count("validate_draft: PASSED") == 2
    assert [field for field, _ in fields[:2]] == ["schema", "json_schema"]
    assert [thinking for _, thinking in fields[2:4]] == ["enabled", "disabled"]
    assert [call.operation for call in fake.calls] == ["chat"] * 4 + ["embed"] * 2 + ["rerank"]
    assert "7 calls, 0 failed checks" in output
    events = [
        json.loads(line)
        for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(events) == 7
    (run_id,) = {event["run_id"] for event in events}
    assert f"Run ID: {run_id}" in output
    assert all(event["schema_version"] == "1.1" for event in events)
    assert [event.get("finish_reason") for event in events] == ["COMPLETE"] * 4 + [None] * 3
    assert output.count("finish_reason COMPLETE") == 4
    assert KEY not in output


def test_smoke_script_fails_when_the_adapter_field_is_ignored(tmp_path, decision_draft):
    smoke = load_smoke_script()
    used = smoke.RESPONSE_SCHEMA_FIELD
    other = "json_schema" if used == "schema" else "schema"
    answers = {used: {"color": "blue"}, other: {"color": "vermilion"}}
    fake = FakeLLM([answers["schema"], answers["json_schema"], decision_draft, decision_draft])
    lines = []
    settings = LLMSettings(api_key=KEY, event_log=tmp_path / "events.jsonl")
    assert smoke.run(settings, build=fake_builder(fake, []), out=lines.append) == 1
    output = "\n".join(lines)
    assert f"{used!r}: answer {{'color': 'blue'}}, schema NOT enforced" in output
    assert f"Adapter uses {used!r}; enforced: [{other!r}]" in output


def test_smoke_script_reports_failed_checks_and_carries_on(tmp_path):
    smoke = load_smoke_script()
    fake = FakeLLM([{"color": "blue"}, {"color": "blue"}, {"content": {}}, {"content": {}}])
    lines = []
    settings = LLMSettings(api_key=KEY, event_log=tmp_path / "events.jsonl")
    failures = smoke.run(settings, build=fake_builder(fake, []), out=lines.append)
    output = "\n".join(lines)
    assert failures == 3
    assert output.count("validate_draft: FAILED") == 2
    assert "== 4. Rerank" in output


def test_smoke_script_prints_the_error_message_of_a_failed_call(tmp_path, decision_draft):
    smoke = load_smoke_script()
    truncated = LLMResponseError(
        "The chat response was truncated at the token limit (finish_reason MAX_TOKENS)",
        finish_reason="MAX_TOKENS",
    )
    vermilion = {"color": "vermilion"}
    fake = FakeLLM([vermilion, vermilion, truncated, decision_draft])
    lines = []
    settings = LLMSettings(api_key=KEY, event_log=tmp_path / "events.jsonl")
    assert smoke.run(settings, build=fake_builder(fake, []), out=lines.append) == 1
    output = "\n".join(lines)
    assert "finish_reason MAX_TOKENS" in output
    assert "error_message The chat response was truncated at the token limit" in output


def test_smoke_script_without_a_key_exits_with_the_hint(monkeypatch, capsys):
    smoke = load_smoke_script()
    monkeypatch.delenv("CO_API_KEY", raising=False)
    assert smoke.main() == 2
    assert "uv run --env-file .env" in capsys.readouterr().err
