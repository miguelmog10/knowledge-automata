import copy
from datetime import UTC, datetime, timedelta, timezone

import pytest

from knowledge_automata.core import ledger
from knowledge_automata.core.ledger import LedgerError, error_paths, new_entry, transition
from knowledge_automata.core.validation import validate_ledger_entry

NOW = datetime(2026, 10, 28, 14, 0, tzinfo=UTC)
LATER = NOW + timedelta(seconds=20)
HASH = "sha256:" + "ab" * 32
RUN_ID = "1b9e8a2c-4f3d-4c6b-9a1e-2d7f5e8c3b10"
PRODUCED = {
    "schema_version": "1.0",
    "prompt_version": "decision-registrar.v1",
    "model": "command-a-plus-05-2026",
    "record_id": "DEC-0002",
    "register": "decision-log",
}
REJECTED = {
    "error_paths": ["$.evidence[1]"],
    "prompt_version": "decision-registrar.v1",
    "attempts": 2,
    "register": "decision-log",
}


def received(**overrides):
    values = {
        "artifact_id": "ART-0002",
        "title": "Tallyleaf greenhouse inventory app: pilot review",
        "source_name": "pilot-review.md",
        "size_bytes": 2048,
        "content_hash": HASH,
        "at": NOW,
        "artifact_date": "2026-03-02",
        "media_type": "text/markdown",
        "stored_path": "artifacts/ART-0002-pilot-review.md",
    }
    values.update(overrides)
    return new_entry(**values)


def accepted():
    return transition(received(), to="accepted", by="sensor", at=NOW)


def processed():
    entry = transition(accepted(), to="processed", by="pipeline", at=LATER, run_id=RUN_ID)
    return ledger.with_results(entry, [PRODUCED], [])


def errors_of(entry):
    return validate_ledger_entry(entry).errors


# Building and transitions


def test_new_entry_matches_the_handoff_example_in_schema_key_order():
    entry = processed()
    assert list(entry) == [
        "schema_version",
        "id",
        "title",
        "source",
        "artifact_date",
        "media_type",
        "size_bytes",
        "content_hash",
        "stored_path",
        "status",
        "created_at",
        "updated_at",
        "produced",
        "rejected",
        "history",
    ]
    assert entry["schema_version"] == "1.0"
    assert entry["source"] == {"type": "file", "name": "pilot-review.md"}
    assert entry["created_at"] == "2026-10-28T14:00:00Z"
    assert entry["updated_at"] == "2026-10-28T14:00:20Z"
    assert list(entry["produced"][0]) == [
        "register",
        "record_id",
        "model",
        "prompt_version",
        "schema_version",
    ]
    assert entry["history"] == [
        {"at": "2026-10-28T14:00:00Z", "status": "received", "by": "sensor"},
        {"at": "2026-10-28T14:00:00Z", "status": "accepted", "by": "sensor"},
        {"at": "2026-10-28T14:00:20Z", "status": "processed", "by": "pipeline", "run_id": RUN_ID},
    ]
    assert errors_of(entry) == ()


def test_new_entry_leaves_out_optional_fields_not_given():
    entry = new_entry(
        artifact_id="ART-0006",
        title="diagram",
        source_name="diagram.pdf",
        size_bytes=10,
        content_hash=HASH,
        at=NOW,
    )
    for field in ("artifact_date", "media_type", "stored_path", "same_name_as"):
        assert field not in entry
    assert entry["status"] == "received"
    assert entry["produced"] == [] and entry["rejected"] == []


def test_new_entry_keeps_same_name_as_and_a_reason():
    entry = received(same_name_as=["ART-0001"], reason="Backfilled")
    assert entry["same_name_as"] == ["ART-0001"]
    assert entry["history"][0]["reason"] == "Backfilled"


