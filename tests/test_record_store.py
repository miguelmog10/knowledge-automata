import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from knowledge_automata.core.records import history_entry, new_record, new_sources, order_record
from knowledge_automata.core.validation import revision_errors
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

    monkeypatch.setattr("knowledge_automata.storage.json_files.os.replace", failing_replace)
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


# Revisions

LATER = "2026-10-27T09:15:00Z"


def superseded(old, by="DEC-0002"):
    new = copy.deepcopy(old)
    new["record_status"] = "superseded"
    new["revision"] = old["revision"] + 1
    new["updated_at"] = LATER
    new["relations"] = {"superseded_by": by}
    new["history"].append(
        history_entry(
            revision=new["revision"],
            timestamp=LATER,
            change="superseded",
            artifact_id="ART-0008",
            related_id=by,
        )
    )
    return order_record(new)


def reaffirmed(old):
    new = copy.deepcopy(old)
    new["revision"] = old["revision"] + 1
    new["updated_at"] = LATER
    new["sources"] += new_sources(
        ["Paul’s greenhouse again"], artifact_id="ART-0008", artifact_date=None, timestamp=LATER
    )
    new["history"].append(
        history_entry(
            revision=new["revision"],
            timestamp=LATER,
            change="reaffirmation",
            artifact_id="ART-0008",
            model="fake-chat",
            prompt_version="decision-registrar.v1",
        )
    )
    return new


def saved(tmp_path, record=None):
    store = RecordStore(tmp_path)
    record = record or make_record()
    store.save_new(record, DECISION_LOG)
    return store, record


def test_a_revision_writes_the_hand_written_bytes(tmp_path):
    store, old = saved(tmp_path)
    path = store.save_revision(old, superseded(old), DECISION_LOG)
    expected = (FIXTURES / "store" / "DEC-0001.revision-2.json").read_bytes()
    assert path.read_bytes() == expected.replace(b"\r\n", b"\n")
    assert [p.name for p in register(tmp_path).iterdir()] == ["DEC-0001.json"]


def test_revisions_follow_each_other(tmp_path):
    store, old = saved(tmp_path)
    second = reaffirmed(old)
    store.save_revision(old, second, DECISION_LOG)
    third = superseded(second)
    store.save_revision(second, third, DECISION_LOG)
    assert store.load_all(DECISION_LOG) == [third]
    assert [entry["change"] for entry in third["history"]] == [
        "new",
        "reaffirmation",
        "superseded",
    ]


def test_save_revision_refuses_a_stale_old_record(tmp_path):
    store, old = saved(tmp_path)
    store.save_revision(old, reaffirmed(old), DECISION_LOG)
    with pytest.raises(RecordStoreError, match="changed in the register since it was read"):
        store.save_revision(old, superseded(old), DECISION_LOG)
    missing = make_record("DEC-0002")
    with pytest.raises(RecordStoreError, match="changed in the register"):
        store.save_revision(missing, reaffirmed(missing), DECISION_LOG)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda new: new["history"][0].update(model="other"), "$.history: must be the old"),
        (lambda new: new["history"].append(dict(new["history"][-1])), "$.history"),
        (lambda new: new["sources"][0].update(excerpt="rewritten"), "$.sources: must start"),
        (lambda new: new["sources"].pop(0), "$.sources: must start"),
        (lambda new: new.update(created_at=LATER), "$.created_at: a revision cannot change it"),
        (lambda new: new.update(updated_at="2026-10-28T00:00:00Z"), "$.updated_at: must match"),
        (
            lambda new: new.update(relations={"supersedes": ["DEC-0009"]}),
            "$.relations.supersedes: a revision cannot change it",
        ),
        (
            lambda new: new.update(relations={"superseded_by": "DEC-0009"}),
            "$.relations.superseded_by: added only when",
        ),
    ],
)
def test_save_revision_refuses_rewritten_history_sources_or_envelope(tmp_path, change, message):
    store, old = saved(tmp_path)
    before = (register(tmp_path) / "DEC-0001.json").read_bytes()
    new = reaffirmed(old)
    change(new)
    with pytest.raises(RecordStoreError) as raised:
        store.save_revision(old, new, DECISION_LOG)
    assert message in str(raised.value)
    assert (register(tmp_path) / "DEC-0001.json").read_bytes() == before
    assert [p.name for p in register(tmp_path).iterdir()] == ["DEC-0001.json"]


def test_save_revision_refuses_a_revision_jump(tmp_path):
    store, old = saved(tmp_path)
    jump = reaffirmed(old)
    jump["revision"] = 3
    jump["history"][-1]["revision"] = 3
    with pytest.raises(RecordStoreError):
        store.save_revision(old, jump, DECISION_LOG)
    # validate_record catches the gap first; revision_errors catches it on its own too.
    assert "$.revision: must be 2, the next after 1" in revision_errors(old, jump)


def test_a_superseded_record_never_goes_back_to_active(tmp_path):
    store, old = saved(tmp_path)
    gone = superseded(old)
    store.save_revision(old, gone, DECISION_LOG)
    back = reaffirmed(gone)
    back["record_status"] = "active"
    del back["relations"]
    with pytest.raises(RecordStoreError, match="a 'superseded' record cannot be revised"):
        store.save_revision(gone, back, DECISION_LOG)
    again = reaffirmed(gone)
    with pytest.raises(RecordStoreError, match="a 'superseded' record cannot be revised"):
        store.save_revision(gone, again, DECISION_LOG)


def test_save_revision_refuses_an_invalid_record(tmp_path):
    store, old = saved(tmp_path)
    new = superseded(old)
    del new["relations"]
    with pytest.raises(RecordStoreError, match="invalid and was not written"):
        store.save_revision(old, new, DECISION_LOG)
    assert store.load_all(DECISION_LOG) == [old]


def test_save_revision_leaves_no_temporary_file_when_writing_fails(tmp_path, monkeypatch):
    store, old = saved(tmp_path)

    def failing_replace(source, target):
        raise PermissionError(13, "locked", str(target))

    monkeypatch.setattr("knowledge_automata.storage.json_files.os.replace", failing_replace)
    with pytest.raises(PermissionError):
        store.save_revision(old, reaffirmed(old), DECISION_LOG)
    assert [p.name for p in register(tmp_path).iterdir()] == ["DEC-0001.json"]


def test_load_active_skips_superseded_records(tmp_path):
    store, first = saved(tmp_path)
    second = make_record("DEC-0002")
    store.save_new(second, DECISION_LOG)
    assert store.load_active(DECISION_LOG) == [first, second]
    store.save_revision(first, superseded(first), DECISION_LOG)
    assert store.load_active(DECISION_LOG) == [second]
    assert RecordStore(tmp_path / "empty").load_active(DECISION_LOG) == []
