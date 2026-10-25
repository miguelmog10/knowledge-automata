"""Reduce a JSON Schema to the keywords Cohere's structured outputs document (ADR-0012).

This module does not import ``cohere``, so it stays testable without the SDK. Any keyword
that is neither kept nor deliberately removed raises ``ValueError``, so a future schema
change cannot silently send something unsupported.
"""

import copy
from collections.abc import Mapping
from typing import Any

KEPT_KEYWORDS = frozenset(
    {
        "type",
        "properties",
        "required",
        "items",
        "enum",
        "const",
        "description",
        "title",
        "format",
        "additionalProperties",
    }
)
# Annotations and validation-only keywords: our validators still enforce them after the call.
REMOVED_KEYWORDS = frozenset({"$schema", "$id", "maxLength", "minLength", "minItems", "maxItems"})
SUPPORTED_FORMATS = frozenset({"date", "date-time", "time", "uuid"})


def to_cohere_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Return a new schema with only the keywords Cohere documents; the input is not changed."""
    return _reduce(schema, "$")


def _reduce(schema: Any, path: str) -> dict[str, Any]:
    if not isinstance(schema, Mapping):
        raise ValueError(f"Expected a schema object at {path}, got {type(schema).__name__}")
    reduced: dict[str, Any] = {}
    for keyword, value in schema.items():
        if keyword in REMOVED_KEYWORDS or keyword.startswith("x-"):
            continue
        if keyword not in KEPT_KEYWORDS:
            raise ValueError(f"Unsupported JSON Schema keyword {keyword!r} at {path}")
        if keyword == "properties":
            # Keys here are property names, not keywords: keep every name, even "title".
            reduced[keyword] = {
                name: _reduce(subschema, f"{path}.properties.{name}")
                for name, subschema in value.items()
            }
        elif keyword == "items":
            reduced[keyword] = _reduce(value, f"{path}.items")
        elif keyword == "additionalProperties" and not isinstance(value, bool):
            reduced[keyword] = _reduce(value, f"{path}.additionalProperties")
        elif keyword == "format" and value not in SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported format {value!r} at {path}")
        else:
            reduced[keyword] = copy.deepcopy(value)
    return reduced