def test_timestamps_are_utc_and_naive_datetimes_are_refused():
    entry = received(at=datetime(2026, 10, 28, 16, 0, tzinfo=timezone(timedelta(hours=2))))
    assert entry["created_at"] == "2026-10-28T14:00:00Z"
    with pytest.raises(ValueError, match="timezone-aware"):
        received(at=datetime(2026, 10, 28, 14, 0))


def test_history_entry_keys_follow_the_schema_order():
    entry = transition(
        received(stored_path=None, media_type=None),
        to="rejected",
        by="sensor",
        at=NOW,
        reason="Only .md, .markdown and .txt files are supported",
        check="unsupported-format",
    )
    assert list(entry["history"][-1]) == ["at", "status", "by", "check", "reason"]
    assert errors_of(entry) == ()


def test_transition_returns_a_new_entry_and_never_changes_the_input():
    before = accepted()
    snapshot = copy.deepcopy(before)
    after = transition(before, to="failed", by="pipeline", at=LATER, run_id=RUN_ID, error_type="X")
    assert before == snapshot
    assert after["history"][:2] == before["history"]
    assert after["status"] == "failed"


@pytest.mark.parametrize(
    ("steps", "message"),
    [
        ([("accepted", "sensor"), ("rejected", "sensor")], "cannot change status from 'accepted'"),
        ([("accepted", "sensor"), ("accepted", "operator")], "from 'accepted' to 'accepted'"),
        ([("quarantined", "sensor"), ("processed", "pipeline")], "'quarantined' to 'processed'"),
        ([("rejected", "sensor"), ("accepted", "operator")], "'rejected' to 'accepted'"),
        ([("accepted", "operator")], "'operator' cannot change"),
        ([("quarantined", "sensor"), ("accepted", "sensor")], "allowed: operator"),
        ([("accepted", "sensor"), ("processed", "sensor")], "allowed: governor, pipeline"),
        (
            [("accepted", "sensor"), ("processed", "pipeline"), ("failed", "pipeline")],
            "'processed' to 'failed'",
        ),
    ],
)
def test_transitions_outside_the_table_or_by_the_wrong_owner_are_refused(steps, message):
    entry = received()
    with pytest.raises(LedgerError, match=message):
        for status, by in steps:
            entry = transition(entry, to=status, by=by, at=NOW)


@pytest.mark.parametrize(
    "path",
    [
        [("accepted", "sensor"), ("processed", "pipeline")],
        [("accepted", "sensor"), ("failed", "pipeline"), ("failed", "governor")],
        [("accepted", "sensor"), ("failed", "pipeline"), ("processed", "pipeline")],
        [("quarantined", "sensor"), ("accepted", "operator"), ("processed", "pipeline")],
    ],
)
def test_every_allowed_path_is_accepted(path):
    entry = received()
    for status, by in path:
        entry = transition(entry, to=status, by=by, at=NOW)
    assert entry["status"] == path[-1][0]


def test_a_transition_cannot_go_back_in_time():
    with pytest.raises(LedgerError, match="earlier than the last history entry"):
        transition(received(), to="accepted", by="sensor", at=NOW - timedelta(seconds=1))


def test_with_results_orders_items_and_leaves_the_input_alone():
    entry = accepted()
    updated = ledger.with_results(entry, [PRODUCED], [REJECTED])
    assert entry["produced"] == [] and entry["rejected"] == []
    assert list(updated["rejected"][0]) == ["register", "attempts", "prompt_version", "error_paths"]


def test_error_paths_are_unique_in_first_seen_order():
    errors = [
        "$.evidence[1]: quote not found in the artifact: 'some model text'",
        "$.content.title: 'x' is too short",
        "$.evidence[1]: another problem",
        "$: 'evidence' is a required property",
    ]
    assert error_paths(errors) == ["$.evidence[1]", "$.content.title", "$"]


def test_an_unusable_response_message_becomes_the_root_path():
    assert error_paths(["Response was not valid JSON (finish_reason MAX_TOKENS)"]) == ["$"]
    assert error_paths([]) == []


# Validation


