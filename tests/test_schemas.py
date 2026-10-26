import ast
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from knowledge_automata.core import schemas
from knowledge_automata.core.registers import CLASSIFICATIONS, RegisterSpec
from knowledge_automata.domains.project_management.registers import (
    DECISION_LOG,
    REGISTERS,
    RISK_REGISTER,
)
from knowledge_automata.llm.provider_schema import KEPT_KEYWORDS, SUPPORTED_FORMATS

CORE_DIR = Path(__file__).resolve().parents[1] / "src" / "knowledge_automata" / "core"

# Keywords the provider adapter sends to the LLM provider (llm/provider_schema.py), and
# keywords it removes before sending.
SENT_KEYWORDS = KEPT_KEYWORDS
REMOVED_KEYWORDS = {
    "$schema",
    "$id",
    "x-version",
    "x-pmi-mapping",
    "maxLength",
    "minItems",
    "maxItems",
}
SENT_FORMATS = SUPPORTED_FORMATS


def provider_compatibility_errors(schema: dict, path: str = "$") -> list[str]:
    """Return every way a schema breaks the provider keyword subset or Cohere's rules."""
    errors = []
    for keyword in schema:
        if keyword not in SENT_KEYWORDS | REMOVED_KEYWORDS:
            errors.append(f"{path}: unsupported keyword {keyword!r}")
    if "format" in schema and schema["format"] not in SENT_FORMATS:
        errors.append(f"{path}: unsupported format {schema['format']!r}")
    if "enum" in schema and "type" not in schema:
        errors.append(f"{path}: enum without type")
    if schema.get("type") == "object":
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        # Cohere: every object needs at least one required field.
        if not required:
            errors.append(f"{path}: object without required fields")
        for name in required:
            if name not in properties:
                errors.append(f"{path}: required field {name!r} is not a property")
        for name, subschema in properties.items():
            errors.extend(provider_compatibility_errors(subschema, f"{path}.{name}"))
        if isinstance(schema.get("additionalProperties"), dict):
            errors.extend(
                provider_compatibility_errors(schema["additionalProperties"], f"{path}.*")
            )
    if isinstance(schema.get("items"), dict):
        errors.extend(provider_compatibility_errors(schema["items"], f"{path}[]"))
    return errors


def provider_schemas() -> list[tuple[str, dict]]:
    pairs = [(f"draft:{spec.name}", schemas.draft_schema(spec)) for spec in REGISTERS]
    pairs.append(("reconciliation", schemas.load_schema(schemas.RECONCILIATION_SCHEMA)))
    return pairs


def test_all_expected_schema_files_are_found():
    assert set(schemas.list_schemas()) >= {
        "core/record.v1.json",
        "core/draft.v1.json",
        "core/reconciliation.v1.json",
        "project-management/decision.v1.json",
        "project-management/risk.v1.json",
    }


@pytest.mark.parametrize("relative_path", schemas.list_schemas())
def test_schema_file_is_valid_draft_2020_12(relative_path):
    schema = schemas.load_schema(relative_path)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize("relative_path", schemas.list_schemas())
def test_schema_file_has_major_minor_version(relative_path):
    schema = schemas.load_schema(relative_path)
    major, minor = schema["x-version"].split(".")
    assert major.isdigit() and minor.isdigit()
    assert relative_path.endswith(f".v{major}.json")


@pytest.mark.parametrize(("name", "schema"), provider_schemas(), ids=lambda value: str(value)[:30])
def test_provider_schema_uses_only_supported_keywords(name, schema):
    assert schema["type"] == "object"
    assert provider_compatibility_errors(schema) == []


def test_provider_compatibility_check_catches_violations():
    bad = {
        "type": "object",
        "properties": {
            "code": {"type": "string", "pattern": "[A-Z]+", "minLength": 2},
            "email": {"type": "string", "format": "email"},
            "level": {"enum": ["low", "high"]},
            "nested": {"type": "object", "properties": {"a": {"type": "string"}}},
            "choice": {"anyOf": [{"type": "string"}, {"type": "integer"}]},
        },
        "required": ["code", "missing"],
    }
    errors = provider_compatibility_errors(bad)
    expected = [
        "$.code: unsupported keyword 'pattern'",
        "$.code: unsupported keyword 'minLength'",
        "$.email: unsupported format 'email'",
        "$.level: enum without type",
        "$.nested: object without required fields",
        "$.choice: unsupported keyword 'anyOf'",
        "$: required field 'missing' is not a property",
    ]
    assert sorted(errors) == sorted(expected)


@pytest.mark.parametrize("spec", REGISTERS, ids=lambda spec: spec.name)
def test_draft_schema_inlines_the_content_schema(spec):
    draft = schemas.draft_schema(spec)
    assert draft["properties"]["content"] == schemas.load_schema(spec.content_schema)
    assert "$ref" not in json.dumps(draft)
    Draft202012Validator.check_schema(draft)


def test_draft_schema_returns_an_independent_copy():
    first = schemas.draft_schema(DECISION_LOG)
    first["properties"]["content"]["required"].append("tampered")
    assert "tampered" not in schemas.draft_schema(DECISION_LOG)["properties"]["content"]["required"]
    assert "tampered" not in schemas.load_schema(DECISION_LOG.content_schema)["required"]


def test_schema_version_reads_x_version():
    assert schemas.schema_version(DECISION_LOG) == "1.0"
    assert schemas.schema_version(RISK_REGISTER) == "1.0"
    assert schemas.major_version("12.3") == 12


@pytest.mark.parametrize("bad_path", ["../pyproject.toml", "/etc/passwd", ""])
def test_load_schema_rejects_paths_outside_schemas(bad_path):
    with pytest.raises(ValueError):
        schemas.load_schema(bad_path)


def test_load_schema_raises_for_missing_file():
    with pytest.raises(FileNotFoundError):
        schemas.load_schema("core/missing.v1.json")


def test_registers_point_at_existing_content_schemas():
    for spec in REGISTERS:
        assert spec.content_schema in schemas.list_schemas()


def test_risk_register_does_not_allow_supersession():
    assert DECISION_LOG.allowed_classifications == CLASSIFICATIONS
    assert RISK_REGISTER.allowed_classifications == CLASSIFICATIONS - {"supersession"}


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": "Decision Log"},
        {"id_prefix": "DE"},
        {"allowed_classifications": frozenset({"new", "merge"})},
        {"allowed_classifications": frozenset({"update"})},
    ],
)
def test_register_spec_rejects_invalid_definitions(kwargs):
    defaults = {
        "name": "test-register",
        "id_prefix": "TST",
        "content_schema": "project-management/decision.v1.json",
        "allowed_classifications": CLASSIFICATIONS,
    }
    with pytest.raises(ValueError):
        RegisterSpec(**(defaults | kwargs))


def test_core_does_not_import_domains():
    # ADR-0009: the core is domain-neutral.
    for module in CORE_DIR.glob("*.py"):
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                assert "domains" not in name.split("."), f"{module.name} imports {name}"
