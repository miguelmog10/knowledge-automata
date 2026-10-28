import json
from datetime import UTC, datetime, timedelta

import pytest

from knowledge_automata.agents import sensor
from knowledge_automata.agents.sensor import SensorConfigError, SensorInputError, content_hash
from knowledge_automata.core.validation import validate_ledger_entry
from knowledge_automata.pipeline import InputError, ingest_file, release_artifact
from knowledge_automata.storage.ledger_store import LedgerEntryNotFoundError, LedgerStore

NOW = datetime(2026, 10, 28, 14, 0, tzinfo=UTC)
LATER = NOW + timedelta(minutes=5)
NOTES = b"# Pilot review\r\n\r\nWe decided to keep the pilot.\r\n"


@pytest.fixture
def memory(tmp_path):
    return tmp_path / "memory"


@pytest.fixture
def inbox(tmp_path):
    folder = tmp_path / "inbox"
    folder.mkdir()
    return folder


def drop(inbox, name, raw):
    path = inbox / name
    path.write_bytes(raw)
    return path


def run(memory, path, *, artifact_date=None, max_bytes=100_000, now=NOW):
    return ingest_file(
        path=path, memory=memory, artifact_date=artifact_date, max_bytes=max_bytes, now=now
    )


def files_in(folder):
    return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []


# Content hash (6.2)


def test_line_endings_and_a_bom_do_not_change_the_hash():
    lf = b"line one\nline two\n"
    variants = [lf, b"line one\r\nline two\r\n", b"line one\rline two\r", b"\xef\xbb\xbf" + lf]
    assert {content_hash(raw) for raw in variants} == {content_hash(lf)}
    assert content_hash(lf).startswith("sha256:") and len(content_hash(lf)) == 71


def test_one_changed_character_changes_the_hash():
    assert content_hash(b"line one\n") != content_hash(b"line One\n")


def test_the_hash_works_on_undecodable_bytes():
    assert content_hash(b"\xff\xfe\x00") == content_hash(b"\xff\xfe\x00")


# Settings


@pytest.mark.parametrize(("value", "expected"), [(None, 100_000), ("", 100_000), (" 250 ", 250)])
def test_max_bytes_comes_from_the_environment(value, expected):
    env = {} if value is None else {"KA_SENSOR_MAX_BYTES": value}
    assert sensor.max_bytes_from_env(env) == expected


@pytest.mark.parametrize("value", ["0", "-5", "1e5", "lots", "10.5"])
def test_an_invalid_max_bytes_is_a_configuration_error(value):
    with pytest.raises(SensorConfigError, match="KA_SENSOR_MAX_BYTES must be a positive"):
        sensor.max_bytes_from_env({"KA_SENSOR_MAX_BYTES": value})


# Names, titles and slugs


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("pilot-review.md", "ART-0002-pilot-review.md"),
        ("Pilot Review (Final).MD", "ART-0002-pilot-review-final.md"),
        ("ART-0001-project-board-2026-02-03.md", "ART-0002-project-board-2026-02-03.md"),
        ("art-12-notes.txt", "ART-0002-notes.txt"),
        ("Café — notes.markdown", "ART-0002-caf-notes.markdown"),
        ("日本.txt", "ART-0002-artifact.txt"),
        ("x" * 80 + ".md", "ART-0002-" + "x" * 60 + ".md"),
        ("a" * 59 + "-b.md", "ART-0002-" + "a" * 59 + ".md"),
    ],
)
def test_copy_names(name, expected):
    assert sensor.copy_name("ART-0002", name) == expected


@pytest.mark.parametrize(
    ("name", "text", "media", "expected"),
    [
        ("notes.md", "Intro\n#  Pilot review  \n# Later", "text/markdown", "Pilot review"),
        ("notes.md", "## Only a subheading\n#No space", "text/markdown", "notes"),
        ("notes.md", "#   \n# Real", "text/markdown", "Real"),
        ("notes.txt", "# Not a heading in plain text", "text/plain", "notes"),
        ("notes.md", None, "text/markdown", "notes"),
        ("diagram.pdf", None, None, "diagram"),
        ("notes.md", "# " + "t" * 300, "text/markdown", "t" * 200),
    ],
)
def test_titles(name, text, media, expected):
    assert sensor.title(name, text, media) == expected