def test_the_quarantined_example_from_the_handoff_is_valid():
    entry = new_entry(
        artifact_id="ART-0005",
        title="notes",
        source_name="notes.md",
        size_bytes=182340,
        content_hash=HASH,
        at=NOW,
        media_type="text/markdown",
        stored_path="artifacts/ART-0005-notes.md",
        same_name_as=["ART-0003"],
    )
    entry = transition(
        entry,
        to="quarantined",
        by="sensor",
        at=NOW,
        check="oversized",
        reason="182,340 bytes; the limit is 100,000 (KA_SENSOR_MAX_BYTES)",
    )
    assert errors_of(entry) == ()
    released = transition(entry, to="accepted", by="operator", at=LATER, reason="Read in full")
    assert errors_of(released) == ()


def test_a_processed_entry_with_rejected_drafts_and_an_error_type_is_valid():
    entry = transition(accepted(), to="processed", by="pipeline", at=LATER, run_id=RUN_ID)
    unusable = {**REJECTED, "error_paths": ["$"], "error_type": "LLMResponseError"}
    assert errors_of(ledger.with_results(entry, [], [unusable])) == ()


def test_a_failed_entry_needs_an_error_type_and_a_run_id():
    entry = transition(
        accepted(),
        to="failed",
        by="pipeline",
        at=LATER,
        run_id=RUN_ID,
        error_type="LLMTimeoutError",
    )
    assert errors_of(entry) == ()
    del entry["history"][-1]["error_type"]
    del entry["history"][-1]["run_id"]
    assert errors_of(entry) == (
        "$.history[2]: a 'failed' entry needs a run_id",
        "$.history[2]: a 'failed' entry needs an error_type",
    )


def test_a_received_entry_is_never_stored():
    assert "$.status: an entry is stored only after the Sensor's checks" in errors_of(received())


def test_status_and_times_must_match_the_history():
    entry = accepted()
    entry["status"] = "quarantined"
    entry["updated_at"] = "2026-10-28T15:00:00Z"
    entry["created_at"] = "2026-10-28T13:00:00Z"
    assert errors_of(entry) == (
        "$.status: 'quarantined' does not match the last history entry",
        "$.updated_at: does not match the last history entry's time",
        "$.created_at: does not match the first history entry's time",
    )


def test_a_hand_edited_history_is_caught():
    entry = processed()
    entry["history"].insert(
        1, {"at": "2026-10-28T14:00:00Z", "status": "quarantined", "by": "sensor"}
    )
    entry["history"][0]["by"] = "operator"
    entry["history"][3]["at"] = "2026-10-28T13:59:59Z"
    errors = errors_of(entry)
    assert "$.history[0].by: 'operator' cannot change from None to 'received'" in errors
    assert "$.history[1]: a Sensor 'quarantined' entry needs the check that decided it" in errors
    assert "$.history[2].by: 'sensor' cannot change from 'quarantined' to 'accepted'" in errors
    assert "$.history[3].at: earlier than the previous history entry" in errors


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"check": "oversized"}, "$.history[1].check: 'oversized' leads to 'quarantined'"),
        ({"check": None}, "$.history[1]: a Sensor 'rejected' entry needs the check"),
        ({"run_id": RUN_ID}, "$.history[1].run_id: only 'processed' and 'failed' entries"),
        ({"error_type": "X"}, "$.history[1].error_type: only 'failed' entries have one"),
    ],
)
def test_history_fields_must_fit_the_step(change, message):
    entry = transition(
        received(stored_path=None),
        to="rejected",
        by="sensor",
        at=NOW,
        check="empty",
        reason="The file is empty",
    )
    step = entry["history"][1]
    for key, value in change.items():
        if value is None:
            step.pop(key)
        else:
            step[key] = value
    assert message in "\n".join(errors_of(entry))


