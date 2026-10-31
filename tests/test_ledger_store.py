import json
from datetime import UTC, datetime, timedelta

import pytest

from knowledge_automata.core.ledger import new_entry, transition, with_results
from knowledge_automata.storage.ledger_store import (
    LedgerEntryNotFoundError,
    LedgerStore,
    LedgerStoreError,
)

NOW = datetime(2026, 10, 28, 14, 0, tzinfo=UTC)
LATER = NOW + timedelta(seconds=20)
RUN_ID = "1b9e8a2c-4f3d-4c6b-9a1e-2d7f5e8c3b10"

# Written by hand from the handoff's rules: schema key order, two-space indent, LF,
# non-ASCII kept as is, trailing newline.
EXPECTED_ART_0002 = """{
  "schema_version": "1.1",
  "id": "ART-0002",
  "title": "Pilot review: café",
  "source": {
    "type": "file",
    "name": "pilot-review.md"
  },
  "artifact_date": "2026-03-02",
  "media_type": "text/markdown",
  "size_bytes": 2048,
  "content_hash": "sha256:abababababababababababababababababababababababababababababababab",
  "stored_path": "artifacts/ART-0002-pilot-review.md",
  "status": "accepted",
  "created_at": "2026-10-28T14:00:00Z",
  "updated_at": "2026-10-28T14:00:00Z",
  "produced": [],
  "rejected": [],
  "history": [
    {
      "at": "2026-10-28T14:00:00Z",
      "status": "received",
      "by": "sensor"
    },
    {
      "at": "2026-10-28T14:00:00Z",
      "status": "accepted",
      "by": "sensor"
    }
  ]
}
"""


def entry(artifact_id="ART-0002", *, name="pilot-review.md", content_hash="ab", status="accepted"):
    built = new_entry(
        artifact_id=artifact_id,
        title="Pilot review: café",
        source_name=name,
        size_bytes=2048,
        content_hash="sha256:" + content_hash * 32,
        at=NOW,
        artifact_date="2026-03-02",
        media_type="text/markdown",
        stored_path=None if status == "rejected" else f"artifacts/{artifact_id}-pilot-review.md",
    )
    if status == "accepted":
        return transition(built, to="accepted", by="sensor", at=NOW)
    if status == "rejected":
        return transition(built, to="rejected", by="sensor", at=NOW, check="empty", reason="Empty")
    return transition(built, to="quarantined", by="sensor", at=NOW, check="oversized", reason="Big")


def processed(old):
    new = transition(old, to="processed", by="pipeline", at=LATER, run_id=RUN_ID)
    return with_results(new, [], [])


def test_save_new_writes_the_deterministic_format(tmp_path):
    store = LedgerStore(tmp_path)
    path = store.save_new(entry())
    assert path == tmp_path / "ledger" / "ART-0002.json"
    assert path.read_bytes() == EXPECTED_ART_0002.encode("utf-8")
    assert store.load("ART-0002") == entry()


def test_next_id_is_the_highest_sequence_plus_one(tmp_path):
    store = LedgerStore(tmp_path)
    assert store.next_id() == "ART-0001"
    store.save_new(entry("ART-0001"))
    store.save_new(entry("ART-0009", content_hash="cd"))
    assert store.next_id() == "ART-0010"
    (tmp_path / "ledger" / "ART-0009.json").unlink()
    assert store.next_id() == "ART-0002"
    store.save_new(entry("ART-9999", content_hash="ef"))
    assert store.next_id() == "ART-10000"


def test_save_new_refuses_an_invalid_entry_or_an_existing_file(tmp_path):
    store = LedgerStore(tmp_path)
    invalid = entry()
    invalid["status"] = "processed"
    with pytest.raises(LedgerStoreError, match="invalid and was not written"):
        store.save_new(invalid)
    assert not (tmp_path / "ledger").exists()

    store.save_new(entry())
    with pytest.raises(LedgerStoreError, match="already exists, not overwritten"):
        store.save_new(entry())


def test_load_all_is_sorted_and_validates_every_file(tmp_path):
    store = LedgerStore(tmp_path)
    store.save_new(entry("ART-0010", content_hash="cd"))
    store.save_new(entry("ART-0002"))
    assert [item["id"] for item in store.load_all()] == ["ART-0002", "ART-0010"]

    path = tmp_path / "ledger" / "ART-0010.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["status"] = "processed"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(LedgerStoreError, match=r"ART-0010.json is not a valid Ledger entry"):
        store.load_all()


@pytest.mark.parametrize("name", ["notes.md", "ART-1.json", "art-0001.json", ".ART-0001.tmp"])
def test_an_unexpected_file_in_the_ledger_folder_is_an_error(tmp_path, name):
    store = LedgerStore(tmp_path)
    store.save_new(entry())
    (tmp_path / "ledger" / name).write_text("{}", encoding="utf-8")
    with pytest.raises(LedgerStoreError, match="Unexpected entry in Ledger folder"):
        store.load_all()


def test_load_reports_missing_bad_json_and_a_mismatched_id(tmp_path):
    store = LedgerStore(tmp_path)
    with pytest.raises(LedgerEntryNotFoundError, match="ART-0002 is not in the Ledger"):
        store.load("ART-0002")
    with pytest.raises(LedgerStoreError, match="Not an artifact ID"):
        store.load("../ART-0002")

    folder = tmp_path / "ledger"
    folder.mkdir()
    (folder / "ART-0002.json").write_bytes(b"\xff{")
    with pytest.raises(LedgerStoreError, match="not valid UTF-8 JSON"):
        store.load("ART-0002")

    (folder / "ART-0003.json").write_text(json.dumps(entry()), encoding="utf-8")
    with pytest.raises(LedgerStoreError, match="holds entry 'ART-0002', not 'ART-0003'"):
        store.load("ART-0003")


