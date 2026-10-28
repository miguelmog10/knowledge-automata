import json
from pathlib import Path

import pytest

from knowledge_automata.domains.project_management.registers import DECISION_LOG
from knowledge_automata.storage.json_files import format_json, write_json_atomic
from knowledge_automata.storage.record_store import RecordStore

ROOT = Path(__file__).resolve().parents[1]
RECORD_FILES = [
    ROOT / "examples" / "sample-project" / "registers" / "decision-log" / "DEC-0001.json",
    ROOT / "tests" / "fixtures" / "store" / "DEC-0001.json",
]


def committed_bytes(path):
    # A Windows checkout may turn the committed LF into CRLF; the stores always write LF.
    return path.read_bytes().replace(b"\r\n", b"\n")


def handoff_004_format(data):
    """The record format before the shared writer, kept here as the reference."""
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


@pytest.mark.parametrize("path", RECORD_FILES, ids=lambda path: path.parent.name)
def test_committed_records_round_trip_byte_for_byte(path, tmp_path):
    expected = committed_bytes(path)
    record = json.loads(expected)
    assert format_json(record).encode("utf-8") == expected
    saved = RecordStore(tmp_path).save_new(record, DECISION_LOG)
    assert saved.read_bytes() == expected


@pytest.mark.parametrize(
    "data",
    [
        {"b": 1, "a": [1, {"z": None, "y": True}], "c": 'Paul’s “café” — 日本 \\ " \t'},
        [],
        {},
    ],
)
def test_format_matches_the_handoff_004_record_format(data):
    assert format_json(data) == handoff_004_format(data)


def test_keys_keep_their_order_and_non_ascii_stays_readable():
    text = format_json({"z": "é", "a": 1})
    assert text == '{\n  "z": "é",\n  "a": 1\n}\n'


def test_write_creates_the_folder_and_writes_lf_utf8(tmp_path):
    path = tmp_path / "ledger" / "ART-0001.json"
    write_json_atomic(path, {"title": "Café\nnotes"}, overwrite=False)
    assert path.read_bytes() == '{\n  "title": "Café\\nnotes"\n}\n'.encode()
    assert [p.name for p in path.parent.iterdir()] == ["ART-0001.json"]


def test_write_refuses_an_existing_file_unless_overwrite(tmp_path):
    path = tmp_path / "ART-0001.json"
    path.write_bytes(b"before")
    with pytest.raises(FileExistsError):
        write_json_atomic(path, {"a": 1}, overwrite=False)
    assert path.read_bytes() == b"before"
    write_json_atomic(path, {"a": 1}, overwrite=True)
    assert path.read_bytes() == b'{\n  "a": 1\n}\n'
    assert [p.name for p in tmp_path.iterdir()] == ["ART-0001.json"]


def test_a_failed_write_leaves_no_temporary_file_and_keeps_the_old_one(tmp_path, monkeypatch):
    path = tmp_path / "ART-0001.json"
    path.write_bytes(b"before")

    def failing_replace(source, target):
        raise PermissionError(13, "locked", str(target))

    monkeypatch.setattr("knowledge_automata.storage.json_files.os.replace", failing_replace)
    with pytest.raises(PermissionError):
        write_json_atomic(path, {"a": 1}, overwrite=True)
    assert path.read_bytes() == b"before"
    assert [p.name for p in tmp_path.iterdir()] == ["ART-0001.json"]
