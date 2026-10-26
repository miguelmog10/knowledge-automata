from datetime import date
from decimal import Decimal

import pytest

from knowledge_automata.llm import Usage
from knowledge_automata.llm.pricing import (
    estimate_cost,
    format_cost,
    load_price_table,
    parse_price_table,
)

TEST_TABLE = {
    "checked_on": "2026-10-25",
    "source": "https://example.test/prices",
    "currency": "USD",
    "models": {
        "chat-model": {"input_per_million_tokens": "2.50", "output_per_million_tokens": "10.00"},
        "embed-model": {"input_per_million_tokens": "0.12"},
        "rerank-units": {"per_thousand_search_units": "2.00"},
        "rerank-tokens": {"per_million_tokens": "0.05"},
        "input-only": {"input_per_million_tokens": "1"},
    },
}


@pytest.fixture
def table():
    return parse_price_table(TEST_TABLE)


def test_the_packaged_table_loads_with_a_date_and_source():
    packaged = load_price_table()
    assert isinstance(packaged.checked_on, date)
    assert packaged.source == "https://cohere.com/pricing"
    assert packaged.currency == "USD"
    for price in packaged.models.values():
        assert any(value is not None for value in vars(price).values())


def test_a_table_file_can_be_loaded(tmp_path):
    path = tmp_path / "prices.toml"
    path.write_text(
        'checked_on = "2026-10-25"\nsource = "https://example.test"\ncurrency = "USD"\n'
        '[models."m"]\ninput_per_million_tokens = "3"\n',
        encoding="utf-8",
    )
    assert load_price_table(path).models["m"].input_per_million_tokens == Decimal("3")


@pytest.mark.parametrize(
    ("model", "usage", "expected"),
    [
        ("chat-model", Usage(input_tokens=1_000, output_tokens=500), "0.0075"),
        ("chat-model", Usage(input_tokens=1, output_tokens=0), "0.0000025"),
        ("embed-model", Usage(input_tokens=250_000), "0.03"),
        ("rerank-units", Usage(search_units=3), "0.006"),
        ("rerank-units", Usage(input_tokens=900, search_units=1), "0.002"),
        ("rerank-tokens", Usage(input_tokens=2_000_000), "0.1"),
    ],
)
def test_costs_use_exact_decimal_arithmetic(table, model, usage, expected):
    cost = estimate_cost(model, usage, table)
    assert isinstance(cost, Decimal)
    assert cost == Decimal(expected)


def test_costs_format_without_exponents(table):
    tiny = estimate_cost("chat-model", Usage(input_tokens=1), table)
    assert format_cost(tiny) == "0.0000025"
    assert format_cost(Decimal("1E-7")) == "0.0000001"


@pytest.mark.parametrize(
    ("model", "usage"),
    [
        ("chat-model", Usage()),
        ("input-only", Usage(input_tokens=10, output_tokens=5)),
        ("rerank-units", Usage(input_tokens=10)),
    ],
)
def test_missing_units_or_unit_prices_give_no_cost(table, model, usage):
    assert estimate_cost(model, usage, table) is None


def test_unknown_models_give_no_cost_and_warn_once(table, caplog):
    assert estimate_cost("mystery", Usage(input_tokens=5), table) is None
    assert estimate_cost("mystery", Usage(input_tokens=5), table) is None
    warnings = [r for r in caplog.records if "mystery" in r.getMessage()]
    assert len(warnings) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"currency": "EUR"},
        {"checked_on": "25/10/2026"},
        {"source": "http://example.test"},
        {"extra": 1},
        {"models": {"m": {"input_per_million_tokens": 2.5}}},
        {"models": {"m": {"input_per_million_tokens": "-1"}}},
        {"models": {"m": {"input_per_million_tokens": "1e-6"}}},
        {"models": {"m": {"per_token": "1"}}},
        {"models": {"m": {}}},
    ],
)
def test_bad_tables_are_rejected(changes):
    with pytest.raises(ValueError):
        parse_price_table({**TEST_TABLE, **changes})
