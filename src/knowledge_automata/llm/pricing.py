"""The dated price table and cost estimates from billed units (ADR-0012).

Prices are strings in ``prices.toml`` and are computed with ``Decimal``. A model without a
published price is left out of the table, and its cost is ``None`` rather than a guess.
"""

import logging
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from importlib import resources
from pathlib import Path
from typing import Any

from knowledge_automata.llm.interfaces import Usage

logger = logging.getLogger(__name__)

PRICE_FIELDS = (
    "input_per_million_tokens",
    "output_per_million_tokens",
    "per_thousand_search_units",
    "per_million_tokens",
)
_PRICE = re.compile(r"[0-9]+(\.[0-9]+)?")
_MILLION = Decimal(1_000_000)
_THOUSAND = Decimal(1_000)


@dataclass(frozen=True)
class ModelPrice:
    input_per_million_tokens: Decimal | None = None
    output_per_million_tokens: Decimal | None = None
    per_thousand_search_units: Decimal | None = None
    # Rerank models priced per token rather than per search unit.
    per_million_tokens: Decimal | None = None


@dataclass(frozen=True)
class PriceTable:
    checked_on: date
    source: str
    currency: str
    models: Mapping[str, ModelPrice]
    _warned: set[str] = field(default_factory=set, init=False, repr=False, compare=False)


def parse_price_table(data: Mapping[str, Any]) -> PriceTable:
    """Build a PriceTable from parsed TOML, rejecting anything that is not a clean price."""
    unknown = set(data) - {"checked_on", "source", "currency", "models"}
    if unknown:
        raise ValueError(f"Unknown price table keys: {sorted(unknown)}")
    if data.get("currency") != "USD":
        raise ValueError(f"Price table currency must be USD, got {data.get('currency')!r}")
    try:
        checked_on = date.fromisoformat(str(data["checked_on"]))
    except (KeyError, ValueError):
        raise ValueError("Price table checked_on must be a date such as 2026-10-25") from None
    source = data.get("source")
    if not isinstance(source, str) or not source.startswith("https://"):
        raise ValueError("Price table source must be an https URL")
    models = {}
    for model, prices in (data.get("models") or {}).items():
        unknown = set(prices) - set(PRICE_FIELDS)
        if unknown:
            raise ValueError(f"Unknown price keys for {model}: {sorted(unknown)}")
        for key, value in prices.items():
            if not isinstance(value, str) or not _PRICE.fullmatch(value):
                raise ValueError(f"Price {model}.{key} must be a decimal string, got {value!r}")
        if not prices:
            raise ValueError(f"Model {model} has no prices; leave it out instead")
        models[model] = ModelPrice(**{key: Decimal(value) for key, value in prices.items()})
    return PriceTable(checked_on=checked_on, source=source, currency="USD", models=models)


def load_price_table(path: Path | None = None) -> PriceTable:
    """Load ``path``, or the table packaged with knowledge_automata when ``path`` is None."""
    if path is None:
        text = resources.files("knowledge_automata.llm").joinpath("prices.toml").read_text("utf-8")
    else:
        text = Path(path).read_text(encoding="utf-8")
    return parse_price_table(tomllib.loads(text))


def estimate_cost(model: str, usage: Usage, table: PriceTable) -> Decimal | None:
    """Return the cost in USD of ``usage`` on ``model``, or None if it cannot be priced.

    None means the model or a price for a billed unit is missing, or the provider reported
    no billed units. Unknown models are logged once per table.
    """
    price = table.models.get(model)
    if price is None:
        if model not in table._warned:
            table._warned.add(model)
            logger.warning(
                "No price for model %s in the price table checked on %s; cost is omitted",
                model,
                table.checked_on,
            )
        return None

    if price.per_thousand_search_units is not None:
        if usage.search_units is None:
            return None
        return usage.search_units * price.per_thousand_search_units / _THOUSAND

    if usage.input_tokens is None and usage.output_tokens is None:
        return None
    cost = Decimal(0)
    if usage.input_tokens is not None:
        rate = price.input_per_million_tokens
        if rate is None:
            rate = price.per_million_tokens
        if rate is None:
            return None
        cost += usage.input_tokens * rate / _MILLION
    if usage.output_tokens is not None:
        if price.output_per_million_tokens is None:
            return None
        cost += usage.output_tokens * price.output_per_million_tokens / _MILLION
    return cost


def format_cost(cost: Decimal) -> str:
    """Plain decimal notation for the event log, never exponent form such as 1E-7."""
    return format(cost, "f")
