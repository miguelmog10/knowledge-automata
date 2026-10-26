"""The Cohere adapter: the only module that imports the Cohere SDK (ADR-0003, ADR-0012).

It also imports ``httpx``, the SDK's transport, because the SDK lets timeouts and
network errors through unwrapped. Retries for 408, 409, 429 and 5xx responses and for
connection errors are the SDK's own, bounded by ``KA_LLM_MAX_RETRIES``; there is no
second retry loop here.
"""

import dataclasses
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
# The structured outputs guide names the field "schema", the SDK and the API reference
# "json_schema". The smoke check of 2026-10-25 found both enforced, but SDK 7.3 logs an
# "experimental feature" warning for "schema" only, so the documented field is used.
# Re-run the smoke check after each SDK upgrade: it tests both names.
RESPONSE_SCHEMA_FIELD = "json_schema"
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

        usage = _read_usage(getattr(response, "usage", None))
        request_id = _request_id(response)
        finish_reason = getattr(response, "finish_reason", None)
        if finish_reason == "MAX_TOKENS":
            raise LLMResponseError(
                "The chat response was truncated at the token limit (finish_reason MAX_TOKENS)",
                usage=usage,
                request_id=request_id,
            )
        if finish_reason not in (None, "COMPLETE"):
            raise LLMResponseError(
                f"The chat response did not complete (finish_reason {finish_reason})",
                usage=usage,
                request_id=request_id,
            )
        return ChatResult(
            data=_parse_json_object(response, usage, request_id),
            model=self.models.chat,
            usage=usage,
            finish_reason=finish_reason,
            request_id=request_id,
        )

    def embed(
        self, texts: Sequence[str], *, input_type: InputType, context: CallContext
    ) -> EmbedResult:
        """Embed ``texts`` in batches of at most 96.

        Usage is summed over the batches; ``request_id`` lists the batch response IDs,
        separated by commas, when there is more than one batch.
        """
        if input_type not in COHERE_INPUT_TYPES:
            raise ValueError(f"input_type must be 'document' or 'query', got {input_type!r}")
        texts = list(texts)
        vectors: list[list[float]] = []
        usages: list[Usage] = []
        request_ids: list[str] = []
        for start in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[start : start + EMBED_BATCH_SIZE]
            response = self._call(
                self._client.embed,
                model=self.models.embed,
                input_type=COHERE_INPUT_TYPES[input_type],
                texts=batch,
                embedding_types=["float"],
            )
            usages.append(_read_usage(getattr(response, "meta", None)))
            if (request_id := _request_id(response)) is not None:
                request_ids.append(request_id)
            batch_vectors = getattr(getattr(response, "embeddings", None), "float_", None)
            if batch_vectors is None or len(batch_vectors) != len(batch):
                raise LLMResponseError(
                    f"Cohere returned {0 if batch_vectors is None else len(batch_vectors)} "
                    f"embeddings for {len(batch)} texts",
                    usage=_sum_usage(usages),
                    request_id=",".join(request_ids) or None,
                )
            vectors.extend([float(x) for x in vector] for vector in batch_vectors)
        return EmbedResult(
            vectors=vectors,
            model=self.models.embed,
            usage=_sum_usage(usages),
            request_id=",".join(request_ids) or None,
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
        usage = _read_usage(getattr(response, "meta", None))
        request_id = _request_id(response)
        results = []
        for item in getattr(response, "results", None) or []:
            index, score = getattr(item, "index", None), getattr(item, "relevance_score", None)
            if not isinstance(index, int) or not 0 <= index < len(documents) or score is None:
                raise LLMResponseError(
                    "Cohere returned a rerank result without a valid index or score",
                    usage=usage,
                    request_id=request_id,
                )
            results.append(RankedDocument(index=index, score=float(score)))
        results.sort(key=lambda result: (-result.score, result.index))
        return RerankResult(
            results=results[:top_n], model=self.models.rerank, usage=usage, request_id=request_id
        )

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


def _parse_json_object(response: Any, usage: Usage, request_id: str | None) -> dict[str, Any]:
    # Reasoning models such as Command A+ may put a thinking block before the text block.
    content = getattr(getattr(response, "message", None), "content", None) or []
    text = next((item.text for item in content if getattr(item, "type", None) == "text"), None)
    if text is None:
        raise LLMResponseError(
            "The chat response has no text content", usage=usage, request_id=request_id
        )
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        # The position only: the output may quote artifact text.
        raise LLMResponseError(
            f"The chat response is not valid JSON (line {exc.lineno}, column {exc.colno})",
            usage=usage,
            request_id=request_id,
        ) from None
    if not isinstance(data, dict):
        raise LLMResponseError(
            f"The chat response is a JSON {_JSON_TYPES.get(type(data), 'value')}, not an object",
            usage=usage,
            request_id=request_id,
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


def _read_usage(container: Any) -> Usage:
    """Read ``billed_units`` and raw ``tokens`` from chat ``usage`` or embed/rerank ``meta``."""
    billed = getattr(container, "billed_units", None)
    raw = getattr(container, "tokens", None)
    return Usage(
        input_tokens=_units(getattr(billed, "input_tokens", None)),
        output_tokens=_units(getattr(billed, "output_tokens", None)),
        search_units=_units(getattr(billed, "search_units", None)),
        raw_input_tokens=_units(getattr(raw, "input_tokens", None)),
        raw_output_tokens=_units(getattr(raw, "output_tokens", None)),
    )


def _request_id(response: Any) -> str | None:
    value = getattr(response, "id", None)
    return value if isinstance(value, str) and value else None


def _units(value: Any) -> int | None:
    """Units arrive as numbers that may be floats; round up to whole units."""
    if value is None:
        return None
    return math.ceil(float(value))


def _sum_usage(usages: list[Usage]) -> Usage:
    """Add up per-batch usage; a unit no batch reported stays None."""

    def total(name: str) -> int | None:
        known = [value for usage in usages if (value := getattr(usage, name)) is not None]
        return sum(known) if known else None

    return Usage(**{field.name: total(field.name) for field in dataclasses.fields(Usage)})
