import socket

import httpx
import pytest

from knowledge_automata.llm import CallContext, LLMRateLimitError, ModelIds

BLOCKED = "must not use the network"


def test_sockets_are_blocked():
    with pytest.raises(RuntimeError, match=BLOCKED):
        socket.create_connection(("example.com", 443))
    with pytest.raises(RuntimeError, match=BLOCKED):
        socket.socket().connect(("127.0.0.1", 9))


def test_http_clients_are_blocked():
    with pytest.raises(RuntimeError, match=BLOCKED):
        httpx.get("https://api.cohere.com", timeout=1)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"agent": "decision-registrar"},
        {"agent": "smoke-check", "artifact_id": "ART-0001", "prompt_version": "1.0"},
        {"agent": "a1", "artifact_id": "ART-123456"},
    ],
)
def test_call_context_accepts_valid_values(kwargs):
    assert CallContext(**kwargs).agent == kwargs["agent"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"agent": "Decision Registrar"},
        {"agent": "decision_registrar"},
        {"agent": "-registrar"},
        {"agent": ""},
        {"agent": "registrar\n"},
        {"agent": "registrar", "artifact_id": "ART-1"},
        {"agent": "registrar", "artifact_id": "art-0001"},
        {"agent": "registrar", "artifact_id": "ART-0001\n"},
        {"agent": "registrar", "prompt_version": ""},
    ],
)
def test_call_context_rejects_values_the_event_schema_would_reject(kwargs):
    with pytest.raises(ValueError):
        CallContext(**kwargs)


def test_model_ids_by_operation():
    models = ModelIds(chat="c", embed="e", rerank="r")
    assert [models.for_operation(op) for op in ("chat", "embed", "rerank")] == ["c", "e", "r"]


def test_rate_limit_error_flags_the_monthly_cap():
    assert LLMRateLimitError("slow down").monthly_cap is False
    assert LLMRateLimitError("cap reached", monthly_cap=True).monthly_cap is True
