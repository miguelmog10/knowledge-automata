import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from knowledge_automata.core.records import new_record
from knowledge_automata.domains.project_management.registers import DECISION_LOG, RISK_REGISTER
from knowledge_automata.storage.record_store import RecordStore, RecordStoreError

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 26, 14, 3, 12, 500000, tzinfo=UTC)


def make_record(record_id="DEC-0001", artifact_id="ART-0007"):
    return new_record(
        spec=DECISION_LOG,
        record_id=record_id,
        content={
            "statement": "Use Paul’s greenhouse for the pilot.",
            "title": "Pilot at Paul’s greenhouse",
            "alternatives": ["Use the city greenhouse"],
        },
        quotes=["the pilot runs at Paul’s greenhouse"],
        artifact_id=artifact_id,
        artifact_date="2026-02-03",
        model="fake-chat",
        prompt_version="decision-registrar.v1",
        now=NOW,
    )


def register(tmp_path):
    return tmp_path / "registers" / "decision-log"


def touch(tmp_path, *names):
    folder = register(tmp_path)
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        (folder / name).write_text("{}", encoding="utf-8")


def test_next_id_on_an_empty_register(tmp_path):
    assert RecordStore(tmp_path).next_id(DECISION_LOG) == "DEC-0001"
    register(tmp_path).mkdir(parents=True)
    assert RecordStore(tmp_path).next_id(DECISION_LOG) == "DEC-0001"


def test_next_id_follows_the_highest_sequence_despite_gaps(tmp_path):
    touch(tmp_path, "DEC-0001.json", "DEC-0003.json")
    assert RecordStore(tmp_path).next_id(DECISION_LOG) == "DEC-0004"


def test_next_id_past_9999(tmp_path):
    touch(tmp_path, "DEC-9999.json", "DEC-0002.json")
    assert RecordStore(tmp_path).next_id(DECISION_LOG) == "DEC-10000"


def test_registers_are_separate(tmp_path):
    touch(tmp_path, "DEC-0005.json")
    assert RecordStore(tmp_path).next_id(RISK_REGISTER) == "RSK-0001"


def test_saved_bytes_match_the_hand_written_file(tmp_path):
    path = RecordStore(tmp_path).save_new(make_record(), DECISION_LOG)
    assert path == register(tmp_path) / "DEC-0001.json"
    # A Windows checkout may turn the fixture's LF into CRLF; the store always writes LF.
    expected = (FIXTURES / "store" / "DEC-0001.json").read_bytes().replace(b"\r\n", b"\n")
    assert path.read_bytes() == expected
    assert b"\r" not in path.read_bytes()


def test_save_new_refuses_an_existing_id(tmp_path):
    store = RecordStore(tmp_path)
    path = store.save_new(make_record(), DECISION_LOG)
    before = path.read_bytes()
    with pytest.raises(RecordStoreError, match="already exists"):
        store.save_new(make_record(artifact_id="ART-0008"), DECISION_LOG)
    assert path.read_bytes() == before
    assert [p.name for p in register(tmp_path).iterdir()] == ["DEC-0001.json"]


def test_save_new_refuses_an_invalid_record_and_writes_nothing(tmp_path):
    record = make_record()
    record["content"]["title"] = "x" * 200
    del record["sources"]
    with pytest.raises(RecordStoreError) as raised:
        RecordStore(tmp_path).save_new(record, DECISION_LOG)
    message = str(raised.value)
    assert "$.content.title" in message and "'sources' is a required property" in message
    assert not (tmp_path / "registers").exists()


def test_save_new_leaves_no_temporary_file_when_writing_fails(tmp_path, monkeypatch):
    def failing_replace(source, target):
        raise PermissionError(13, "locked", str(target))

    monkeypatch.setattr("knowledge_automata.storage.record_store.os.replace", failing_replace)
    with pytest.raises(PermissionError):
        RecordStore(tmp_path).save_new(make_record(), DECISION_LOG)
    assert list(register(tmp_path).iterdir()) == []


def test_save_new_leaves_no_temporary_file_on_success(tmp_path):
    RecordStore(tmp_path).save_new(make_record(), DECISION_LOG)
    assert [p.name for p in register(tmp_path).iterdir()] == ["DEC-0001.json"]


def test_load_all_round_trips_sorted_by_id(tmp_path):
    store = RecordStore(tmp_path)
    second = make_record("DEC-10000")
    first = make_record("DEC-0002")
    store.save_new(second, DECISION_LOG)
    store.save_new(first, DECISION_LOG)
    assert store.load_all(DECISION_LOG) == [first, second]


def test_load_all_names_an_invalid_file(tmp_path):
    store = RecordStore(tmp_path)
    store.save_new(make_record(), DECISION_LOG)
    bad = make_record("DEC-0002")
    bad["record_status"] = "deleted"
    (register(tmp_path) / "DEC-0002.json").write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(RecordStoreError, match="DEC-0002.json"):
        store.load_all(DECISION_LOG)


def test_load_all_names_a_file_that_is_not_json(tmp_path):
    touch(tmp_path)
    (register(tmp_path) / "DEC-0001.json").write_text("not json", encoding="utf-8")
    with pytest.raises(RecordStoreError, match="DEC-0001.json"):
        RecordStore(tmp_path).load_all(DECISION_LOG)


def test_load_all_names_a_record_whose_id_does_not_match_its_file(tmp_path):
    touch(tmp_path)
    path = register(tmp_path) / "DEC-0002.json"
    path.write_text(json.dumps(make_record("DEC-0001")), encoding="utf-8")
    with pytest.raises(RecordStoreError, match="DEC-0002.json"):
        RecordStore(tmp_path).load_all(DECISION_LOG)


@pytest.mark.parametrize("name", ["notes.txt", "DEC-1.json", "RSK-0001.json", ".DEC-0001.x.tmp"])
def test_unexpected_files_are_never_ignored(tmp_path, name):
    touch(tmp_path, name)
    store = RecordStore(tmp_path)
    with pytest.raises(RecordStoreError, match=name.replace(".", r"\.")):
        store.load_all(DECISION_LOG)
    with pytest.raises(RecordStoreError):
        store.next_id(DECISION_LOG)


def test_ids_citing_finds_records_by_artifact(tmp_path):
    store = RecordStore(tmp_path)
    store.save_new(make_record("DEC-0001", "ART-0007"), DECISION_LOG)
    store.save_new(make_record("DEC-0002", "ART-0008"), DECISION_LOG)
    store.save_new(make_record("DEC-0003", "ART-0007"), DECISION_LOG)
    assert store.ids_citing(DECISION_LOG, "ART-0007") == ["DEC-0001", "DEC-0003"]
    assert store.ids_citing(DECISION_LOG, "ART-0009") == []
