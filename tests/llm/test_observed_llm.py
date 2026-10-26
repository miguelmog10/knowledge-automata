import dataclasses
import json
import uuid
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from knowledge_automata.core.validation import validate_llm_event
from knowledge_automata.llm import (
    CallContext,
    JsonlFileSink,
    LLMRateLimitError,
    LLMResponseError,
    MemorySink,
    ObservedLLM,
    Usage,
)
from knowledge_automata.llm.fake import FakeLLM
from knowledge_automata.llm.pricing import ModelPrice, PriceTable

SENTINEL = "SENTINEL-c0ffee"
CONTEXT = CallContext(agent="decision-registrar", artifact_id="ART-0042", prompt_version="v1")
FIXED_TS = datetime(2026, 10, 25, 9, 30, 0, 123456, tzinfo=UTC)
TABLE = PriceTable(
    checked_on=date(2026, 10, 25),
    source="https://example.test/prices",
    currency="USD",
    models={
        "fake-chat": ModelPrice(
            input_per_million_tokens=Decimal("2.50"), output_per_million_tokens=Decimal("10")
        ),
        "fake-rerank": ModelPrice(per_thousand_search_units=Decimal("2")),
    },
)


def ticking_timer(step=0.25):
    now = [100.0]

    def timer():
        now[0] += step
        return now[0]

    return timer


RUN_ID = "0b6c4c1e-8f2d-4d8a-9a1e-3c5f7e9b2d41"


def observed(fake, prices=None, sink=None, run_id=RUN_ID):
    sink = sink if sink is not None else MemorySink()
    llm = ObservedLLM(
        fake,
        provider="fake",
        sink=sink,
        run_id=run_id,
        prices=prices,
        clock=lambda: FIXED_TS,
        timer=ticking_timer(),
    )
    return llm, sink


def chat(llm, user="notes"):
    return llm.chat_json(system="sys", user=user, schema={"type": "object"}, context=CONTEXT)


def test_chat_emits_one_complete_event():
    fake = FakeLLM([{"title": "ok"}])
    llm, sink = observed(fake)
    result = chat(llm)
    assert result.data == {"title": "ok"}
    (event,) = sink.events
    assert set(event) == {
        "schema_version",
        "ts",
        "event_id",
        "run_id",
        "provider",
        "model",
        "operation",
        "agent",
        "artifact_id",
        "prompt_version",
        "status",
        "latency_ms",
        "items",
        "input_tokens",
        "output_tokens",
    }
    assert event["schema_version"] == "1.0"
    assert event["run_id"] == RUN_ID
    assert event["ts"] == "2026-10-25T09:30:00.123Z"
    assert event["provider"] == "fake"
    assert event["model"] == "fake-chat"
    assert event["operation"] == "chat"
    assert event["agent"] == "decision-registrar"
    assert event["artifact_id"] == "ART-0042"
    assert event["prompt_version"] == "v1"
    assert event["status"] == "ok"
    assert event["latency_ms"] == 250
    assert event["items"] == 1
    assert (event["input_tokens"], event["output_tokens"]) == (
        result.usage.input_tokens,
        result.usage.output_tokens,
    )
    assert validate_llm_event(event).ok


def test_embed_and_rerank_events_count_items_and_units():
    llm, sink = observed(FakeLLM())
    context = CallContext(agent="smoke-check")
    llm.embed(["a", "b", "c"], input_type="document", context=context)
    llm.rerank("q", ["a", "b"], top_n=1, context=context)
    embed_event, rerank_event = sink.events
    assert (embed_event["operation"], embed_event["model"], embed_event["items"]) == (
        "embed",
        "fake-embed",
        3,
    )
    assert embed_event["input_tokens"] == 3
    assert "output_tokens" not in embed_event
    assert "artifact_id" not in embed_event
    assert (rerank_event["operation"], rerank_event["items"], rerank_event["search_units"]) == (
        "rerank",
        2,
        1,
    )
    assert all(validate_llm_event(event).ok for event in sink.events)
    assert embed_event["event_id"] != rerank_event["event_id"]


class ReportingLLM(FakeLLM):
    """A fake that also reports raw tokens and a request ID, as Cohere does."""

    def chat_json(self, **kwargs):
        result = super().chat_json(**kwargs)
        usage = dataclasses.replace(result.usage, raw_input_tokens=300, raw_output_tokens=9)
        return dataclasses.replace(result, usage=usage, request_id="req-chat-1")


