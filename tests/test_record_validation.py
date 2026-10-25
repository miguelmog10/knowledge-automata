import pytest

from knowledge_automata.core.validation import is_date_time, validate_record
from knowledge_automata.domains.project_management.registers import DECISION_LOG, RISK_REGISTER


def assert_fails(result, *fragments):
    assert not result.ok
    for fragment in fragments:
        assert any(fragment in error for error in result.errors), (fragment, result.errors)


def test_valid_decision_record_passes(decision_record):
    result = validate_record(decision_record, DECISION_LOG)
    assert result.ok, result.errors


def test_valid_risk_record_passes(risk_record):
    result = validate_record(risk_record, RISK_REGISTER)
    assert result.ok, result.errors


@pytest.mark.parametrize("field", ["id", "register", "content", "sources", "history"])
def test_missing_required_envelope_field_fails(decision_record, field):
    del decision_record[field]
    result = validate_record(decision_record, DECISION_LOG)
    assert_fails(result, f"'{field}' is a required property")


def test_bad_record_status_fails(decision_record):
    decision_record["record_status"] = "archived"
    assert_fails(validate_record(decision_record, DECISION_LOG), "$.record_status")


def test_superseded_without_superseded_by_fails(decision_record):
    decision_record["record_status"] = "superseded"
    result = validate_record(decision_record, DECISION_LOG)
    assert_fails(result, "'relations' is a required property")
    decision_record["relations"] = {"supersedes": ["DEC-0000"]}
    assert_fails(
        validate_record(decision_record, DECISION_LOG), "'superseded_by' is a required property"
    )


def test_superseded_with_superseded_by_passes(decision_record):
    decision_record["record_status"] = "superseded"
    decision_record["relations"] = {"superseded_by": "DEC-0007"}
    decision_record["revision"] = 2
    decision_record["history"].append(
        {
            "revision": 2,
            "at": "2026-04-02T09:00:00Z",
            "change": "superseded",
            "artifact_id": "ART-0005",
            "related_id": "DEC-0007",
        }
    )
    result = validate_record(decision_record, DECISION_LOG)
    assert result.ok, result.errors


@pytest.mark.parametrize("bad_id", ["DEC-1", "dec-0001", "DEC0001", "DECI-0001", ""])
def test_malformed_id_fails(decision_record, bad_id):
    decision_record["id"] = bad_id
    assert_fails(validate_record(decision_record, DECISION_LOG), "$.id")


def test_decision_id_in_risk_register_fails(risk_record):
    risk_record["id"] = "DEC-0001"
    assert_fails(validate_record(risk_record, RISK_REGISTER), "$.id: 'DEC-0001' does not start")


def test_register_mismatch_fails(decision_record):
    assert_fails(validate_record(decision_record, RISK_REGISTER), "$.register")


@pytest.mark.parametrize(
    "bad_value",
    [
        "yesterday",
        "2026-03-12",
        "2026-03-12T18:30:00",  # no timezone
        "2026-03-12 18:30:00Z",  # space instead of T
        "2026-03-12T18:30Z",  # no seconds
        "20260312T183000Z",  # compact ISO 8601
        "2026-02-30T18:30:00Z",  # no such day
        "2026-03-12T25:00:00Z",
    ],
)
def test_invalid_date_time_fails(decision_record, bad_value):
    decision_record["created_at"] = bad_value
    assert_fails(validate_record(decision_record, DECISION_LOG), "$.created_at", "date-time")


@pytest.mark.parametrize(
    "value",
    [
        "2026-03-12T18:30:00Z",
        "2026-03-12t18:30:00z",
        "2026-03-12T18:30:00.123456+01:00",
        "2026-03-12T18:30:00-05:00",
    ],
)
def test_rfc3339_date_times_pass(value):
    assert is_date_time(value)


def test_invalid_content_date_fails(decision_record):
    decision_record["content"]["decided_on"] = "12/03/2026"
    assert_fails(validate_record(decision_record, DECISION_LOG), "$.content.decided_on")


def test_content_missing_required_field_fails(risk_record):
    del risk_record["content"]["kind"]
    assert_fails(
        validate_record(risk_record, RISK_REGISTER), "$.content: 'kind' is a required property"
    )


def test_content_failing_semantic_check_fails(risk_record):
    risk_record["content"]["response_strategy"] = "exploit"
    assert_fails(validate_record(risk_record, RISK_REGISTER), "$.content: response_strategy")


def test_wrong_major_schema_version_fails(decision_record):
    decision_record["schema_version"] = "2.0"
    assert_fails(validate_record(decision_record, DECISION_LOG), "$.schema_version: major version")


def test_newer_minor_schema_version_passes(decision_record):
    decision_record["schema_version"] = "1.3"
    assert validate_record(decision_record, DECISION_LOG).ok


def test_revision_not_matching_last_history_entry_fails(risk_record):
    risk_record["revision"] = 3
    assert_fails(validate_record(risk_record, RISK_REGISTER), "$.revision: 3 does not match")


def test_history_revisions_must_increase_by_one(risk_record):
    risk_record["history"][1]["revision"] = 3
    risk_record["revision"] = 3
    assert_fails(validate_record(risk_record, RISK_REGISTER), "$.history: revisions must increase")


@pytest.mark.parametrize(
    ("relations", "path"),
    [
        ({"supersedes": ["DEC-0001"]}, "$.relations.supersedes"),
        ({"superseded_by": "DEC-0001"}, "$.relations.superseded_by"),
    ],
)
def test_relations_pointing_at_own_id_fail(decision_record, relations, path):
    decision_record["relations"] = relations
    if "superseded_by" in relations:
        decision_record["record_status"] = "superseded"
    assert_fails(validate_record(decision_record, DECISION_LOG), path)


def test_history_related_id_pointing_at_own_id_fails(decision_record):
    decision_record["history"][0]["related_id"] = "DEC-0001"
    assert_fails(validate_record(decision_record, DECISION_LOG), "$.history[0].related_id")


@pytest.mark.parametrize("record", [None, [], "DEC-0001", 42])
def test_non_object_record_fails_without_raising(record):
    assert_fails(validate_record(record, DECISION_LOG), "$: ")
