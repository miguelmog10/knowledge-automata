"""``build_llm``: the one way callers get a working, observed LLM (ADR-0012)."""

from typing import Any

from knowledge_automata.llm.cohere_adapter import RESPONSE_SCHEMA_FIELD, CohereAdapter
from knowledge_automata.llm.observed import EventSink, JsonlFileSink, ObservedLLM
from knowledge_automata.llm.pricing import load_price_table
from knowledge_automata.llm.settings import LLMSettings


def build_llm(
    settings: LLMSettings | None = None,
    *,
    run_id: str | None = None,
    sink: EventSink | None = None,
    client: Any = None,
    schema_field: str = RESPONSE_SCHEMA_FIELD,
) -> ObservedLLM:
    """Wire the Cohere adapter, the observation wrapper, the event log and the prices.

    ``settings`` defaults to ``LLMSettings.from_env()``. Every event carries ``run_id``,
    a new UUID 4 when None; pass the same one to group several builds into one run.
    Events go to ``sink``, or append to ``settings.event_log`` (relative to the working
    directory). ``client`` and
    ``schema_field`` exist for tests and the smoke check. Raises ``LLMConfigError`` when
    the API key is missing.
    """
    if settings is None:
        settings = LLMSettings.from_env()
    adapter = CohereAdapter(settings, client=client, schema_field=schema_field)
    return ObservedLLM(
        adapter,
        provider=adapter.provider,
        sink=sink if sink is not None else JsonlFileSink(settings.event_log),
        run_id=run_id,
        prices=load_price_table(),
    )
