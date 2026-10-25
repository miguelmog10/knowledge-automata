"""The Cohere adapter: the only module that imports the Cohere SDK (ADR-0003, ADR-0012).

It also imports ``httpx``, the SDK's transport, because the SDK lets timeouts and
network errors through unwrapped. Retries for 408, 409, 429 and 5xx responses and for
connection errors are the SDK's own, bounded by ``KA_LLM_MAX_RETRIES``; there is no
second retry loop here.
"""

import json
import math
from collections.abc import Mapping, Sequence
from typing import Any

import cohere
import httpx
from cohere.core.api_error import ApiError

from knowledge_automata.llm.errors import (
    LLMAuthError,
    LLMError,
    LLMRateLimitError,
    LLMRequestError,
    LLMResponseError,
    LLMUnavailableError,
)
from knowledge_automata.llm.interfaces import (
    CallContext,
    ChatResult,
    EmbedResult,
    InputType,
    RankedDocument,
    RerankResult,
    Usage,
)
from knowledge_automata.llm.provider_schema import to_cohere_schema
from knowledge_automata.llm.settings import LLMSettings

PROVIDER = "cohere"
# Cohere's structured outputs guide names the field "schema"; the SDK and the API
# reference name it "json_schema". The smoke check settles which one is enforced.
RESPONSE_SCHEMA_FIELD = "schema"
# Cohere's documented maximum number of texts per embed call.
EMBED_BATCH_SIZE = 96
COHERE_INPUT_TYPES: dict[str, str] = {"document": "search_document", "query": "search_query"}
_MAX_PROVIDER_MESSAGE = 500


