import copy
from datetime import UTC, datetime

import pytest

from knowledge_automata.core.records import new_record
from knowledge_automata.core.validation import revision_errors, validate_record
from knowledge_automata.core.write_rules import (
    apply_reaffirmation,
    apply_supersession,
    apply_update,
    check_supersession_links,
)
from knowledge_automata.domains.project_management.registers import DECISION_LOG, RISK_REGISTER

CREATED = datetime(2026, 11, 2, 14, 58, 30, tzinfo=UTC)
NOW = datetime(2026, 11, 2, 15, 4, 11, tzinfo=UTC)
CONTEXT = {
    "artifact_id": "ART-0004",
    "artifact_date": "2026-03-31",
    "model": "command-a-plus-05-2026",
    "prompt_version": "decision-registrar.v1",
    "now": NOW,
}


def target(record_id="DEC-0002", **content):
    return new_record(
        spec=DECISION_LOG,
        record_id=record_id,
        content=content
        or {
            "title": "One status ladder for every batch",
            "statement": "Every batch of plants moves through one status ladder.",
        },
        quotes=["one status ladder for every batch"],
        artifact_id="ART-0002",
        artifact_date="2026-03-03",
        model="command-a-plus-05-2026",
        prompt_version="decision-registrar.v1",
        now=CREATED,
    )


DRAFT = {
    "content": {
        "alternatives": ["Separate statuses per crop type"],
        "title": "Keep one status ladder for every batch",
        "statement": "The board kept the one status ladder for every batch for version 1.",
        "rationale": "Growers learn the screen once.",
    },
    "evidence": [
        "the board kept the one status ladder for every batch for version 1",
        "one set of statuses means they learn the screen once",
    ],
}


def assert_next_revision(old, new):
    assert validate_record(new, DECISION_LOG).errors == ()
    assert revision_errors(old, new) == []


# Update


def test_update_fills_only_absent_fields_and_reports_differences():
    old = target()
    snapshot, draft = copy.deepcopy(old), copy.deepcopy(DRAFT)
    record, filled, ignored = apply_update(DECISION_LOG, old, draft, **CONTEXT)
    assert old == snapshot and draft == DRAFT
    assert filled == ["rationale", "alternatives"]
    assert ignored == ["title", "statement"]
    assert record["content"] == {
        "title": "One status ladder for every batch",
        "statement": "Every batch of plants moves through one status ladder.",
        "rationale": "Growers learn the screen once.",
        "alternatives": ["Separate statuses per crop type"],
    }
    assert list(record["content"]) == ["title", "statement", "rationale", "alternatives"]
    assert record["revision"] == 2 and record["updated_at"] == "2026-11-02T15:04:11Z"
    assert record["history"][-1] == {
        "revision": 2,
        "at": "2026-11-02T15:04:11Z",
        "change": "update",
        "artifact_id": "ART-0004",
        "fields": ["rationale", "alternatives"],
        "model": "command-a-plus-05-2026",
        "prompt_version": "decision-registrar.v1",
    }
    assert record["sources"][1:] == [
        {
            "artifact_id": "ART-0004",
            "artifact_date": "2026-03-31",
            "excerpt": quote,
            "added_at": "2026-11-02T15:04:11Z",
        }
        for quote in DRAFT["evidence"]
    ]
    assert_next_revision(old, record)


def test_an_update_that_fills_nothing_still_adds_sources_and_a_revision():
    old = target()
    draft = {"content": dict(old["content"]), "evidence": ["one status ladder for every batch"]}
    record, filled, ignored = apply_update(
        DECISION_LOG, old, draft, **(CONTEXT | {"artifact_date": None})
    )
    assert filled == [] and ignored == []
    assert record["history"][-1]["fields"] == []
    assert record["sources"][-1] == {
        "artifact_id": "ART-0004",
        "excerpt": "one status ladder for every batch",
        "added_at": "2026-11-02T15:04:11Z",
    }
    assert len(record["sources"]) == 2
    assert_next_revision(old, record)


# Reaffirmation


def test_reaffirmation_adds_sources_and_ignores_content():
    old = target()
    record = apply_reaffirmation(DECISION_LOG, old, DRAFT["evidence"], **CONTEXT)
    assert record["content"] == old["content"]
    assert [source["excerpt"] for source in record["sources"][1:]] == DRAFT["evidence"]
    assert record["history"][-1] == {
        "revision": 2,
        "at": "2026-11-02T15:04:11Z",
        "change": "reaffirmation",
        "artifact_id": "ART-0004",
        "model": "command-a-plus-05-2026",
        "prompt_version": "decision-registrar.v1",
    }
    assert_next_revision(old, record)


