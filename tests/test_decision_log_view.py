from pathlib import Path

import pytest

from knowledge_automata.core.validation import validate_record
from knowledge_automata.domains.project_management.decision_log_view import (
    OWNED,
    render_decision_log,
)
from knowledge_automata.domains.project_management.registers import DECISION_LOG
from knowledge_automata.views.markdown import check_views, relative_link, write_views

EXPECTED = Path(__file__).parent / "fixtures" / "views"


def record(record_id, content, sources, history, **envelope):
    built = {
        "id": record_id,
        "register": "decision-log",
        "schema_version": "1.0",
        "record_status": "active",
        "revision": len(history),
        "created_at": history[0]["at"],
        "updated_at": history[-1]["at"],
        "content": content,
        "sources": sources,
        **envelope,
        "history": history,
    }
    result = validate_record(built, DECISION_LOG)
    assert result.ok, result.errors
    return built


def source(artifact_id, excerpt, at, date=None):
    entry = {"artifact_id": artifact_id}
    if date:
        entry["artifact_date"] = date
    return entry | {"excerpt": excerpt, "added_at": at}


def entry(revision, at, change, artifact_id, fields=None, model=None, prompt=None, related=None):
    built = {"revision": revision, "at": at, "change": change, "artifact_id": artifact_id}
    if fields is not None:
        built["fields"] = fields
    if related:
        built["related_id"] = related
    if model:
        built["model"] = model
    if prompt:
        built["prompt_version"] = prompt
    return built


def minimal_records():
    at = "2026-10-26T14:03:12Z"
    return [
        record(
            "DEC-0002",
            {"title": "Meet on Tuesdays", "statement": "The team meets every Tuesday."},
            [source("ART-0002", "We will meet every Tuesday.", at)],
            [
                entry(
                    1,
                    at,
                    "new",
                    "ART-0002",
                    ["title", "statement"],
                    "fake-chat",
                    "decision-registrar.v1+registrar-retry.v1",
                )
            ],
        )
    ]


def superseded_records():
    first_at, second_at = "2026-01-10T10:00:00Z", "2026-02-10T10:00:00Z"
    old = record(
        "DEC-0001",
        {"title": "Meet on Tuesdays", "statement": "The team meets every Tuesday."},
        [source("ART-0003", "We meet every Tuesday.", first_at, "2026-01-10")],
        [
            entry(
                1,
                first_at,
                "new",
                "ART-0003",
                ["title", "statement"],
                "fake-chat",
                "decision-registrar.v1",
            ),
            entry(2, second_at, "superseded", "ART-0004", related="DEC-0002"),
        ],
        record_status="superseded",
        relations={"superseded_by": "DEC-0002"},
    )
    new = record(
        "DEC-0002",
        {
            "title": "Meet on Wednesdays",
            "statement": "The team meets every Wednesday instead of Tuesday.",
        },
        [source("ART-0004", "From now on we meet on Wednesdays.", second_at, "2026-02-10")],
        [
            entry(
                1,
                second_at,
                "supersession",
                "ART-0004",
                ["title", "statement"],
                "fake-chat",
                "decision-registrar.v1",
                related="DEC-0001",
            )
        ],
        relations={"supersedes": ["DEC-0001"]},
    )
    return [new, old]  # out of order on purpose: views sort by ID


def revised_records():
    first, second, third = "2026-02-03T09:00:00Z", "2026-03-03T09:00:00Z", "2026-03-31T09:00:00Z"
    ladder = record(
        "DEC-0001",
        {
            "title": "One status ladder for every batch",
            "statement": "Every batch moves through one status ladder.",
            "rationale": "Growers learn one screen.",
        },
        [
            source("ART-0001", "Every batch moves through one status ladder.", first, "2026-02-03"),
            source("ART-0001", "Whatever the crop.", first, "2026-02-03"),
            source("ART-0002", "We confirmed the single ladder.", second, "2026-03-03"),
            source("ART-0003", "Growers learn one screen.", third),
        ],
        [
            entry(1, first, "new", "ART-0001", ["title", "statement"], "fake-chat", "registrar.v1"),
            entry(2, second, "reaffirmation", "ART-0002", None, "fake-chat", "registrar.v1"),
            entry(3, third, "update", "ART-0003", ["rationale"], "fake-chat", "registrar.v1"),
        ],
    )
    labels = record(
        "DEC-0002",
        {"title": "Print bench labels", "statement": "Print a label for every bench."},
        [
            source("ART-0002", "Every bench gets a printed label.", second, "2026-03-03"),
            source("ART-0003", "Labels stay printed.", third),
        ],
        [
            entry(
                1, second, "new", "ART-0002", ["title", "statement"], "fake-chat", "registrar.v1"
            ),
            entry(2, third, "update", "ART-0003", [], "fake-chat", "registrar.v1"),
        ],
    )
    return [ladder, labels]


