from pathlib import Path

import pytest

from knowledge_automata.agents.sensor import DEFAULT_MAX_BYTES, max_bytes_from_env
from knowledge_automata.llm import LLMConfigError, LLMSettings
from knowledge_automata.llm.settings import MISSING_KEY_HINT

SECRET = "sk-test-SECRET-KEY-123"


def test_defaults():
    settings = LLMSettings.from_env({})
    assert settings.api_key is None
    assert settings.chat_model == "command-a-plus-05-2026"
    assert settings.embed_model == "embed-v5.0-fast"
    assert settings.rerank_model == "rerank-v5.0-pro"
    assert settings.temperature == 0
    assert settings.timeout_seconds == 60
    assert settings.max_retries == 2
    assert settings.chat_thinking is None
    assert settings.event_log == Path("runtime/logs/llm-events.jsonl")


def test_values_from_the_environment():
    settings = LLMSettings.from_env(
        {
            "CO_API_KEY": f"  {SECRET}  ",
            "KA_CHAT_MODEL": "command-a-03-2025",
            "KA_EMBED_MODEL": "embed-v5.0-pro",
            "KA_RERANK_MODEL": "rerank-v5.0-fast",
            "KA_LLM_TEMPERATURE": "0.3",
            "KA_LLM_TIMEOUT_SECONDS": "90",
            "KA_LLM_MAX_RETRIES": "0",
            "KA_CHAT_THINKING": "Disabled",
            "KA_EVENT_LOG": "elsewhere/events.jsonl",
        }
    )
    assert settings.api_key == SECRET
    assert settings.models.chat == "command-a-03-2025"
    assert settings.models.embed == "embed-v5.0-pro"
    assert settings.models.rerank == "rerank-v5.0-fast"
    assert settings.temperature == 0.3
    assert settings.timeout_seconds == 90
    assert settings.max_retries == 0
    assert settings.chat_thinking == "disabled"
    assert settings.event_log == Path("elsewhere/events.jsonl")


def test_empty_variables_count_as_unset():
    settings = LLMSettings.from_env(
        {"CO_API_KEY": "", "KA_CHAT_MODEL": " ", "KA_LLM_MAX_RETRIES": ""}
    )
    assert settings == LLMSettings()


def test_missing_key_raises_only_when_required():
    settings = LLMSettings.from_env({})
    with pytest.raises(LLMConfigError) as excinfo:
        settings.require_api_key()
    assert str(excinfo.value) == MISSING_KEY_HINT
    assert ".env.example" in MISSING_KEY_HINT
    assert "uv run --env-file .env" in MISSING_KEY_HINT


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("KA_LLM_TEMPERATURE", "warm"),
        ("KA_LLM_TEMPERATURE", "-0.1"),
        ("KA_LLM_TEMPERATURE", "nan"),
        ("KA_LLM_TIMEOUT_SECONDS", "sixty"),
        ("KA_LLM_TIMEOUT_SECONDS", "0"),
        ("KA_LLM_TIMEOUT_SECONDS", "inf"),
        ("KA_LLM_MAX_RETRIES", "2.5"),
        ("KA_LLM_MAX_RETRIES", "-1"),
        ("KA_CHAT_THINKING", "maybe"),
    ],
)
def test_invalid_values_name_the_variable(name, value):
    with pytest.raises(LLMConfigError, match=name):
        LLMSettings.from_env({name: value, "CO_API_KEY": SECRET})


def test_repr_and_errors_never_show_the_key():
    settings = LLMSettings.from_env({"CO_API_KEY": SECRET})
    assert SECRET not in repr(settings)
    assert SECRET not in str(settings)
    with pytest.raises(LLMConfigError) as excinfo:
        LLMSettings.from_env({"CO_API_KEY": SECRET, "KA_LLM_MAX_RETRIES": "x"})
    assert SECRET not in str(excinfo.value)


ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"


def test_env_example_documents_every_setting_with_its_default():
    assignments = {}
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = line.removeprefix("# ").strip()
        name, sep, value = line.partition("=")
        if sep and name.isupper() and " " not in name:
            assignments[name] = value
    assert assignments["CO_API_KEY"] == ""
    assert {name for name in assignments if name.startswith("KA_")} == {
        "KA_CHAT_MODEL",
        "KA_EMBED_MODEL",
        "KA_RERANK_MODEL",
        "KA_LLM_TEMPERATURE",
        "KA_LLM_TIMEOUT_SECONDS",
        "KA_LLM_MAX_RETRIES",
        "KA_CHAT_THINKING",
        "KA_EVENT_LOG",
        "KA_SENSOR_MAX_BYTES",
    }
    assert LLMSettings.from_env(assignments) == LLMSettings()
    assert max_bytes_from_env(assignments) == DEFAULT_MAX_BYTES
