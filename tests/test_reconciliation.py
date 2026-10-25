import pytest

from knowledge_automata.core.validation import validate_reconciliation
from knowledge_automata.domains.project_management.registers import DECISION_LOG, RISK_REGISTER


def assert_fails(result, *fragments):
    assert not result.ok
    for fragment in fragments:
        assert any(fragment in error for error in result.errors), (fragment, result.errors)


@pytest.fixture
def decision_candidates(decision_record):
    superseded = decision_record | {
        "id": "DEC-0002",
        "record_status": "superseded",
        "relations": {"superseded_by": "DEC-0003"},
    }
    return {"DEC-0001": decision_record, "DEC-0002": superseded}


@pytest.fixture
def risk_candidates(risk_record):
    return {"RSK-0001": risk_record}


def result(classification, target_id=None):
    value = {"classification": classification, "reason": "Fictional reason for the test."}
    if target_id is not None:
        value["target_id"] = target_id
    return value


def test_new_without_target_passes(decision_candidates):
    assert validate_reconciliation(result("new"), DECISION_LOG, decision_candidates).ok


def test_new_with_no_candidates_passes():
    assert validate_reconciliation(result("new"), RISK_REGISTER, {}).ok


@pytest.mark.parametrize("classification", ["update", "reaffirmation", "supersession"])
def test_decision_classification_of_active_candidate_passes(classification, decision_candidates):
    outcome = validate_reconciliation(
        result(classification, "DEC-0001"), DECISION_LOG, decision_candidates
    )
    assert outcome.ok, outcome.errors


@pytest.mark.parametrize("classification", ["update", "reaffirmation"])
def test_risk_classification_of_active_candidate_passes(classification, risk_candidates):
    outcome = validate_reconciliation(
        result(classification, "RSK-0001"), RISK_REGISTER, risk_candidates
    )
    assert outcome.ok, outcome.errors


def test_new_with_target_fails(decision_candidates):
    assert_fails(
        validate_reconciliation(result("new", "DEC-0001"), DECISION_LOG, decision_candidates),
        "$.target_id: must be omitted",
    )


@pytest.mark.parametrize("classification", ["update", "reaffirmation", "supersession"])
def test_missing_target_fails(classification, decision_candidates):
    assert_fails(
        validate_reconciliation(result(classification), DECISION_LOG, decision_candidates),
        "$.target_id: required",
    )


def test_target_not_among_candidates_fails(decision_candidates):
    assert_fails(
        validate_reconciliation(result("update", "DEC-0099"), DECISION_LOG, decision_candidates),
        "was not one of the candidates",
    )


def test_target_with_another_registers_prefix_fails(decision_candidates, risk_record):
    # Even if a record from another register slipped into the candidates.
    candidates = decision_candidates | {"RSK-0001": risk_record}
    assert_fails(
        validate_reconciliation(result("update", "RSK-0001"), DECISION_LOG, candidates),
        "$.target_id: 'RSK-0001' does not start with 'DEC-'",
    )


def test_supersession_in_risk_register_fails(risk_candidates):
    assert_fails(
        validate_reconciliation(result("supersession", "RSK-0001"), RISK_REGISTER, risk_candidates),
        "$.classification: 'supersession' is not allowed in register 'risk-register'",
    )


@pytest.mark.parametrize("classification", ["update", "reaffirmation", "supersession"])
def test_superseded_target_fails(classification, decision_candidates):
    assert_fails(
        validate_reconciliation(
            result(classification, "DEC-0002"), DECISION_LOG, decision_candidates
        ),
        "only active records can be the target",
    )


@pytest.mark.parametrize(
    "bad_result",
    [
        {"classification": "merge", "reason": "Not a classification."},
        {"classification": "new"},
        {"classification": "new", "reason": "Extra field.", "confidence": 0.9},
        {"classification": "update", "reason": "Wrong type.", "target_id": 1},
        None,
        "new",
    ],
)
def test_schema_invalid_result_fails_without_raising(bad_result, decision_candidates):
    assert not validate_reconciliation(bad_result, DECISION_LOG, decision_candidates).ok
