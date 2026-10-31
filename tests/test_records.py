import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from knowledge_automata.core.records import (
    format_timestamp,
    history_entry,
    new_record,
    new_sources,
)
from knowledge_automata.core.schemas import RECORD_SCHEMA, load_schema
from knowledge_automata.core.validation import validate_record
from knowledge_automata.domains.project_management.registers import DECISION_LOG
from knowledge_automata.storage.json_files import format_json

NOW = datetime(2026, 10, 26, 14, 3, 12, 987654, tzinfo=UTC)
SAMPLE = Path(__file__).parent.parent / "examples" / "sample-project"


def build(decision_draft, **overrides):
    kwargs = {
        "spec": DECISION_LOG,
        "record_id": "DEC-0001",
        "content": decision_draft["content"],
        "quotes": decision_draft["evidence"],
        "artifact_id": "ART-0001",
        "artifact_date": "2026-03-12",
        "model": "fake-chat",
        "prompt_version": "decision-registrar.v1",
        "now": NOW,
    }
    return new_record(**(kwargs | overrides))


def test_built_record_passes_validation(decision_draft):
    record = build(decision_draft)
    assert validate_record(record, DECISION_LOG).ok, validate_record(record, DECISION_LOG).errors
    assert record["record_status"] == "active"
    assert record["revision"] == 1
    assert record["register"] == "decision-log"
    assert record["schema_version"] == "1.0"
    assert "relations" not in record


def test_one_source_per_quote_in_order(decision_draft):
    record = build(decision_draft)
    assert [source["excerpt"] for source in record["sources"]] == decision_draft["evidence"]
    assert all(source["artifact_id"] == "ART-0001" for source in record["sources"])
    assert all(source["artifact_date"] == "2026-03-12" for source in record["sources"])
    assert list(record["sources"][0]) == ["artifact_id", "artifact_date", "excerpt", "added_at"]


def test_artifact_date_only_when_given(decision_draft):
    record = build(decision_draft, artifact_date=None)
    assert all("artifact_date" not in source for source in record["sources"])
    assert validate_record(record, DECISION_LOG).ok


def test_envelope_key_order_follows_the_record_schema(decision_draft):
    record = build(decision_draft)
    schema_order = [key for key in load_schema(RECORD_SCHEMA)["properties"] if key in record]
    assert list(record) == schema_order


def test_content_keys_follow_the_content_schema_order():
    content = {"impacts": "I", "statement": "S", "decided_on": "2026-02-03", "title": "T"}
    record = build({"content": content, "evidence": ["q"]})
    assert list(record["content"]) == ["title", "statement", "decided_on", "impacts"]
    assert record["history"][0]["fields"] == ["title", "statement", "decided_on", "impacts"]


def test_timestamps_are_utc_seconds_with_z(decision_draft):
    record = build(decision_draft)
    stamps = {record["created_at"], record["updated_at"], record["history"][0]["at"]}
    stamps |= {source["added_at"] for source in record["sources"]}
    assert stamps == {"2026-10-26T14:03:12Z"}


def test_timestamp_converts_to_utc_and_refuses_naive_times():
    assert format_timestamp(datetime(2026, 1, 1, 9, 0, tzinfo=timezone(timedelta(hours=-5)))) == (
        "2026-01-01T14:00:00Z"
    )
    with pytest.raises(ValueError):
        format_timestamp(datetime(2026, 1, 1, 9, 0))


def test_history_entry(decision_draft):
    record = build(decision_draft, prompt_version="decision-registrar.v1+registrar-retry.v1")
    assert record["history"] == [
        {
            "revision": 1,
            "at": "2026-10-26T14:03:12Z",
            "change": "new",
            "artifact_id": "ART-0001",
            "fields": [
                "title",
                "statement",
                "context",
                "rationale",
                "alternatives",
                "decided_by",
                "decided_on",
                "impacts",
            ],
            "model": "fake-chat",
            "prompt_version": "decision-registrar.v1+registrar-retry.v1",
        }
    ]


def test_new_record_does_not_modify_the_draft(decision_draft):
    original = {"statement": "S", "title": "T"}
    build({"content": original, "evidence": ["q"]})
    assert list(original) == ["statement", "title"]


def test_the_sample_decision_is_rebuilt_byte_for_byte():
    path = SAMPLE / "registers" / "decision-log" / "DEC-0001.json"
    stored = json.loads(path.read_text(encoding="utf-8"))
    entry = stored["history"][0]
    rebuilt = new_record(
        spec=DECISION_LOG,
        record_id=stored["id"],
        content=stored["content"],
        quotes=[source["excerpt"] for source in stored["sources"]],
        artifact_id=entry["artifact_id"],
        artifact_date=stored["sources"][0]["artifact_date"],
        model=entry["model"],
        prompt_version=entry["prompt_version"],
        now=datetime.fromisoformat(stored["created_at"]),
    )
    expected = path.read_bytes().replace(b"\r\n", b"\n")
    assert format_json(rebuilt).encode("utf-8") == expected


def test_a_superseding_record_links_to_its_target(decision_draft):
    record = build(
        decision_draft, record_id="DEC-0003", change="supersession", supersedes="DEC-0002"
    )
    assert record["relations"] == {"supersedes": ["DEC-0002"]}
    assert list(record)[-2:] == ["relations", "history"]
    assert record["history"][0]["change"] == "supersession"
    assert list(record["history"][0]) == [
        "revision",
        "at",
        "change",
        "artifact_id",
        "fields",
        "related_id",
        "model",
        "prompt_version",
    ]
    assert record["history"][0]["related_id"] == "DEC-0002"
    assert validate_record(record, DECISION_LOG).ok


def test_history_entry_leaves_out_what_is_not_given():
    assert history_entry(
        revision=2,
        timestamp="2026-10-27T09:15:00Z",
        change="superseded",
        artifact_id="ART-0002",
        related_id="DEC-0003",
    ) == {
        "revision": 2,
        "at": "2026-10-27T09:15:00Z",
        "change": "superseded",
        "artifact_id": "ART-0002",
        "related_id": "DEC-0003",
    }
    entry = history_entry(
        revision=2, timestamp="t", change="update", artifact_id="ART-0002", fields=[]
    )
    assert entry["fields"] == []


def test_new_sources_follow_the_schema_order():
    sources = new_sources(["a", "b"], artifact_id="ART-0002", artifact_date=None, timestamp="t")
    assert sources == [
        {"artifact_id": "ART-0002", "excerpt": "a", "added_at": "t"},
        {"artifact_id": "ART-0002", "excerpt": "b", "added_at": "t"},
    ]
