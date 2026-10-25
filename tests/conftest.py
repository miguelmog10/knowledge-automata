import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


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
