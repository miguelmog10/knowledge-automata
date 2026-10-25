"""Observation: one metadata-only event per LLM call (ADR-0012).

Events hold timing, model, billed units, estimated cost and the caller's context. They
never hold prompts, artifact text, model output or keys, so the log is safe to keep and
cannot become an unvalidated second copy of the institutional memory.
"""

import functools
import json
import re
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, TypeVar, runtime_checkable

from knowledge_automata.core.schemas import LLM_EVENT_SCHEMA, load_schema
from knowledge_automata.core.validation import validate_llm_event
from knowledge_automata.llm.interfaces import (
    CallContext,
    ChatResult,
    EmbedResult,
    InputType,
    ModelIds,
    Operation,
    RerankResult,
    Usage,
)
from knowledge_automata.llm.pricing import PriceTable, estimate_cost, format_cost

_PROVIDER = re.compile(r"[a-z][a-z0-9-]*")
_Result = TypeVar("_Result", ChatResult, EmbedResult, RerankResult)
_UNITS = ("input_tokens", "output_tokens", "raw_input_tokens", "raw_output_tokens", "search_units")


@functools.cache
def event_schema_version() -> str:
    """The ``MAJOR.MINOR`` version of the event schema, written into every event."""
    return load_schema(LLM_EVENT_SCHEMA)["x-version"]


@runtime_checkable
class EventSink(Protocol):
    def emit(self, event: dict[str, Any]) -> None: ...


class JsonlFileSink:
    """An append-only JSON Lines log that survives across runs.

    For each event it opens the file in append mode, writes one UTF-8 line and closes it,
    creating the folder and the file if they are missing. It never truncates, rewrites or
    rotates the file. One writing process at a time is assumed in v0.1.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def emit(self, event: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as file:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")


class MemorySink:
    """Keeps events in a list, for tests and for the smoke check report."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def emit(self, event: dict[str, Any]) -> None:
        self.events.append(event)


def utc_now() -> datetime:
    return datetime.now(UTC)


class ObservedLLM:
    """Wraps an adapter, fake included, and emits one validated event per interface call.

    ``inner`` must implement the three interfaces and expose ``models`` (ModelIds), so a
    failed call is still logged with the model it was meant for. Exceptions from ``inner``
    are logged with ``status: "error"`` and re-raised unchanged. Every event carries
    ``run_id`` (a UUID grouping the calls of one run; a new one when None).
    """

    def __init__(
        self,
        inner: Any,
        *,
        provider: str,
        sink: EventSink,
        run_id: str | None = None,
        prices: PriceTable | None = None,
        clock: Callable[[], datetime] = utc_now,
        timer: Callable[[], float] = time.perf_counter,
    ) -> None:
        if not _PROVIDER.fullmatch(provider):
            raise ValueError(f"provider must be lowercase words joined by hyphens: {provider!r}")
        if not isinstance(inner.models, ModelIds):
            raise TypeError("The wrapped adapter must expose models as ModelIds")
        try:
            self.run_id = str(uuid.UUID(run_id)) if run_id is not None else str(uuid.uuid4())
        except (TypeError, ValueError, AttributeError):
            raise ValueError(f"run_id must be a UUID, got {run_id!r}") from None
        self.inner = inner
        self.provider = provider
        self.models: ModelIds = inner.models
        self.sink = sink
        self.prices = prices
        self._clock = clock
        self._timer = timer

    def chat_json(
        self, *, system: str, user: str, schema: Mapping[str, Any], context: CallContext
    ) -> ChatResult:
        return self._observe(
            "chat",
            context,
            1,
            lambda: self.inner.chat_json(system=system, user=user, schema=schema, context=context),
        )

    def embed(
        self, texts: Sequence[str], *, input_type: InputType, context: CallContext
    ) -> EmbedResult:
        texts = list(texts)
        return self._observe(
            "embed",
            context,
            len(texts),
            lambda: self.inner.embed(texts, input_type=input_type, context=context),
        )

    def rerank(
        self, query: str, documents: Sequence[str], *, top_n: int, context: CallContext
    ) -> RerankResult:
        documents = list(documents)
        return self._observe(
            "rerank",
            context,
            len(documents),
            lambda: self.inner.rerank(query, documents, top_n=top_n, context=context),
        )

    def _observe(
        self,
        operation: Operation,
        context: CallContext,
        items: int,
        call: Callable[[], _Result],
    ) -> _Result:
        start = self._timer()
        try:
            result = call()
        except Exception as exc:
            usage = getattr(exc, "usage", None)
            request_id = getattr(exc, "request_id", None)
            self._emit(
                operation,
                context,
                items,
                latency_seconds=self._timer() - start,
                model=self.models.for_operation(operation),
                usage=usage if isinstance(usage, Usage) else Usage(),
                request_id=request_id if isinstance(request_id, str) else None,
                error_type=type(exc).__name__,
            )
            raise
        self._emit(
            operation,
            context,
            items,
            latency_seconds=self._timer() - start,
            model=result.model,
            usage=result.usage,
            request_id=result.request_id,
        )
        return result

    def _emit(
        self,
        operation: Operation,
        context: CallContext,
        items: int,
        *,
        latency_seconds: float,
        model: str,
        usage: Usage,
        request_id: str | None = None,
        error_type: str | None = None,
    ) -> None:
        event: dict[str, Any] = {
            "schema_version": event_schema_version(),
            "ts": _timestamp(self._clock()),
            "event_id": str(uuid.uuid4()),
            "run_id": self.run_id,
        }
        if request_id:
            event["request_id"] = request_id
        event |= {
            "provider": self.provider,
            "model": model,
            "operation": operation,
            "agent": context.agent,
        }
        if context.artifact_id is not None:
            event["artifact_id"] = context.artifact_id
        if context.prompt_version is not None:
            event["prompt_version"] = context.prompt_version
        event["status"] = "ok" if error_type is None else "error"
        if error_type is not None:
            event["error_type"] = error_type
        event["latency_ms"] = max(0, round(latency_seconds * 1000))
        event["items"] = items
        for name in _UNITS:
            value = getattr(usage, name)
            if value is not None:
                event[name] = value
        if self.prices is not None:
            cost = estimate_cost(model, usage, self.prices)
            if cost is not None:
                event["cost_usd"] = format_cost(cost)
                event["price_table"] = self.prices.checked_on.isoformat()

        validation = validate_llm_event(event)
        if not validation.ok:
            # A bug in this module, not in the caller's data: CallContext and the adapters
            # already guarantee the shapes the schema checks.
            raise ValueError(f"Invalid LLM event: {'; '.join(validation.errors)}")
        self.sink.emit(event)


def _timestamp(moment: datetime) -> str:
    if moment.tzinfo is None:
        raise ValueError("The event clock must return timezone-aware datetimes")
    return moment.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
