"""The LLM service layer (ADR-0003, ADR-0012).

The only place that talks to an LLM provider. Callers use the interfaces and results
exported here; only ``cohere_adapter`` imports the Cohere SDK.
"""

from knowledge_automata.llm.errors import (
    LLMAuthError,
    LLMConfigError,
    LLMError,
    LLMRateLimitError,
    LLMRequestError,
    LLMResponseError,
    LLMUnavailableError,
)
from knowledge_automata.llm.interfaces import (
    CallContext,
    ChatModel,
    ChatResult,
    EmbeddingModel,
    EmbedResult,
    ModelIds,
    RankedDocument,
    RerankModel,
    RerankResult,
    Usage,
)
from knowledge_automata.llm.observed import EventSink, JsonlFileSink, MemorySink, ObservedLLM
from knowledge_automata.llm.pricing import PriceTable, estimate_cost, load_price_table
from knowledge_automata.llm.settings import LLMSettings

__all__ = [
    "CallContext",
    "ChatModel",
    "ChatResult",
    "EmbedResult",
    "EmbeddingModel",
    "EventSink",
    "JsonlFileSink",
    "LLMAuthError",
    "LLMConfigError",
    "LLMError",
    "LLMRateLimitError",
    "LLMRequestError",
    "LLMResponseError",
    "LLMSettings",
    "LLMUnavailableError",
    "MemorySink",
    "ModelIds",
    "ObservedLLM",
    "PriceTable",
    "RankedDocument",
    "RerankModel",
    "RerankResult",
    "Usage",
    "estimate_cost",
    "load_price_table",
]
