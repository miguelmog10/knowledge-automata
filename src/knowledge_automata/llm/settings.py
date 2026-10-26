"""LLM settings from environment variables (ADR-0012).

Locally, ``.env`` is loaded by uv: ``uv run --env-file .env ...``. Empty variables count as
unset, so a copied ``.env.example`` falls back to the defaults.
"""

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from knowledge_automata.llm.errors import LLMConfigError
from knowledge_automata.llm.interfaces import ModelIds

DEFAULT_CHAT_MODEL = "command-a-plus-05-2026"
DEFAULT_EMBED_MODEL = "embed-v5.0-fast"
DEFAULT_RERANK_MODEL = "rerank-v5.0-pro"
DEFAULT_TEMPERATURE = 0.0
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_EVENT_LOG = Path("runtime/logs/llm-events.jsonl")

Thinking = Literal["enabled", "disabled"]
THINKING_VALUES: tuple[Thinking, ...] = ("enabled", "disabled")

MISSING_KEY_HINT = (
    "CO_API_KEY is not set. Copy .env.example to .env, paste your Cohere API key, "
    "and run the command with `uv run --env-file .env ...`."
)


@dataclass(frozen=True)
class LLMSettings:
    # Kept out of repr, so printing or logging the settings never shows the key.
    api_key: str | None = field(default=None, repr=False)
    chat_model: str = DEFAULT_CHAT_MODEL
    embed_model: str = DEFAULT_EMBED_MODEL
    rerank_model: str = DEFAULT_RERANK_MODEL
    temperature: float = DEFAULT_TEMPERATURE
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES
    # None leaves the provider's default (Command A+ thinks by default).
    chat_thinking: Thinking | None = None
    event_log: Path = DEFAULT_EVENT_LOG

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "LLMSettings":
        """Read the settings; raise ``LLMConfigError`` naming any invalid variable."""

        def get(name: str) -> str | None:
            value = env.get(name, "").strip()
            return value or None

        thinking = get("KA_CHAT_THINKING")
        if thinking is not None:
            thinking = thinking.lower()
            if thinking not in THINKING_VALUES:
                raise LLMConfigError(
                    f"KA_CHAT_THINKING must be one of {', '.join(THINKING_VALUES)}, "
                    f"got {thinking!r}"
                )

        return cls(
            api_key=get("CO_API_KEY"),
            chat_model=get("KA_CHAT_MODEL") or DEFAULT_CHAT_MODEL,
            embed_model=get("KA_EMBED_MODEL") or DEFAULT_EMBED_MODEL,
            rerank_model=get("KA_RERANK_MODEL") or DEFAULT_RERANK_MODEL,
            temperature=_number(get, "KA_LLM_TEMPERATURE", DEFAULT_TEMPERATURE, minimum=0),
            timeout_seconds=_number(
                get, "KA_LLM_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS, minimum=0, strict=True
            ),
            max_retries=_integer(get, "KA_LLM_MAX_RETRIES", DEFAULT_MAX_RETRIES),
            chat_thinking=thinking,
            event_log=Path(get("KA_EVENT_LOG") or DEFAULT_EVENT_LOG),
        )

    @property
    def models(self) -> ModelIds:
        return ModelIds(chat=self.chat_model, embed=self.embed_model, rerank=self.rerank_model)

    def require_api_key(self) -> str:
        """Return the API key, or raise ``LLMConfigError`` with the setup hint."""
        if not self.api_key:
            raise LLMConfigError(MISSING_KEY_HINT)
        return self.api_key


def _number(get, name: str, default: float, *, minimum: float, strict: bool = False) -> float:
    raw = get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        raise LLMConfigError(f"{name} must be a number, got {raw!r}") from None
    if not math.isfinite(value) or value < minimum or (strict and value == minimum):
        relation = "greater than" if strict else "at least"
        raise LLMConfigError(f"{name} must be {relation} {minimum:g}, got {raw!r}")
    return value


def _integer(get, name: str, default: int) -> int:
    raw = get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise LLMConfigError(f"{name} must be a whole number, got {raw!r}") from None
    if value < 0:
        raise LLMConfigError(f"{name} must be at least 0, got {raw!r}")
    return value
