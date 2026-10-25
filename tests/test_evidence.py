import pytest

from knowledge_automata.core.evidence import (
    DEFAULT_MIN_CHARS,
    check_evidence,
    normalize_quote,
    normalize_text,
)

# Typographic characters are written as escapes so the test data is unambiguous.
ARTIFACT = (
    "Steering group, 12 March 2026.\n"
    "Decision: we will buy the drip irrigation kit from supplier A, because they\n"
    "guarantee  delivery before the April planting.\n"
    "Tom said \u201cthe city\u2019s permits office may delay the water connection\u201d.\n"
    "Supplier B \u2014 cheaper but unreliable \u2014 is rejected for this season.\n"
    "Budget range: 400\u2013600 euros.\n"
    "Next\u00a0review on\u00a0Friday\u2026 if the permit arrives.\n"
)


def passes(quote: str, artifact: str = ARTIFACT) -> bool:
    [result] = check_evidence([quote], artifact)
    return result.passed


def test_exact_quote_passes():
    quote = "Supplier B \u2014 cheaper but unreliable \u2014 is rejected"
    [result] = check_evidence([quote], ARTIFACT)
    assert result.passed
    assert result.reason == "found in the artifact"


@pytest.mark.parametrize(
    "quote",
    [
        pytest.param("the city's permits office may delay", id="straight-apostrophe"),
        pytest.param('Tom said "the city\u2019s permits office', id="straight-double-quotes"),
        pytest.param(
            "because they guarantee delivery before the April planting", id="line-break-and-spaces"
        ),
        pytest.param("because they\n\nguarantee   delivery", id="extra-whitespace-in-quote"),
        pytest.param("Supplier B - cheaper but unreliable - is rejected", id="em-dash-as-hyphen"),
        pytest.param("Budget range: 400-600 euros", id="en-dash-as-hyphen"),
        pytest.param("Budget range: 400\u2212600 euros", id="minus-sign-as-hyphen"),
        pytest.param("Next review on Friday... if the permit", id="nbsp-and-ellipsis"),
        pytest.param("WE WILL BUY THE DRIP IRRIGATION KIT", id="case"),
        pytest.param('"we will buy the drip irrigation kit"', id="surrounding-straight-quotes"),
        pytest.param("\u201cwe will buy the drip irrigation kit\u201d", id="curly-quotes-around"),
        pytest.param("we will buy the drip irrigation kit...", id="trailing-ellipsis"),
        pytest.param("...we will buy the drip irrigation kit", id="leading-ellipsis"),
        pytest.param("we will buy the drip irrigation kit\u2026", id="trailing-ellipsis-character"),
        pytest.param('"...we will buy the drip irrigation kit..."', id="quotes-and-ellipses"),
        pytest.param("  we will buy the drip irrigation kit  ", id="surrounding-spaces"),
    ],
)
def test_formatting_differences_pass(quote):
    assert passes(quote)


def test_paraphrase_fails():
    quote = "We decided to purchase the irrigation kit from supplier A"
    [result] = check_evidence([quote], ARTIFACT)
    assert not result.passed
    assert result.reason == "not found in the artifact"


def test_quote_joining_separate_sentences_fails():
    assert not passes("we will buy the drip irrigation kit. Supplier B is rejected")


def test_short_quote_fails_even_when_present():
    [result] = check_evidence(["supplier A"], ARTIFACT)
    assert not result.passed
    assert result.reason.startswith("too short: 10 characters")


def test_quote_at_minimum_length_passes():
    quote = "the city's p"
    assert len(quote) == DEFAULT_MIN_CHARS
    assert passes(quote)


@pytest.mark.parametrize("quote", ["", "   ", '"..."', "\u2026"])
def test_empty_quotes_fail(quote):
    assert not passes(quote)


def test_min_chars_is_configurable():
    assert check_evidence(["supplier A"], ARTIFACT, min_chars=5)[0].passed


def test_one_result_per_quote_in_order():
    quotes = [
        "we will buy the drip irrigation kit",
        "we will rent the drip irrigation kit",
        "is rejected for this season",
    ]
    results = check_evidence(quotes, ARTIFACT)
    assert [result.quote for result in results] == quotes
    assert [result.passed for result in results] == [True, False, True]


def test_normalization_is_consistent_for_text_and_quotes():
    text = "\u201cIt\u2019s\u00a0done \u2014\nOK\u2026\u201d"
    assert normalize_text(text) == '"it\'s done - ok..."'
    assert normalize_quote(text) == "it's done - ok"


def test_empty_artifact_fails_every_quote():
    assert not passes("we will buy the drip irrigation kit", artifact="")
