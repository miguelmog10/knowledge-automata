import json
import socket
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


class NetworkBlockedError(RuntimeError):
    """Raised when a test tries to open a network connection."""


@pytest.fixture(autouse=True)
def _block_network(monkeypatch):
    # An accidental real LLM call fails loudly instead of spending trial calls.
    def blocked(*args, **kwargs):
        raise NetworkBlockedError("Tests must not use the network; use FakeLLM or a stub client")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)


def load_json(name: str) -> dict:
    with (FIXTURES / name).open(encoding="utf-8") as file:
        return json.load(file)


@pytest.fixture
def artifact_text() -> str:
    return (FIXTURES / "artifact-steering-group.txt").read_text(encoding="utf-8")


@pytest.fixture
def decision_record() -> dict:
    return load_json("decision-record.json")


@pytest.fixture
def risk_record() -> dict:
    return load_json("risk-record.json")


@pytest.fixture
def decision_draft() -> dict:
    return load_json("decision-draft.json")


@pytest.fixture
def risk_draft() -> dict:
    return load_json("risk-draft.json")