def test_a_check_on_an_accepted_entry_and_an_operator_without_a_reason_are_caught():
    entry = transition(
        received(), to="quarantined", by="sensor", at=NOW, check="oversized", reason="Too big"
    )
    entry = transition(entry, to="accepted", by="operator", at=LATER)
    entry["history"][1]["check"] = "oversized"
    entry["history"][2]["check"] = "oversized"
    errors = errors_of(entry)
    assert "$.history[2]: an Operator entry needs a reason" in errors
    assert "$.history[2].check: only Sensor 'rejected' and 'quarantined' entries have one" in errors


def test_stored_path_presence_follows_the_status():
    entry = accepted()
    del entry["stored_path"]
    assert "$: a 'accepted' entry needs a stored_path" in errors_of(entry)
    rejected = transition(
        received(), to="rejected", by="sensor", at=NOW, check="empty", reason="The file is empty"
    )
    assert "$.stored_path: a 'rejected' entry has no stored copy" in errors_of(rejected)


def test_media_type_is_absent_only_for_an_unsupported_format():
    entry = accepted()
    del entry["media_type"]
    assert "$: media_type is required unless the format is unsupported" in errors_of(entry)
    rejected = transition(
        received(stored_path=None),
        to="rejected",
        by="sensor",
        at=NOW,
        check="unsupported-format",
        reason="Only .md, .markdown and .txt files are supported",
    )
    assert "$.media_type: must be absent when the format is unsupported" in errors_of(rejected)


def test_results_are_empty_unless_processed():
    entry = ledger.with_results(accepted(), [PRODUCED], [REJECTED])
    assert errors_of(entry) == (
        "$.produced: must be empty unless the status is 'processed'",
        "$.rejected: must be empty unless the status is 'processed'",
    )


def test_same_name_as_lists_earlier_ids_in_ascending_order():
    assert (
        errors_of(
            transition(received(same_name_as=["ART-0001"]), to="accepted", by="sensor", at=NOW)
        )
        == ()
    )
    entry = transition(
        received(same_name_as=["ART-0001", "ART-0003", "ART-0002"]),
        to="accepted",
        by="sensor",
        at=NOW,
    )
    assert errors_of(entry) == (
        "$.same_name_as: IDs must be in ascending order",
        "$.same_name_as: may list only earlier entries",
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", "ART-1"),
        ("content_hash", "sha256:ABC"),
        ("stored_path", "artifacts/../.env"),
        ("stored_path", "/tmp/ART-0002.md"),
        ("source", {"type": "file", "name": "C:\\Users\\me\\notes.md"}),
        ("source", {"type": "file", "name": "home/me/notes.md"}),
        ("source", {"type": "email", "name": "notes.md"}),
        ("title", ""),
        ("title", "x" * 201),
        ("media_type", "application/pdf"),
        ("size_bytes", -1),
        ("created_at", "2026-10-28T16:00:00+02:00"),
        ("same_name_as", []),
        ("extra", True),
    ],
)
def test_schema_rejects_bad_fields(field, value):
    entry = accepted()
    entry[field] = value
    assert errors_of(entry)


@pytest.mark.parametrize(
    "item",
    [
        {**REJECTED, "error_paths": []},
        {**REJECTED, "error_paths": ["evidence[1]"]},
        {**REJECTED, "error_paths": ["$.a", "$.a"]},
        {**REJECTED, "attempts": 0},
        {**REJECTED, "error_type": "not a class"},
        {**REJECTED, "errors": ["$.evidence[1]: quote not found: 'model text'"]},
    ],
)
def test_schema_rejects_bad_rejected_items(item):
    entry = transition(accepted(), to="processed", by="pipeline", at=LATER, run_id=RUN_ID)
    assert errors_of(ledger.with_results(entry, [], [item]))


def test_a_reason_is_limited_to_500_characters():
    entry = transition(
        received(), to="quarantined", by="sensor", at=NOW, check="oversized", reason="x" * 501
    )
    assert errors_of(entry)


def test_validation_never_raises_for_non_objects():
    for value in (None, [], "ART-0001", {"history": []}):
        assert errors_of(value)
