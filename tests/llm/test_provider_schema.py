import copy
import re

import pytest

from knowledge_automata.core.schemas import draft_schema
from knowledge_automata.domains.project_management.registers import REGISTERS
from knowledge_automata.llm.provider_schema import (
    KEPT_KEYWORDS,
    SUPPORTED_FORMATS,
    to_cohere_schema,
)

NESTED = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "urn:test",
    "x-version": "1.0",
    "type": "object",
    "title": "Thing",
    "properties": {
        "title": {"type": "string", "minLength": 1, "maxLength": 200, "x-pmi-mapping": "Name"},
        "format": {"type": "string", "format": "date", "description": "A property named format"},
        "tags": {
            "type": "array",
            "minItems": 1,
            "maxItems": 5,
            "items": {"type": "string", "enum": ["a", "b"], "x-note": "inner"},
        },
        "meta": {
            "type": "object",
            "properties": {"kind": {"const": "fixed", "type": "string", "x-deep": True}},
            "required": ["kind"],
            "additionalProperties": False,
        },
        "extra": {
            "type": "object",
            "properties": {"a": {"type": "string"}},
            "required": ["a"],
            "additionalProperties": {"type": "string", "maxLength": 3},
        },
    },
    "required": ["title"],
    "additionalProperties": False,
}


def keywords(schema, found=None):
    """Every keyword used at any depth, skipping property names."""
    found = set() if found is None else found
    for keyword, value in schema.items():
        found.add(keyword)
        if keyword == "properties":
            for subschema in value.values():
                keywords(subschema, found)
        elif keyword in ("items", "additionalProperties") and isinstance(value, dict):
            keywords(value, found)
    return found


def test_annotations_and_validation_only_keywords_are_removed_at_every_depth():
    reduced = to_cohere_schema(NESTED)
    assert keywords(reduced) <= KEPT_KEYWORDS
    assert reduced == {
        "type": "object",
        "title": "Thing",
        "properties": {
            "title": {"type": "string"},
            "format": {
                "type": "string",
                "format": "date",
                "description": "A property named format",
            },
            "tags": {"type": "array", "items": {"type": "string", "enum": ["a", "b"]}},
            "meta": {
                "type": "object",
                "properties": {"kind": {"const": "fixed", "type": "string"}},
                "required": ["kind"],
                "additionalProperties": False,
            },
            "extra": {
                "type": "object",
                "properties": {"a": {"type": "string"}},
                "required": ["a"],
                "additionalProperties": {"type": "string"},
            },
        },
        "required": ["title"],
        "additionalProperties": False,
    }


def test_property_names_that_look_like_keywords_survive():
    reduced = to_cohere_schema(NESTED)
    assert {"title", "format"} <= set(reduced["properties"])


@pytest.mark.parametrize(
    ("schema", "message"),
    [
        (
            {"type": "object", "properties": {"code": {"type": "string", "pattern": "[A-Z]+"}}},
            "'pattern' at $.properties.code",
        ),
        ({"type": "object", "anyOf": []}, "'anyOf' at $"),
        ({"type": "array", "items": {"type": "integer", "minimum": 1}}, "'minimum' at $.items"),
        (
            {"type": "object", "additionalProperties": {"type": "string", "$ref": "#/x"}},
            "'$ref' at $.additionalProperties",
        ),
        (
            {"type": "object", "properties": {"mail": {"type": "string", "format": "email"}}},
            "format 'email' at $.properties.mail",
        ),
    ],
)
def test_unknown_keywords_and_formats_raise_with_their_path(schema, message):
    with pytest.raises(ValueError, match=re.escape(message)):
        to_cohere_schema(schema)


def test_input_is_not_mutated_and_output_is_independent():
    original = copy.deepcopy(NESTED)
    reduced = to_cohere_schema(NESTED)
    assert NESTED == original
    reduced["properties"]["tags"]["items"]["enum"].append("c")
    reduced["required"].append("format")
    assert NESTED == original


@pytest.mark.parametrize("spec", REGISTERS, ids=lambda spec: spec.name)
def test_register_draft_schemas_reduce_to_allowlisted_keywords(spec):
    schema = draft_schema(spec)
    reduced = to_cohere_schema(schema)
    assert keywords(reduced) <= KEPT_KEYWORDS
    assert reduced["type"] == "object"
    assert set(reduced["properties"]) == set(schema["properties"])
    for path_format in _formats(reduced):
        assert path_format in SUPPORTED_FORMATS


def _formats(schema):
    if "format" in schema:
        yield schema["format"]
    for subschema in schema.get("properties", {}).values():
        yield from _formats(subschema)
    if isinstance(schema.get("items"), dict):
        yield from _formats(schema["items"])
