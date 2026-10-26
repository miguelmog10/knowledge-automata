"""FakeLLM: a deterministic, offline stand-in for every LLM interface, for tests."""

import copy
import hashlib
import json
import math
import re
from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from knowledge_automata.llm.interfaces import (
    CallContext,
    ChatResult,
    EmbedResult,
    InputType,
    ModelIds,
    RankedDocument,
    RerankResult,
    Usage,
)

PROVIDER = "fake"
FAKE_MODELS = ModelIds(chat="fake-chat", embed="fake-embed", rerank="fake-rerank")
EMBED_DIMENSIONS = 8
_WORD = re.compile(r"\w+")


@dataclass(frozen=True)
class FakeCall:
    operation: str
    context: CallContext
    inputs: dict[str, Any]


class FakeLLM:
    """Implements ChatModel, EmbeddingModel and RerankModel with no network and no randomness.

    ``chat_responses`` are returned in order; an exception in the list is raised instead.
    Every call is recorded in ``calls``.
    """

    provider = PROVIDER

    def __init__(
        self,
        chat_responses: Iterable[Mapping[str, Any] | BaseException] = (),
        *,
        models: ModelIds = FAKE_MODELS,
    ) -> None:
        responses = list(chat_responses)
        for item in responses:
            if not isinstance(item, Mapping | BaseException):
                raise TypeError(f"Scripted chat responses must be dicts or exceptions: {item!r}")
        self._chat_responses = deque(responses)
        self.models = models
        self.calls: list[FakeCall] = []

    def chat_json(
        self, *, system: str, user: str, schema: Mapping[str, Any], context: CallContext
    ) -> ChatResult:
        self.calls.append(
            FakeCall("chat", context, {"system": system, "user": user, "schema": schema})
        )
        chat_calls = sum(call.operation == "chat" for call in self.calls)
        if not self._chat_responses:
            raise AssertionError(
                f"FakeLLM ran out of scripted chat responses at chat call {chat_calls}"
            )
        item = self._chat_responses.popleft()
        if isinstance(item, BaseException):
            raise item
        data = copy.deepcopy(dict(item))
        usage = Usage(
            input_tokens=_tokens(system) + _tokens(user),
            output_tokens=_tokens(json.dumps(data)),
        )
        return ChatResult(data=data, model=self.models.chat, usage=usage, finish_reason="COMPLETE")

    def embed(
        self, texts: Sequence[str], *, input_type: InputType, context: CallContext
    ) -> EmbedResult:
        if input_type not in ("document", "query"):
            raise ValueError(f"input_type must be 'document' or 'query', got {input_type!r}")
        texts = list(texts)
        self.calls.append(FakeCall("embed", context, {"texts": texts, "input_type": input_type}))
        return EmbedResult(
            vectors=[_vector(text) for text in texts],
            model=self.models.embed,
            usage=Usage(input_tokens=sum(_tokens(text) for text in texts)),
        )

    def rerank(
        self, query: str, documents: Sequence[str], *, top_n: int, context: CallContext
    ) -> RerankResult:
        if top_n < 1:
            raise ValueError(f"top_n must be at least 1, got {top_n}")
        documents = list(documents)
        self.calls.append(
            FakeCall("rerank", context, {"query": query, "documents": documents, "top_n": top_n})
        )
        query_words = _words(query)
        ranked = sorted(
            (
                RankedDocument(index=index, score=_jaccard(query_words, _words(document)))
                for index, document in enumerate(documents)
            ),
            key=lambda result: (-result.score, result.index),
        )
        return RerankResult(
            results=ranked[:top_n],
            model=self.models.rerank,
            usage=Usage(search_units=1 if documents else 0),
        )


def _tokens(text: str) -> int:
    return math.ceil(len(text) / 4)


def _vector(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    raw = [int.from_bytes(digest[i : i + 4], "big") / 2**31 - 1 for i in range(0, 32, 4)]
    norm = math.sqrt(sum(x * x for x in raw)) or 1.0
    return [x / norm for x in raw]


def _words(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0