# Ingest outcomes (6.3)


def test_an_accepted_artifact_gets_an_entry_and_an_identical_copy(memory, inbox):
    outcome = run(memory, drop(inbox, "Pilot Review.md", NOTES), artifact_date="2026-03-02")
    assert outcome.status == "accepted"
    entry = outcome.entry
    assert entry["id"] == "ART-0001"
    assert entry["title"] == "Pilot review"
    assert entry["source"] == {"type": "file", "name": "Pilot Review.md"}
    assert entry["artifact_date"] == "2026-03-02"
    assert entry["media_type"] == "text/markdown"
    assert entry["size_bytes"] == len(NOTES)
    assert entry["content_hash"] == content_hash(NOTES)
    assert entry["stored_path"] == "artifacts/ART-0001-pilot-review.md"
    assert "same_name_as" not in entry
    assert entry["history"] == [
        {"at": "2026-10-28T14:00:00Z", "status": "received", "by": "sensor"},
        {"at": "2026-10-28T14:00:00Z", "status": "accepted", "by": "sensor"},
    ]
    assert (memory / "artifacts" / "ART-0001-pilot-review.md").read_bytes() == NOTES
    assert LedgerStore(memory).load("ART-0001") == entry


@pytest.mark.parametrize(
    ("name", "raw", "check", "reason"),
    [
        ("diagram.pdf", b"%PDF-1.7", "unsupported-format", "Only .md, .markdown and .txt"),
        ("notes", b"text", "unsupported-format", "Only .md, .markdown and .txt"),
        ("notes.md.bak", b"text", "unsupported-format", "Only .md, .markdown and .txt"),
        ("empty.md", b"", "empty", "The file is empty"),
        ("blank.txt", b" \r\n\t\n", "empty", "The file holds only whitespace"),
        ("bom.md", b"\xef\xbb\xbf", "empty", "The file holds only whitespace"),
    ],
)
def test_rejected_files_get_an_entry_and_no_copy(memory, inbox, name, raw, check, reason):
    outcome = run(memory, drop(inbox, name, raw))
    assert outcome.status == "rejected"
    step = outcome.entry["history"][-1]
    assert (step["check"], step["status"], step["by"]) == (check, "rejected", "sensor")
    assert step["reason"].startswith(reason)
    assert "stored_path" not in outcome.entry
    assert files_in(memory / "artifacts") == []
    assert files_in(memory / "ledger") == ["ART-0001.json"]
    assert ("media_type" in outcome.entry) is (check != "unsupported-format")


@pytest.mark.parametrize(
    ("name", "raw", "check", "reason"),
    [
        ("latin1.md", b"caf\xe9 notes", "encoding", "Not valid UTF-8 text (first bad byte at 3)"),
        ("utf16.txt", "notes".encode("utf-16"), "encoding", "Not valid UTF-8 text"),
        ("big.md", b"# Big\n" + b"x" * 200, "oversized", "206 bytes; the limit is 100 "),
        ("tag.md", b"# Notes\nsee </ARTIFACT > here", "delimiter", "Contains '</artifact'"),
    ],
)
def test_quarantined_files_get_an_entry_and_a_copy(memory, inbox, name, raw, check, reason):
    outcome = run(memory, drop(inbox, name, raw), max_bytes=100)
    assert outcome.status == "quarantined"
    step = outcome.entry["history"][-1]
    assert (step["check"], step["status"]) == (check, "quarantined")
    assert step["reason"].startswith(reason)
    stored = memory / outcome.entry["stored_path"]
    assert stored.read_bytes() == raw


def test_the_oversized_reason_names_the_variable(memory, inbox):
    outcome = run(memory, drop(inbox, "big.md", b"x" * 182_340))
    assert outcome.entry["history"][-1]["reason"] == (
        "182,340 bytes; the limit is 100,000 (KA_SENSOR_MAX_BYTES)"
    )


