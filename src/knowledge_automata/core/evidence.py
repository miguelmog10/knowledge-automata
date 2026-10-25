"""Evidence quote check: every quote in a draft must appear in its artifact (ADR-0011).

Also known as a grounding check (attribution to source text). The quote and the artifact
text are normalized the same way first, so a valid quote does not fail over formatting.
"""

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

DEFAULT_MIN_CHARS = 12

# Applied after NFKC, which already turns the ellipsis character into three dots and
# non-breaking spaces into spaces; they are listed anyway so the intent is explicit.
_TYPOGRAPHY = str.maketrans(
    {
        "\u2018": "'",  # left single quotation mark
        "\u2019": "'",  # right single quotation mark
        "\u201a": "'",  # single low-9 quotation mark
        "\u201b": "'",  # single high-reversed-9 quotation mark
        "\u201c": '"',  # left double quotation mark
        "\u201d": '"',  # right double quotation mark
        "\u201e": '"',  # double low-9 quotation mark
        "\u201f": '"',  # double high-reversed-9 quotation mark
        "\u2013": "-",  # en dash
        "\u2014": "-",  # em dash
        "\u2212": "-",  # minus sign
        "\u2026": "...",  # ellipsis
        "\u00a0": " ",  # non-breaking space
        "\u202f": " ",  # narrow non-breaking space
    }
)
_QUOTE_MARKS = "\"'"
_ELLIPSIS = "..."


@dataclass(frozen=True)
class QuoteCheck:
    """The result of checking one quote against the artifact text."""

    quote: str
    passed: bool
    reason: str


def normalize_text(text: str) -> str:
    """Normalize Unicode, quote marks, dashes, spaces and case, and collapse whitespace."""
    text = unicodedata.normalize("NFKC", text).translate(_TYPOGRAPHY).casefold()
    return " ".join(text.split())


def normalize_quote(quote: str) -> str:
    """Normalize a quote like artifact text, then strip surrounding quote marks and ellipses."""
    quote = normalize_text(quote)
    previous = None
    while quote != previous:
        previous = quote
        quote = quote.strip(_QUOTE_MARKS).strip()
        quote = quote.removeprefix(_ELLIPSIS).removesuffix(_ELLIPSIS).strip()
    return quote


def check_evidence(
    quotes: Sequence[str], artifact_text: str, min_chars: int = DEFAULT_MIN_CHARS
) -> list[QuoteCheck]:
    """Check each quote against the artifact text; return one result per quote, in order.

    A quote passes if, after normalization, it is at least ``min_chars`` long and appears
    in the normalized artifact text. Short quotes fail, because a quote like "yes" proves
    nothing.
    """
    artifact = normalize_text(artifact_text)
    results = []
    for quote in quotes:
        normalized = normalize_quote(quote)
        if len(normalized) < min_chars:
            reason = (
                f"too short: {len(normalized)} characters after normalization, minimum {min_chars}"
            )
            results.append(QuoteCheck(quote, False, reason))
        elif normalized not in artifact:
            results.append(QuoteCheck(quote, False, "not found in the artifact"))
        else:
            results.append(QuoteCheck(quote, True, "found in the artifact"))
    return results