class CohereAdapter:
    """Implements ChatModel, EmbeddingModel and RerankModel with ``cohere.ClientV2``."""

    provider = PROVIDER

    def __init__(
        self,
        settings: LLMSettings,
        *,
        client: Any = None,
        schema_field: str = RESPONSE_SCHEMA_FIELD,
    ) -> None:
        self.settings = settings
        self.models = settings.models
        self.schema_field = schema_field
        if client is None:
            client = cohere.ClientV2(
                api_key=settings.require_api_key(),
                timeout=settings.timeout_seconds,
                max_retries=settings.max_retries,
            )
        self._client = client

    def chat_json(
        self, *, system: str, user: str, schema: Mapping[str, Any], context: CallContext
    ) -> ChatResult:
        request: dict[str, Any] = {
            "model": self.models.chat,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.settings.temperature,
            "response_format": {
                "type": "json_object",
                self.schema_field: to_cohere_schema(schema),
            },
        }
        if self.settings.chat_thinking is not None:
            request["thinking"] = {"type": self.settings.chat_thinking}
        response = self._call(self._client.chat, **request)

        billed = getattr(getattr(response, "usage", None), "billed_units", None)
        usage = Usage(
            input_tokens=_units(getattr(billed, "input_tokens", None)),
            output_tokens=_units(getattr(billed, "output_tokens", None)),
        )
        finish_reason = getattr(response, "finish_reason", None)
        if finish_reason == "MAX_TOKENS":
            raise LLMResponseError(
                "The chat response was truncated at the token limit (finish_reason MAX_TOKENS)",
                usage=usage,
            )
        if finish_reason not in (None, "COMPLETE"):
            raise LLMResponseError(
                f"The chat response did not complete (finish_reason {finish_reason})",
                usage=usage,
            )
        return ChatResult(
            data=_parse_json_object(response, usage),
            model=self.models.chat,
            usage=usage,
            finish_reason=finish_reason,
        )

    def embed(
        self, texts: Sequence[str], *, input_type: InputType, context: CallContext
    ) -> EmbedResult:
        if input_type not in COHERE_INPUT_TYPES:
            raise ValueError(f"input_type must be 'document' or 'query', got {input_type!r}")
        texts = list(texts)
        vectors: list[list[float]] = []
        billed_tokens: list[int | None] = []
        for start in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[start : start + EMBED_BATCH_SIZE]
            response = self._call(
                self._client.embed,
                model=self.models.embed,
                input_type=COHERE_INPUT_TYPES[input_type],
                texts=batch,
                embedding_types=["float"],
            )
            billed = getattr(getattr(response, "meta", None), "billed_units", None)
            billed_tokens.append(_units(getattr(billed, "input_tokens", None)))
            batch_vectors = getattr(getattr(response, "embeddings", None), "float_", None)
            if batch_vectors is None or len(batch_vectors) != len(batch):
                raise LLMResponseError(
                    f"Cohere returned {0 if batch_vectors is None else len(batch_vectors)} "
                    f"embeddings for {len(batch)} texts",
                    usage=Usage(input_tokens=_sum(billed_tokens)),
                )
            vectors.extend([float(x) for x in vector] for vector in batch_vectors)
        return EmbedResult(
            vectors=vectors, model=self.models.embed, usage=Usage(input_tokens=_sum(billed_tokens))
        )

    def rerank(
        self, query: str, documents: Sequence[str], *, top_n: int, context: CallContext
    ) -> RerankResult:
        if top_n < 1:
            raise ValueError(f"top_n must be at least 1, got {top_n}")
        documents = list(documents)
        if not documents:
            return RerankResult(results=[], model=self.models.rerank, usage=Usage())
        response = self._call(
            self._client.rerank,
            model=self.models.rerank,
            query=query,
            documents=documents,
            top_n=min(top_n, len(documents)),
        )
        billed = getattr(getattr(response, "meta", None), "billed_units", None)
        usage = Usage(
            input_tokens=_units(getattr(billed, "input_tokens", None)),
            search_units=_units(getattr(billed, "search_units", None)),
        )
        results = []
        for item in getattr(response, "results", None) or []:
            index, score = getattr(item, "index", None), getattr(item, "relevance_score", None)
            if not isinstance(index, int) or not 0 <= index < len(documents) or score is None:
                raise LLMResponseError(
                    "Cohere returned a rerank result without a valid index or score", usage=usage
                )
            results.append(RankedDocument(index=index, score=float(score)))
        results.sort(key=lambda result: (-result.score, result.index))
        return RerankResult(results=results[:top_n], model=self.models.rerank, usage=usage)

    def _call(self, method: Any, **kwargs: Any) -> Any:
        try:
            return method(**kwargs)
        except ApiError as exc:
            raise self._map_api_error(exc) from None
        except httpx.TimeoutException:
            raise LLMUnavailableError(
                f"Cohere did not respond within {self.settings.timeout_seconds:g} seconds"
            ) from None
        except httpx.TransportError as exc:
            raise LLMUnavailableError(
                f"Could not reach Cohere ({type(exc).__name__}) after "
                f"{self.settings.max_retries} retries"
            ) from None

    def _map_api_error(self, exc: ApiError) -> LLMError:
        status = exc.status_code
        message = self._provider_message(exc.body)
        detail = f": {message}" if message else ""
        if status in (401, 403, 498):
            return LLMAuthError(
                f"Cohere rejected the API key (HTTP {status}). Check CO_API_KEY in .env."
            )
        if status == 402:
            return LLMRateLimitError(
                f"Cohere's billing limit for this key is reached (HTTP 402){detail}",
                monthly_cap=True,
            )
        if status == 429:
            # Heuristic: Cohere documents no exact wording for the trial monthly cap, and its
            # per-minute trial message also says "Trial key", so only "month" marks the cap.
            monthly_cap = "month" in message.lower()
            limit = "monthly call cap" if monthly_cap else "rate limit"
            return LLMRateLimitError(
                f"Cohere {limit} reached (HTTP 429) after {self.settings.max_retries} "
                f"retries{detail}",
                monthly_cap=monthly_cap,
            )
        if status is None or status in (408, 499) or status >= 500:
            return LLMUnavailableError(
                f"Cohere is unavailable (HTTP {status}) after {self.settings.max_retries} retries"
            )
        return LLMRequestError(f"Cohere rejected the request (HTTP {status}){detail}")

    def _provider_message(self, body: Any) -> str:
        if isinstance(body, Mapping):
            body = body.get("message", "")
        message = body if isinstance(body, str) else ""
        if self.settings.api_key:
            message = message.replace(self.settings.api_key, "[redacted]")
        return message[:_MAX_PROVIDER_MESSAGE]


def _parse_json_object(response: Any, usage: Usage) -> dict[str, Any]:
    # Reasoning models such as Command A+ may put a thinking block before the text block.
    content = getattr(getattr(response, "message", None), "content", None) or []
    text = next((item.text for item in content if getattr(item, "type", None) == "text"), None)
    if text is None:
        raise LLMResponseError("The chat response has no text content", usage=usage)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        # The position only: the output may quote artifact text.
        raise LLMResponseError(
            f"The chat response is not valid JSON (line {exc.lineno}, column {exc.colno})",
            usage=usage,
        ) from None
    if not isinstance(data, dict):
        raise LLMResponseError(
            f"The chat response is a JSON {_JSON_TYPES.get(type(data), 'value')}, not an object",
            usage=usage,
        )
    return data


_JSON_TYPES: dict[type, str] = {
    list: "array",
    str: "string",
    int: "number",
    float: "number",
    bool: "boolean",
    type(None): "null",
}


def _units(value: Any) -> int | None:
    """Billed units arrive as numbers that may be floats; round up to whole units."""
    if value is None:
        return None
    return math.ceil(float(value))


def _sum(values: list[int | None]) -> int | None:
    known = [value for value in values if value is not None]
    return sum(known) if known else None