def test_checks_run_in_order(memory, inbox):
    # Unsupported format wins over encoding; encoding over size; size over the delimiter.
    assert (
        run(memory, drop(inbox, "a.pdf", b"\xff" * 500), max_bytes=10).entry["history"][-1]["check"]
        == "unsupported-format"
    )
    assert (
        run(memory, drop(inbox, "b.md", b"\xff" * 500), max_bytes=10).entry["history"][-1]["check"]
        == "encoding"
    )
    assert (
        run(memory, drop(inbox, "c.md", b"</artifact>" * 5), max_bytes=10).entry["history"][-1][
            "check"
        ]
        == "oversized"
    )
    assert run(memory, drop(inbox, "d.md", b"x" * 10)).status == "accepted"
    assert run(memory, drop(inbox, "e.md", b"x" * 11), max_bytes=10).status == "quarantined"


def test_an_undecodable_markdown_file_is_titled_by_its_name(memory, inbox):
    outcome = run(memory, drop(inbox, "Notes.md", b"# Title \xff"))
    assert outcome.entry["title"] == "Notes"


# Duplicates and names


def test_a_duplicate_writes_nothing_and_names_the_existing_entry(memory, inbox):
    first = run(memory, drop(inbox, "notes.md", NOTES))
    ledger_before = {p.name: p.read_bytes() for p in (memory / "ledger").iterdir()}
    copy_of_lf = NOTES.replace(b"\r\n", b"\n")
    again = run(memory, drop(inbox, "renamed.txt", b"\xef\xbb\xbf" + copy_of_lf), now=LATER)
    assert again.duplicate
    assert again.entry == first.entry
    assert {p.name: p.read_bytes() for p in (memory / "ledger").iterdir()} == ledger_before
    assert files_in(memory / "artifacts") == ["ART-0001-notes.md"]


def test_a_quarantined_entry_also_counts_as_a_duplicate(memory, inbox):
    run(memory, drop(inbox, "big.md", b"x" * 20), max_bytes=10)
    assert run(memory, drop(inbox, "big.md", b"x" * 20), max_bytes=10).status == "duplicate"


def test_a_rejected_file_can_be_ingested_again(memory, inbox):
    first = run(memory, drop(inbox, "blank.md", b"   "))
    assert first.status == "rejected"
    again = run(memory, drop(inbox, "blank.md", b"   "), now=LATER)
    assert again.status == "rejected"
    assert again.entry["id"] == "ART-0002"
    assert again.entry["same_name_as"] == ["ART-0001"]


def test_same_name_different_content_is_a_new_artifact_that_says_so(memory, inbox):
    run(memory, drop(inbox, "notes.md", b"# One\nfirst"))
    run(memory, drop(inbox, "Notes.md", b"# Two\nsecond"))
    run(memory, drop(inbox, "notes.pdf", b"third"))
    third = run(memory, drop(inbox, "notes.md", b"# Four\nfourth"))
    assert third.entry["id"] == "ART-0004"
    assert third.entry["same_name_as"] == ["ART-0001"]
    assert third.entry["stored_path"] == "artifacts/ART-0004-notes.md"
    assert files_in(memory / "artifacts") == [
        "ART-0001-notes.md",
        "ART-0002-notes.md",
        "ART-0004-notes.md",
    ]


def test_every_written_entry_is_valid_and_ids_increase(memory, inbox):
    for index, (name, raw) in enumerate(
        [("a.md", b"a"), ("b.pdf", b"b"), ("c.md", b"\xff"), ("d.txt", b"d")], start=1
    ):
        outcome = run(memory, drop(inbox, name, raw))
        assert outcome.entry["id"] == f"ART-{index:04d}"
    for path in (memory / "ledger").iterdir():
        assert validate_ledger_entry(json.loads(path.read_text(encoding="utf-8"))).ok


# Input problems write nothing


def test_an_unreadable_path_is_an_input_error(memory, inbox):
    with pytest.raises(InputError, match="Cannot read"):
        run(memory, inbox / "missing.md")
    with pytest.raises(InputError, match="Cannot read"):
        run(memory, inbox)
    assert not memory.exists()


@pytest.mark.parametrize("value", ["2026-02-30", "03/02/2026", "2026-3-2", "２０２６-03-02"])
def test_a_bad_artifact_date_is_an_input_error(memory, inbox, value):
    with pytest.raises(SensorInputError, match="--artifact-date must be a real date"):
        run(memory, drop(inbox, "notes.md", NOTES), artifact_date=value)
    assert not memory.exists()