def escaping_records():
    at = "2026-04-01T08:00:00Z"
    return [
        record(
            "DEC-0001",
            {
                "title": "Use A|B *now* <today>",
                "statement": "Pick <b>option</b> one,\nthen [review] it.",
                "context": "Cost | time\r\ntrade_off `x` \\ y",
                "alternatives": ["Option *two*\nlater"],
                "decided_by": ["Ana_R", "Tom|B"],
            },
            [source("ART-0005", "line one *a*\nline <two>", at, "2026-04-01")],
            [entry(1, at, "new", "ART-0005", ["title"], "m_1", "p|1")],
        )
    ]


def expected_files(case):
    folder = EXPECTED / case
    return {
        path.relative_to(folder).as_posix(): path.read_bytes().decode("utf-8").replace("\r\n", "\n")
        for path in folder.rglob("*.md")
    }


CASES = {
    "full": lambda fixture: (
        [fixture],
        {"ART-0001": "artifacts/ART-0001-steering-group.md"},
    ),
    "minimal": lambda fixture: (minimal_records(), {}),
    "superseded": lambda fixture: (superseded_records(), {"ART-0003": "artifacts/ART-0003.md"}),
    "revised": lambda fixture: (
        revised_records(),
        {"ART-0001": "artifacts/ART-0001-tech-sync.md", "ART-0003": "artifacts/ART-0003.md"},
    ),
    "escaping": lambda fixture: (escaping_records(), {"ART-0009": "artifacts/ART-0009.md"}),
    "empty": lambda fixture: ([], {}),
}


@pytest.mark.parametrize("case", sorted(CASES))
def test_rendered_views_match_the_hand_written_files(case, decision_record):
    records, links = CASES[case](decision_record)
    assert render_decision_log(records, links) == expected_files(case)


def test_same_records_render_identical_bytes():
    links = {"ART-0003": "artifacts/ART-0003.md"}
    first = render_decision_log(superseded_records(), links)
    second = render_decision_log(list(reversed(superseded_records())), links)
    assert {path: text.encode("utf-8") for path, text in first.items()} == {
        path: text.encode("utf-8") for path, text in second.items()
    }


def test_relative_links_use_forward_slashes():
    assert (
        relative_link("decision-log.md", "decision-log/DEC-0001.md") == "decision-log/DEC-0001.md"
    )
    assert relative_link("decision-log/DEC-0001.md", "decision-log.md") == "../decision-log.md"
    assert (
        relative_link("views/decision-log/DEC-0001.md", "artifacts/ART-0001 notes.md")
        == "../../artifacts/ART-0001%20notes.md"
    )


def views(tmp_path, decision_record):
    files = render_decision_log([decision_record], {})
    return tmp_path / "views", files


def test_check_views_reports_missing_changed_and_extra(tmp_path, decision_record):
    views_dir, files = views(tmp_path, decision_record)
    differences = check_views(views_dir, files, OWNED)
    assert differences.missing == ("decision-log.md", "decision-log/DEC-0001.md")
    assert not differences.ok

    write_views(views_dir, files, OWNED)
    assert check_views(views_dir, files, OWNED).ok

    (views_dir / "decision-log.md").write_text("edited by hand\n", encoding="utf-8")
    (views_dir / "decision-log" / "DEC-0099.md").write_text("stale\n", encoding="utf-8")
    (views_dir / "notes.md").write_text("not owned\n", encoding="utf-8")
    differences = check_views(views_dir, files, OWNED)
    assert differences.missing == ()
    assert differences.changed == ("decision-log.md",)
    assert differences.extra == ("decision-log/DEC-0099.md",)


def test_check_views_ignores_crlf_versus_lf(tmp_path, decision_record):
    views_dir, files = views(tmp_path, decision_record)
    write_views(views_dir, files, OWNED)
    for path in files:
        target = views_dir / path
        target.write_bytes(target.read_bytes().replace(b"\n", b"\r\n"))
    assert check_views(views_dir, files, OWNED).ok
    # A file that differs only in line endings is not rewritten.
    assert write_views(views_dir, files, OWNED).ok
    assert b"\r\n" in (views_dir / "decision-log.md").read_bytes()


def test_write_views_writes_lf_and_deletes_only_stale_owned_files(tmp_path, decision_record):
    views_dir, files = views(tmp_path, decision_record)
    (views_dir / "decision-log").mkdir(parents=True)
    (views_dir / "decision-log" / "DEC-0099.md").write_text("stale\n", encoding="utf-8")
    (views_dir / "decision-log" / "keep.txt").write_text("not a view\n", encoding="utf-8")
    (views_dir / "risk-register.md").write_text("another generator\n", encoding="utf-8")

    written = write_views(views_dir, files, OWNED)
    assert written.extra == ("decision-log/DEC-0099.md",)
    assert not (views_dir / "decision-log" / "DEC-0099.md").exists()
    assert (views_dir / "decision-log" / "keep.txt").exists()
    assert (views_dir / "risk-register.md").exists()
    for path in files:
        assert b"\r" not in (views_dir / path).read_bytes()


def test_views_refuse_files_the_generator_does_not_own(tmp_path):
    with pytest.raises(ValueError):
        check_views(tmp_path, {"risk-register.md": "x"}, OWNED)
