"""Provider-neutral interfaces for chat, embeddings and reranking (ADR-0003, ADR-0012).

Callers depend only on these types. Chat is structured only in v0.1: ``chat_json`` returns
a parsed JSON object, and validating it against a record schema stays with the caller.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable

Operation = Literal["chat", "embed", "rerank"]
InputType = Literal["document", "query"]

# Same shapes as schemas/core/llm-event.v1.json, checked when the context is created so a
# paid call can never fail event validation afterwards.
_AGENT = re.compile(r"[a-z][a-z0-9-]*")
_ARTIFACT_ID = re.compile(r"ART-[0-9]{4,}")


@dataclass(frozen=True)
class CallContext:
    """Who is calling and about what; copied into the call's event, never sent to the model."""

    agent: str
    artifact_id: str | None = None
    prompt_version: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.agent, str) or not _AGENT.fullmatch(self.agent):
            raise ValueError(
                f"CallContext.agent must be lowercase words joined by hyphens: {self.agent!r}"
            )
        if self.artifact_id is not None and (
            not isinstance(self.artifact_id, str) or not _ARTIFACT_ID.fullmatch(self.artifact_id)
        ):
            raise ValueError(
                f"CallContext.artifact_id must look like ART-0001: {self.artifact_id!r}"
            )
        if self.prompt_version is not None and (
            not isinstance(self.prompt_version, str) or not self.prompt_version
        ):
            raise ValueError("CallContext.prompt_version must be a non-empty string")


@dataclass(frozen=True)
class Usage:
    """Billed units; ``None`` when the provider does not report them."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    search_units: int | None = None


@dataclass(frozen=True)
class ChatResult:
    data: dict[str, Any]
    model: str
    usage: Usage
    finish_reason: str | None = None


@dataclass(frozen=True)
class EmbedResult:
    vectors: list[list[float]]  # one per input text, same order
    model: str
    usage: Usage


@dataclass(frozen=True)
class RankedDocument:
    index: int  # position in the input documents
    score: float


@dataclass(frozen=True)
class RerankResult:
    results: list[RankedDocument]  # best first, at most top_n
    model: str
    usage: Usage


@dataclass(frozen=True)
class ModelIds:
    """The model each operation uses, so failed calls can still be logged with a model."""

    chat: str
    embed: str
    rerank: str

    def for_operation(self, operation: Operation) -> str:
        return getattr(self, operation)


@runtime_checkable
class ChatModel(Protocol):
    def chat_json(
        self, *, system: str, user: str, schema: Mapping[str, Any], context: CallContext
    ) -> ChatResult: ...


@runtime_checkable
class EmbeddingModel(Protocol):
    def embed(
        self, texts: Sequence[str], *, input_type: InputType, context: CallContext
    ) -> EmbedResult: ...


@runtime_checkable
class RerankModel(Protocol):
    def rerank(
        self, query: str, documents: Sequence[str], *, top_n: int, context: CallContext
    ) -> RerankResult: ...