def test_a_file_name_too_long_for_the_ledger_is_an_input_error(memory, tmp_path):
    with pytest.raises(SensorInputError, match="1 to 255 characters"):
        run(memory, tmp_path / ("x" * 256 + ".md"))


def test_an_existing_copy_is_never_overwritten(memory, inbox):
    (memory / "artifacts").mkdir(parents=True)
    (memory / "artifacts" / "ART-0001-notes.md").write_bytes(b"older")
    with pytest.raises(FileExistsError):
        run(memory, drop(inbox, "notes.md", NOTES))
    assert (memory / "artifacts" / "ART-0001-notes.md").read_bytes() == b"older"
    assert files_in(memory / "ledger") == []


# Release (6.7)


def quarantine(memory, inbox, raw=b"# Big\n" + b"x" * 50, name="big.md"):
    return run(memory, drop(inbox, name, raw), max_bytes=10).entry


def test_release_accepts_an_oversized_artifact_with_the_operators_reason(memory, inbox):
    entry = quarantine(memory, inbox)
    outcome = release_artifact(
        artifact_id=entry["id"], memory=memory, reason="  Read in full  ", now=LATER
    )
    assert outcome.released
    assert outcome.entry["status"] == "accepted"
    assert outcome.entry["history"][-1] == {
        "at": "2026-10-28T14:05:00Z",
        "status": "accepted",
        "by": "operator",
        "reason": "Read in full",
    }
    assert LedgerStore(memory).load(entry["id"]) == outcome.entry


@pytest.mark.parametrize(
    ("raw", "check"),
    [(b"caf\xe9" * 20, "encoding"), (b"# Notes\n</artifact>" + b"x" * 20, "delimiter")],
)
def test_release_refuses_while_another_check_still_fails(memory, inbox, raw, check):
    entry = quarantine(memory, inbox, raw)
    outcome = release_artifact(
        artifact_id=entry["id"], memory=memory, reason="Looked at it", now=LATER
    )
    assert not outcome.released
    assert outcome.check == check
    assert LedgerStore(memory).load(entry["id"]) == entry


def test_release_needs_a_quarantined_entry_and_a_reason(memory, inbox):
    accepted = run(memory, drop(inbox, "notes.md", NOTES)).entry
    with pytest.raises(SensorInputError, match="ART-0001 is accepted; only a quarantined"):
        release_artifact(artifact_id=accepted["id"], memory=memory, reason="Why not", now=LATER)
    with pytest.raises(LedgerEntryNotFoundError):
        release_artifact(artifact_id="ART-0009", memory=memory, reason="Why not", now=LATER)
    entry = quarantine(memory, inbox)
    for reason in ("", "   ", "x" * 501):
        with pytest.raises(SensorInputError, match="--reason must be 1 to 500 characters"):
            release_artifact(artifact_id=entry["id"], memory=memory, reason=reason, now=LATER)
    assert LedgerStore(memory).load(entry["id"]) == entry


# The Sensor itself touches no files


def test_assess_builds_the_entry_from_bytes_alone():
    entry = sensor.assess(
        raw=NOTES,
        name="Pilot Review.MD",
        artifact_id="ART-0007",
        artifact_date=None,
        same_name_as=["ART-0002"],
        max_bytes=100_000,
        now=NOW,
    )
    assert entry["status"] == "accepted"
    assert entry["stored_path"] == "artifacts/ART-0007-pilot-review.md"
    assert entry["same_name_as"] == ["ART-0002"]
    assert "artifact_date" not in entry
    assert validate_ledger_entry(entry).ok


def test_release_decides_from_the_copy_and_leaves_the_input_alone():
    entry = sensor.assess(
        raw=b"x" * 20,
        name="big.txt",
        artifact_id="ART-0001",
        artifact_date=None,
        same_name_as=[],
        max_bytes=10,
        now=NOW,
    )
    outcome = sensor.release(entry, b"x" * 20, reason="Fine", now=LATER)
    assert outcome.released and entry["status"] == "quarantined"
    assert validate_ledger_entry(outcome.entry).ok