def test_raw_tokens_and_request_id_reach_the_event_when_reported():
    llm, sink = observed(ReportingLLM([{"a": 1}]))
    chat(llm)
    (event,) = sink.events
    assert (event["raw_input_tokens"], event["raw_output_tokens"]) == (300, 9)
    assert event["request_id"] == "req-chat-1"
    assert validate_llm_event(event).ok


def test_raw_tokens_and_request_id_are_omitted_when_not_reported():
    llm, sink = observed(FakeLLM([{"a": 1}]))
    chat(llm)
    llm.embed(["a"], input_type="query", context=CONTEXT)
    llm.rerank("q", ["a"], top_n=1, context=CONTEXT)
    for event in sink.events:
        assert not {"raw_input_tokens", "raw_output_tokens", "request_id"} & set(event)


def test_every_event_of_one_observer_shares_its_run_id():
    llm, sink = observed(FakeLLM([{"a": 1}, LLMResponseError("bad")]))
    chat(llm)
    with pytest.raises(LLMResponseError):
        chat(llm)
    llm.embed(["a"], input_type="query", context=CONTEXT)
    llm.rerank("q", ["a"], top_n=1, context=CONTEXT)
    assert len(sink.events) == 4
    assert {event["run_id"] for event in sink.events} == {RUN_ID}
    assert {event["schema_version"] for event in sink.events} == {"1.0"}
    assert len({event["event_id"] for event in sink.events}) == 4
    assert all(validate_llm_event(event).ok for event in sink.events)


def test_run_id_defaults_to_a_new_uuid_and_is_validated():
    first, second = observed(FakeLLM(), run_id=None)[0], observed(FakeLLM(), run_id=None)[0]
    assert uuid.UUID(first.run_id).version == 4
    assert first.run_id != second.run_id
    assert observed(FakeLLM(), run_id=RUN_ID.upper())[0].run_id == RUN_ID
    with pytest.raises(ValueError, match="run_id must be a UUID"):
        observed(FakeLLM(), run_id="run-1")


def test_errors_are_logged_and_reraised_unchanged():
    error = LLMRateLimitError("monthly cap", monthly_cap=True)
    llm, sink = observed(FakeLLM([error]))
    with pytest.raises(LLMRateLimitError) as excinfo:
        chat(llm)
    assert excinfo.value is error
    (event,) = sink.events
    assert event["status"] == "error"
    assert event["error_type"] == "LLMRateLimitError"
    assert event["model"] == "fake-chat"
    assert "input_tokens" not in event
    assert validate_llm_event(event).ok


def test_error_events_keep_billed_usage_and_cost():
    error = LLMResponseError("truncated", usage=Usage(input_tokens=400_000, output_tokens=100_000))
    llm, sink = observed(FakeLLM([error]), prices=TABLE)
    with pytest.raises(LLMResponseError):
        chat(llm)
    (event,) = sink.events
    assert (event["input_tokens"], event["output_tokens"]) == (400_000, 100_000)
    assert "request_id" not in event
    assert Decimal(event["cost_usd"]) == 2
    assert event["price_table"] == "2026-10-25"
    assert validate_llm_event(event).ok


def test_error_events_keep_the_request_id_and_raw_tokens():
    error = LLMResponseError(
        "truncated",
        usage=Usage(input_tokens=12, output_tokens=5, raw_input_tokens=300, raw_output_tokens=9),
        request_id="req-err-1",
    )
    llm, sink = observed(FakeLLM([error]))
    with pytest.raises(LLMResponseError):
        chat(llm)
    (event,) = sink.events
    assert event["request_id"] == "req-err-1"
    assert (event["raw_input_tokens"], event["raw_output_tokens"]) == (300, 9)
    assert validate_llm_event(event).ok


def test_sentinels_never_reach_the_event_log(tmp_path):
    path = tmp_path / "events.jsonl"
    fake = FakeLLM([{"summary": SENTINEL}, LLMResponseError(f"bad {SENTINEL}")])
    llm, _ = observed(fake, sink=JsonlFileSink(path))
    artifact_text = f"Meeting notes. {SENTINEL}"
    llm.chat_json(
        system=f"Instructions {SENTINEL}",
        user=artifact_text,
        schema={"type": "object"},
        context=CONTEXT,
    )
    with pytest.raises(LLMResponseError):
        chat(llm, user=artifact_text)
    llm.embed([artifact_text], input_type="document", context=CONTEXT)
    llm.rerank(SENTINEL, [artifact_text], top_n=1, context=CONTEXT)
    log = path.read_text(encoding="utf-8")
    assert len(log.splitlines()) == 4
    assert SENTINEL not in log