def test_save_transition_appends_and_overwrites(tmp_path):
    store = LedgerStore(tmp_path)
    old = entry()
    store.save_new(old)
    new = processed(old)
    store.save_transition(old, new)
    assert store.load("ART-0002") == new
    assert [p.name for p in (tmp_path / "ledger").iterdir()] == ["ART-0002.json"]


def test_save_transition_refuses_a_lost_update(tmp_path):
    store = LedgerStore(tmp_path)
    old = entry()
    store.save_new(old)
    first = processed(old)
    store.save_transition(old, first)
    failed = transition(old, to="failed", by="pipeline", at=LATER, run_id=RUN_ID, error_type="X")
    with pytest.raises(LedgerStoreError, match="changed in the Ledger since it was read"):
        store.save_transition(old, failed)
    assert store.load("ART-0002") == first


def test_save_transition_refuses_rewritten_history_or_changed_fields(tmp_path):
    store = LedgerStore(tmp_path)
    old = entry()
    store.save_new(old)

    rewritten = processed(old)
    rewritten["history"][0]["reason"] = "rewritten"
    with pytest.raises(LedgerStoreError, match="keep the old one unchanged"):
        store.save_transition(old, rewritten)

    with pytest.raises(LedgerStoreError, match="keep the old one unchanged"):
        store.save_transition(old, old)

    retitled = processed(old)
    retitled["title"] = "Another title"
    retitled["content_hash"] = "sha256:" + "cd" * 32
    with pytest.raises(LedgerStoreError, match="cannot change content_hash, title"):
        store.save_transition(old, retitled)

    other = processed(entry("ART-0003"))
    with pytest.raises(LedgerStoreError, match="Cannot replace ART-0002 with ART-0003"):
        store.save_transition(old, other)

    invalid = processed(old)
    invalid["status"] = "failed"
    with pytest.raises(LedgerStoreError, match="invalid and was not written"):
        store.save_transition(old, invalid)
    assert store.load("ART-0002") == old


def test_save_transition_raises_a_1_0_entry_to_the_current_version_only(tmp_path):
    store = LedgerStore(tmp_path)
    old = entry()
    old["schema_version"] = "1.0"
    store.save_new(old)

    sideways = processed(old)
    sideways["schema_version"] = "1.0"
    store.save_transition(old, sideways)
    assert store.load("ART-0002")["schema_version"] == "1.0"

    rerun = transition(sideways, to="processed", by="pipeline", at=LATER, run_id=RUN_ID)
    assert rerun["schema_version"] == "1.1"
    store.save_transition(sideways, rerun)
    assert store.load("ART-0002")["schema_version"] == "1.1"

    downgraded = transition(
        rerun, to="failed", by="pipeline", at=LATER, run_id=RUN_ID, error_type="X"
    )
    downgraded["schema_version"] = "1.0"
    with pytest.raises(LedgerStoreError, match="cannot change schema_version"):
        store.save_transition(rerun, downgraded)


def test_save_transition_refuses_to_rerun_an_entry_that_lists_records(tmp_path):
    store = LedgerStore(tmp_path)
    old = entry()
    store.save_new(old)
    produced = with_results(
        transition(old, to="processed", by="pipeline", at=LATER, run_id=RUN_ID),
        [
            {
                "register": "decision-log",
                "record_id": "DEC-0002",
                "model": "m",
                "prompt_version": "p",
                "schema_version": "1.0",
            }
        ],
        [],
    )
    store.save_transition(old, produced)
    rerun = dict(produced, history=[*produced["history"], produced["history"][-1]])
    rerun["produced"] = []
    with pytest.raises(LedgerStoreError, match="already lists records"):
        store.save_transition(produced, rerun)


def test_save_transition_keeps_earlier_rejected_drafts(tmp_path):
    store = LedgerStore(tmp_path)
    old = entry()
    store.save_new(old)
    item = {
        "register": "decision-log",
        "attempts": 2,
        "prompt_version": "p",
        "error_paths": ["$"],
        "run_id": RUN_ID,
    }
    first = with_results(processed(old), [], [item])
    store.save_transition(old, first)
    second_run = "2c0f9b3d-5a4e-4d7c-8b2f-3e8a6f9d4c21"
    rerun = transition(first, to="processed", by="pipeline", at=LATER, run_id=second_run)
    with pytest.raises(LedgerStoreError, match="must keep the old one unchanged"):
        store.save_transition(first, with_results(rerun, [], []))
    store.save_transition(first, rerun)
    assert store.load("ART-0002")["rejected"] == [item]


def test_find_by_hash_ignores_rejected_entries(tmp_path):
    store = LedgerStore(tmp_path)
    assert store.find_by_hash("sha256:" + "ab" * 32) is None
    store.save_new(entry("ART-0001", status="rejected"))
    assert store.find_by_hash("sha256:" + "ab" * 32) is None
    store.save_new(entry("ART-0002", status="quarantined"))
    store.save_new(entry("ART-0003", content_hash="cd"))
    assert store.find_by_hash("sha256:" + "ab" * 32)["id"] == "ART-0002"
    assert store.find_by_hash("sha256:" + "cd" * 32)["id"] == "ART-0003"


def test_ids_with_name_is_exact_and_includes_every_status(tmp_path):
    store = LedgerStore(tmp_path)
    store.save_new(entry("ART-0001", name="notes.md", status="rejected"))
    store.save_new(entry("ART-0002", name="Notes.md", content_hash="cd"))
    store.save_new(entry("ART-0003", name="notes.md", content_hash="ef", status="quarantined"))
    assert store.ids_with_name("notes.md") == ["ART-0001", "ART-0003"]
    assert store.ids_with_name("notes") == []