# Supersession


def test_supersession_builds_both_records_linked_both_ways():
    old = target()
    snapshot = copy.deepcopy(old)
    new, gone = apply_supersession(DECISION_LOG, old, "DEC-0003", DRAFT, **CONTEXT)
    assert old == snapshot

    assert new["id"] == "DEC-0003" and new["revision"] == 1
    assert new["record_status"] == "active"
    assert new["relations"] == {"supersedes": ["DEC-0002"]}
    assert new["history"][0]["change"] == "supersession"
    assert new["history"][0]["related_id"] == "DEC-0002"
    assert new["history"][0]["model"] == "command-a-plus-05-2026"
    assert validate_record(new, DECISION_LOG).errors == ()

    assert gone["record_status"] == "superseded"
    assert gone["relations"] == {"superseded_by": "DEC-0003"}
    assert gone["content"] == old["content"] and gone["sources"] == old["sources"]
    assert gone["history"][-1] == {
        "revision": 2,
        "at": "2026-11-02T15:04:11Z",
        "change": "superseded",
        "artifact_id": "ART-0004",
        "related_id": "DEC-0003",
    }
    assert list(gone)[-2:] == ["relations", "history"]
    assert_next_revision(old, gone)
    assert check_supersession_links([gone, new]) == []


def test_only_an_active_record_can_be_superseded():
    old = target()
    _, gone = apply_supersession(DECISION_LOG, old, "DEC-0003", DRAFT, **CONTEXT)
    with pytest.raises(ValueError, match="not active"):
        apply_supersession(DECISION_LOG, gone, "DEC-0004", DRAFT, **CONTEXT)


@pytest.mark.parametrize(
    "call",
    [
        lambda spec, record: apply_update(spec, record, DRAFT, **CONTEXT),
        lambda spec, record: apply_reaffirmation(spec, record, ["q"], **CONTEXT),
        lambda spec, record: apply_supersession(spec, record, "RSK-0002", DRAFT, **CONTEXT),
    ],
)
def test_the_risk_register_has_no_write_rules_yet(call):
    risk = {**target(), "id": "RSK-0001", "register": "risk-register"}
    with pytest.raises(ValueError, match="decision log only"):
        call(RISK_REGISTER, risk)
    with pytest.raises(ValueError, match="decision log only"):
        call(DECISION_LOG, risk)


# Link check


def test_a_consistent_register_has_no_link_problems():
    old = target()
    new, gone = apply_supersession(DECISION_LOG, old, "DEC-0003", DRAFT, **CONTEXT)
    assert check_supersession_links([target("DEC-0001"), gone, new]) == []
    assert check_supersession_links([]) == []


def test_an_interrupted_supersession_names_both_records_and_the_fix():
    new, _ = apply_supersession(DECISION_LOG, target(), "DEC-0003", DRAFT, **CONTEXT)
    assert check_supersession_links([target(), new]) == [
        "DEC-0003 supersedes DEC-0002, but DEC-0002 is still active: a supersession was "
        "interrupted. Finish it by marking DEC-0002 superseded by DEC-0003, then run "
        "`knowledge-automata views`."
    ]


def test_dangling_and_mismatched_links_are_reported():
    new, gone = apply_supersession(DECISION_LOG, target(), "DEC-0003", DRAFT, **CONTEXT)
    assert check_supersession_links([gone]) == [
        "DEC-0002 is superseded by DEC-0003, but DEC-0003 does not exist."
    ]
    assert check_supersession_links([new]) == [
        "DEC-0003 supersedes DEC-0002, but DEC-0002 does not exist."
    ]
    other = {**target("DEC-0004"), "relations": {"supersedes": ["DEC-0002"]}}
    unlinked = {**new, "relations": {}}
    assert check_supersession_links([gone, unlinked, other]) == [
        "DEC-0002 is superseded by DEC-0003, but DEC-0003 does not supersede DEC-0002.",
        "DEC-0004 supersedes DEC-0002, but DEC-0002 is superseded and names 'DEC-0003' as "
        "its replacement.",
    ]