def test_cost_is_present_only_when_the_model_has_a_price():
    llm, sink = observed(FakeLLM([{"a": 1}]), prices=TABLE)
    chat(llm)
    llm.rerank("q", ["a", "b"], top_n=1, context=CONTEXT)
    llm.embed(["a"], input_type="query", context=CONTEXT)
    chat_event, rerank_event, embed_event = sink.events
    assert Decimal(chat_event["cost_usd"]) > 0
    assert rerank_event["cost_usd"] == "0.002"
    assert "cost_usd" not in embed_event and "price_table" not in embed_event
    assert all(validate_llm_event(event).ok for event in sink.events)


def test_without_a_price_table_no_cost_is_logged():
    llm, sink = observed(FakeLLM([{"a": 1}]))
    chat(llm)
    assert "cost_usd" not in sink.events[0]


def test_timestamps_are_utc():
    llm = ObservedLLM(
        FakeLLM([{"a": 1}]),
        provider="fake",
        sink=(sink := MemorySink()),
        clock=lambda: datetime(2026, 10, 25, 11, 0, tzinfo=timezone(timedelta(hours=2))),
    )
    chat(llm)
    assert sink.events[0]["ts"] == "2026-10-25T09:00:00.000Z"


def test_naive_clocks_and_bad_providers_are_rejected():
    with pytest.raises(ValueError):
        ObservedLLM(FakeLLM(), provider="Fake", sink=MemorySink())
    llm = ObservedLLM(
        FakeLLM([{"a": 1}]), provider="fake", sink=MemorySink(), clock=lambda: datetime(2026, 1, 1)
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        chat(llm)


def test_jsonl_sink_creates_the_folder_and_appends_lines(tmp_path):
    path = tmp_path / "runtime" / "logs" / "llm-events.jsonl"
    sink = JsonlFileSink(path)
    sink.emit({"n": 1, "text": "café"})
    sink.emit({"n": 2})
    lines = path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == [{"n": 1, "text": "café"}, {"n": 2}]


def test_jsonl_sink_keeps_existing_lines_byte_for_byte(tmp_path):
    path = tmp_path / "llm-events.jsonl"
    earlier = b'{"from": "an earlier run",  "spacing": "kept"}\n'
    path.write_bytes(earlier)
    JsonlFileSink(path).emit({"n": 1})
    content = path.read_bytes()
    assert content.startswith(earlier)
    assert content[len(earlier) :] == b'{"n": 1}\n'


def test_jsonl_sink_starts_a_new_file_if_the_log_is_deleted(tmp_path):
    path = tmp_path / "llm-events.jsonl"
    sink = JsonlFileSink(path)
    sink.emit({"n": 1})
    path.unlink()
    sink.emit({"n": 2})
    assert [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] == [
        {"n": 2}
    ]


# The event schema itself


def valid_event(**changes):
    event = {
        "schema_version": "1.0",
        "ts": "2026-10-25T09:30:00Z",
        "event_id": "6f1c8a8e-3b0a-4c39-9a52-6a0f1f3d2b11",
        "run_id": RUN_ID,
        "provider": "cohere",
        "model": "command-a-plus-05-2026",
        "operation": "chat",
        "agent": "smoke-check",
        "status": "ok",
        "latency_ms": 812,
        "items": 1,
    }
    event.update(changes)
    return {key: value for key, value in event.items() if value is not None}


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"prompt": "leaked"}, "Additional properties"),
        ({"status": "error"}, "'error_type' is a required property"),
        ({"error_type": "LLMError"}, "should not be valid"),
        ({"cost_usd": "0.01"}, "'price_table' is a required property"),
        ({"cost_usd": "1E-7", "price_table": "2026-10-25"}, "does not match"),
        ({"ts": "2026-10-25 09:30"}, "is not a 'date-time'"),
        ({"event_id": "not-a-uuid"}, "is not a 'uuid'"),
        ({"artifact_id": "ART-1"}, "does not match"),
        ({"latency_ms": -1}, "less than the minimum"),
        ({"run_id": None}, "'run_id' is a required property"),
        ({"run_id": "run-1"}, "is not a 'uuid'"),
        ({"schema_version": None}, "'schema_version' is a required property"),
        ({"schema_version": "v1"}, "does not match"),
        ({"request_id": ""}, "should be non-empty"),
        ({"raw_output_tokens": -1}, "less than the minimum"),
    ],
)
def test_invalid_events_are_rejected(changes, message):
    assert validate_llm_event(valid_event()).ok
    result = validate_llm_event(valid_event(**changes))
    assert not result.ok
    assert any(message in error for error in result.errors), result.errors
