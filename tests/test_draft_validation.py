import pytest

from knowledge_automata.core.validation import validate_draft
from knowledge_automata.domains.project_management.registers import (
    DECISION_LOG,
    RISK_REGISTER,
    check_response_strategy_fits_kind,
)


def assert_fails(result, *fragments):
    assert not result.ok
    for fragment in fragments:
        assert any(fragment in error for error in result.errors), (fragment, result.errors)


def test_valid_decision_draft_passes(decision_draft, artifact_text):
    result = validate_draft(decision_draft, DECISION_LOG, artifact_text)
    assert result.ok, result.errors
    assert [check.passed for check in result.evidence] == [True, True]


def test_valid_risk_draft_passes(risk_draft, artifact_text):
    result = validate_draft(risk_draft, RISK_REGISTER, artifact_text)
    assert result.ok, result.errors


def test_llm_setting_id_inside_content_fails(decision_draft, artifact_text):
    decision_draft["content"]["id"] = "DEC-0042"
    assert_fails(
        validate_draft(decision_draft, DECISION_LOG, artifact_text),
        "$.content: Additional properties are not allowed ('id' was unexpected)",
    )


def test_llm_setting_id_at_top_level_fails(decision_draft, artifact_text):
    decision_draft["id"] = "DEC-0042"
    assert_fails(
        validate_draft(decision_draft, DECISION_LOG, artifact_text),
        "$: Additional properties are not allowed ('id' was unexpected)",
    )


def test_missing_required_content_field_fails(decision_draft, artifact_text):
    del decision_draft["content"]["statement"]
    assert_fails(
        validate_draft(decision_draft, DECISION_LOG, artifact_text),
        "$.content: 'statement' is a required property",
    )


def test_bad_enum_fails(risk_draft, artifact_text):
    risk_draft["content"]["probability"] = "likely"
    assert_fails(validate_draft(risk_draft, RISK_REGISTER, artifact_text), "$.content.probability")


def test_empty_evidence_fails(decision_draft, artifact_text):
    decision_draft["evidence"] = []
    assert_fails(validate_draft(decision_draft, DECISION_LOG, artifact_text), "$.evidence")


def test_too_many_quotes_fail(decision_draft, artifact_text):
    decision_draft["evidence"] = ["Supplier B is rejected for this season."] * 6
    assert_fails(validate_draft(decision_draft, DECISION_LOG, artifact_text), "$.evidence")


def test_missing_evidence_fails(decision_draft, artifact_text):
    del decision_draft["evidence"]
    assert_fails(
        validate_draft(decision_draft, DECISION_LOG, artifact_text),
        "'evidence' is a required property",
    )


def test_threat_with_exploit_strategy_fails(risk_draft, artifact_text):
    risk_draft["content"]["response_strategy"] = "exploit"
    assert_fails(
        validate_draft(risk_draft, RISK_REGISTER, artifact_text),
        "$.content: response_strategy 'exploit' does not fit kind 'threat'",
    )


def test_one_bad_quote_rejects_the_draft_and_is_named(decision_draft, artifact_text):
    invented = "The group agreed to double the irrigation budget."
    decision_draft["evidence"].insert(1, invented)
    result = validate_draft(decision_draft, DECISION_LOG, artifact_text)
    assert result.errors == (f"$.evidence[1]: not found in the artifact: {invented!r}",)
    assert [check.passed for check in result.evidence] == [True, False, True]
    assert [check.quote for check in result.evidence if not check.passed] == [invented]


def test_short_quote_rejects_the_draft(decision_draft, artifact_text):
    decision_draft["evidence"].append("supplier A")
    assert_fails(validate_draft(decision_draft, DECISION_LOG, artifact_text), "too short")


def test_quote_from_another_artifact_fails(decision_draft):
    other_artifact = "Minutes of the finance committee. The budget was approved."
    result = validate_draft(decision_draft, DECISION_LOG, other_artifact)
    assert len(result.errors) == 2


@pytest.mark.parametrize("draft", [None, [], "text", 7])
def test_non_object_draft_fails_without_raising(draft, artifact_text):
    assert_fails(validate_draft(draft, DECISION_LOG, artifact_text), "$: ")


@pytest.mark.parametrize(
    ("kind", "strategy", "fits"),
    [
        ("threat", "avoid", True),
        ("threat", "transfer", True),
        ("threat", "mitigate", True),
        ("threat", "exploit", False),
        ("threat", "share", False),
        ("threat", "enhance", False),
        ("opportunity", "exploit", True),
        ("opportunity", "share", True),
        ("opportunity", "enhance", True),
        ("opportunity", "avoid", False),
        ("opportunity", "transfer", False),
        ("opportunity", "mitigate", False),
        ("threat", "escalate", True),
        ("threat", "accept", True),
        ("opportunity", "escalate", True),
        ("opportunity", "accept", True),
    ],
)
def test_response_strategy_must_fit_kind(kind, strategy, fits):
    errors = check_response_strategy_fits_kind({"kind": kind, "response_strategy": strategy})
    assert (errors == []) is fits


def test_risk_without_response_strategy_passes_semantic_check():
    assert check_response_strategy_fits_kind({"kind": "threat"}) == []
