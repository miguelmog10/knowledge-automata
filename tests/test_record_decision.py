"""record-decision with the Comparator (reconciliation), end to end in a temporary folder."""

import dataclasses
import itertools
import json
from datetime import UTC, datetime, timedelta

import pytest

from knowledge_automata import cli, pipeline
from knowledge_automata.core.validation import validate_ledger_entry, validate_record
from knowledge_automata.domains.project_management.registers import DECISION_LOG
from knowledge_automata.llm import (
    LLMRateLimitError,
    MemorySink,
    ObservedLLM,
    RankedDocument,
)
from knowledge_automata.llm.fake import FakeLLM
from knowledge_automata.storage.ledger_store import LedgerStore
from knowledge_automata.storage.record_store import RecordStore

RUN_ID = "7d1c6a52-3b0e-4c47-9a57-0e6f2d1f9a10"
OTHER_RUN_ID = "0b6c1f0e-8c1d-4f57-b3a2-5d9e6c4a7f21"
SENTINEL = "SENTINEL-ARTIFACT-91c3 do not print this line"
COMPARATOR_RETRY = "decision-comparator.v1+comparator-retry.v1"

ARTIFACTS = [
    (
        "tech-sync-2026-02-03.md",
        "2026-02-03",
        "# Tech sync, 3 February\nWe agreed to build one Flutter app for iOS and Android.\n",
    ),
    (
        "board-2026-03-03.md",
        "2026-03-03",
        "# Board, 3 March\nEvery batch moves through one status ladder, whatever the crop.\n",
    ),
    (
        "tech-sync-2026-03-17.md",
        "2026-03-17",
        "# Tech sync, 17 March\nWe confirmed again that we build one Flutter app.\n",
    ),
    (
        "board-2026-03-31.md",
        "2026-03-31",
        "# Board, 31 March\nThe board kept the one status ladder because growers learn one "
        "screen.\n",
    ),
    (
        "board-2026-04-14.md",
        "2026-04-14",
        "# Board, 14 April\nWe drop Flutter and build two native apps instead.\n",
    ),
]

FLUTTER = {
    "content": {
        "title": "Build one Flutter app",
        "statement": "Build one Flutter app for iOS and Android.",
    },
    "evidence": ["We agreed to build one Flutter app for iOS and Android."],
}
LADDER = {
    "content": {
        "title": "One status ladder for every batch",
        "statement": "Every batch moves through one status ladder.",
    },
    "evidence": ["Every batch moves through one status ladder, whatever the crop."],
}
FLUTTER_AGAIN = {
    "content": {"title": "Build one Flutter app", "statement": "We build one Flutter app."},
    "evidence": ["We confirmed again that we build one Flutter app."],
}
LADDER_DETAIL = {
    "content": {
        "title": "One status ladder for every batch",
        "statement": "Keep one status ladder for every batch.",
        "rationale": "Growers learn one screen.",
    },
    "evidence": ["The board kept the one status ladder because growers learn one screen."],
}
NATIVE = {
    "content": {
        "title": "Build two native apps",
        "statement": "Drop Flutter and build two native apps.",
    },
    "evidence": ["We drop Flutter and build two native apps instead."],
}

# Rerank scores by a word in each record's text, so candidate order and scores are known.
SCORES = {"ladder": 0.93, "Flutter": 0.08}


def answer(classification, target_id=None, reason="Same outcome, more detail."):
    data = {"classification": classification, "reason": reason}
    if target_id is not None:
        data["target_id"] = target_id
    return data


class ScoredLLM(FakeLLM):
    def __init__(self, responses, embed_error=None):
        super().__init__(responses)
        self.embed_error = embed_error

    def embed(self, texts, *, input_type, context):
        if self.embed_error is not None:
            raise self.embed_error
        return super().embed(texts, input_type=input_type, context=context)

    def rerank(self, query, documents, *, top_n, context):
        result = super().rerank(query, documents, top_n=top_n, context=context)
        ranked = sorted(
            (RankedDocument(index, _score(text)) for index, text in enumerate(documents)),
            key=lambda item: (-item.score, item.index),
        )
        return dataclasses.replace(result, results=ranked[:top_n])


def _score(text):
    return next((score for word, score in SCORES.items() if word in text), 0.01)


class FakeBuild:
    def __init__(self, *responses, run_id=RUN_ID, embed_error=None):
        self.fake = ScoredLLM(responses, embed_error)
        self.sink = MemorySink()
        self.settings = []
        self.run_id = run_id

    def __call__(self, settings):
        self.settings.append(settings)
        return ObservedLLM(self.fake, provider="fake", sink=self.sink, run_id=self.run_id)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    for name in [
        "CO_API_KEY",
        "KA_CHAT_THINKING",
        "KA_CHAT_MODEL",
        "KA_EVENT_LOG",
        "KA_SENSOR_MAX_BYTES",
        "KA_COMPARATOR_TOP_K",
        "KA_COMPARATOR_TOP_N",
    ]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def clock():
    ticks = itertools.count()
    start = datetime(2026, 11, 2, 14, 0, 0, tzinfo=UTC)
    return lambda: start + timedelta(minutes=next(ticks))


@pytest.fixture
def memory(tmp_path, clock, capsys):
    """A memory folder with the five artifacts ingested, ART-0001 to ART-0005."""
    folder = tmp_path / "memory"
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    for name, date, text in ARTIFACTS:
        path = inbox / name
        path.write_bytes((text + SENTINEL + "\n").encode("utf-8"))
        code = cli.main(
            ["ingest", str(path), "--artifact-date", date, "--memory", str(folder)],
            build=FakeBuild(),
            clock=clock,
        )
        assert code == 0
    capsys.readouterr()
    return folder


def run(build, clock, *args):
    return cli.main(list(args), build=build, clock=clock)


def record(build, clock, memory, artifact_id):
    return run(build, clock, "record-decision", artifact_id, "--memory", str(memory))


def entry(memory, artifact_id):
    return LedgerStore(memory).load(artifact_id)


def records(memory):
    return {item["id"]: item for item in RecordStore(memory).load_all(DECISION_LOG)}


def record_first_two(memory, clock):
    assert record(FakeBuild(FLUTTER), clock, memory, "ART-0001") == 0
    build = FakeBuild(LADDER, answer("new", reason="Another topic."))
    assert record(build, clock, memory, "ART-0002") == 0


def test_the_four_classifications_from_an_empty_memory_folder(memory, clock, capsys):
    build = FakeBuild(FLUTTER)
    assert record(build, clock, memory, "ART-0001") == 0
    out = capsys.readouterr().out.splitlines()
    assert out[1:4] == [
        "Drafted a decision from ART-0001 in 1 attempt "
        "(model fake-chat, prompt decision-registrar.v1, thinking disabled)",
        "No active decisions to compare with: recorded as new without a comparison.",
        "Recorded DEC-0001 as a new decision",
    ]
    assert out[4].startswith("Billed: draft (input tokens ") and "embed" not in out[4]
    assert [call.operation for call in build.fake.calls] == ["chat"]

    build = FakeBuild(LADDER, answer("new", reason="Another topic."))
    assert record(build, clock, memory, "ART-0002") == 0
    out = capsys.readouterr().out.splitlines()
    assert out[2:5] == [
        "Compared with 1 active decision; candidates: DEC-0001 (0.08)",
        "Classified as new in 1 attempt (prompt decision-comparator.v1): Another topic.",
        "Recorded DEC-0002 as a new decision",
    ]
    assert [call.operation for call in build.fake.calls] == [
        "chat",
        "embed",
        "embed",
        "rerank",
        "chat",
    ]
    assert [event["agent"] for event in build.sink.events] == [
        "decision-registrar",
        "comparator",
        "comparator",
        "comparator",
        "comparator",
    ]

    build = FakeBuild(FLUTTER_AGAIN, answer("reaffirmation", "DEC-0001", "Says it again."))
    assert record(build, clock, memory, "ART-0003") == 0
    out = capsys.readouterr().out.splitlines()
    assert out[2:5] == [
        "Compared with 2 active decisions; candidates: DEC-0002 (0.93), DEC-0001 (0.08)",
        "Classified as reaffirmation of DEC-0001 in 1 attempt "
        "(prompt decision-comparator.v1): Says it again.",
        "Reaffirmed DEC-0001 (revision 2): added 1 source",
    ]

    build = FakeBuild(LADDER_DETAIL, answer("update", "DEC-0002", "Same ladder,\nwith a reason."))
    assert record(build, clock, memory, "ART-0004") == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == f"Run ID: {RUN_ID}"
    assert out[2:6] == [
        "Compared with 2 active decisions; candidates: DEC-0002 (0.93), DEC-0001 (0.08)",
        "Classified as update of DEC-0002 in 1 attempt "
        "(prompt decision-comparator.v1): Same ladder, with a reason.",
        "Updated DEC-0002 to revision 2: filled rationale",
        "Kept the existing statement in DEC-0002 (the draft's wording differs; a change of "
        "substance would be a supersession)",
    ]
    billed = out[6]
    assert billed.startswith("Billed: draft (input tokens ")
    assert "; comparison (input tokens " in billed
    assert "; embed (input tokens " in billed
    assert billed.endswith("; rerank (search units 1)")
    assert out[7].endswith("memory/registers/decision-log/DEC-0002.json")
    assert out[8].endswith("memory/views/decision-log.md")

    build = FakeBuild(NATIVE, answer("supersession", "DEC-0001", "Flutter is dropped."))
    assert record(build, clock, memory, "ART-0005") == 0
    out = capsys.readouterr().out.splitlines()
    assert out[4] == "Recorded DEC-0003, superseding DEC-0001 (now superseded)"
    assert out[6].endswith("memory/registers/decision-log/DEC-0003.json")

    stored = records(memory)
    for item in stored.values():
        assert validate_record(item, DECISION_LOG).ok, item["id"]
    flutter, ladder, native = stored["DEC-0001"], stored["DEC-0002"], stored["DEC-0003"]
    assert (flutter["revision"], flutter["record_status"]) == (3, "superseded")
    assert flutter["relations"] == {"superseded_by": "DEC-0003"}
    assert [step["change"] for step in flutter["history"]] == [
        "new",
        "reaffirmation",
        "superseded",
    ]
    assert [source["artifact_id"] for source in flutter["sources"]] == ["ART-0001", "ART-0003"]
    assert flutter["content"] == FLUTTER["content"]

    assert ladder["revision"] == 2 and ladder["record_status"] == "active"
    assert ladder["content"] == LADDER["content"] | {"rationale": "Growers learn one screen."}
    assert ladder["history"][-1]["fields"] == ["rationale"]
    assert ladder["sources"][-1]["artifact_date"] == "2026-03-31"

    assert native["relations"] == {"supersedes": ["DEC-0001"]}
    assert native["history"][0]["change"] == "supersession"
    assert native["history"][0]["related_id"] == "DEC-0001"

    assert pipeline.supersession_link_problems(memory) == []
    for artifact_id in ("ART-0001", "ART-0002", "ART-0003", "ART-0004", "ART-0005"):
        assert validate_ledger_entry(entry(memory, artifact_id)).ok, artifact_id
        assert entry(memory, artifact_id)["schema_version"] == "1.1"

    assert entry(memory, "ART-0001")["produced"] == [
        {
            "register": "decision-log",
            "record_id": "DEC-0001",
            "change": "new",
            "model": "fake-chat",
            "prompt_version": "decision-registrar.v1",
            "schema_version": "1.0",
        }
    ]
    (superseding,) = entry(memory, "ART-0005")["produced"]
    assert list(superseding) == [
        "register",
        "record_id",
        "change",
        "related_id",
        "model",
        "prompt_version",
        "schema_version",
        "comparison",
    ]
    assert superseding["record_id"] == "DEC-0003" and superseding["related_id"] == "DEC-0001"
    assert superseding["comparison"] == {
        "model": "fake-chat",
        "prompt_version": "decision-comparator.v1",
        "attempts": 1,
        "candidates": [
            {"record_id": "DEC-0002", "score": 0.93},
            {"record_id": "DEC-0001", "score": 0.08},
        ],
    }
    (updated,) = entry(memory, "ART-0004")["produced"]
    assert (updated["change"], updated["record_id"]) == ("update", "DEC-0002")
    assert "related_id" not in updated

    assert run(FakeBuild(), clock, "views", "--memory", str(memory), "--check") == 0
    capsys.readouterr()
    assert run(FakeBuild(), clock, "ledger", "--memory", str(memory)) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].endswith("(new DEC-0001)")
    assert lines[2].endswith("(reaffirmation DEC-0001)")
    assert lines[3].endswith("(update DEC-0002)")
    assert lines[4].endswith("(supersession DEC-0003, superseding DEC-0001)")


def test_a_rejected_comparison_writes_nothing_and_a_rerun_keeps_it(memory, clock, capsys):
    assert record(FakeBuild(FLUTTER), clock, memory, "ART-0001") == 0
    before = (memory / "registers" / "decision-log" / "DEC-0001.json").read_bytes()
    views = (memory / "views" / "decision-log.md").read_bytes()
    capsys.readouterr()

    bad = answer("update", "DEC-0009")
    assert record(FakeBuild(LADDER, bad, bad), clock, memory, "ART-0002") == 1
    out, err = capsys.readouterr()
    assert (
        "Rejected the comparison for ART-0002 after 2 attempts "
        f"(prompt {COMPARATOR_RETRY}); no record was written"
    ) in err
    assert "- $.target_id: 'DEC-0009' was not one of the candidates" in err
    assert "Compared with 1 active decision; candidates: DEC-0001 (0.08)" in out
    assert "; rerank (search units 1)" in out
    assert list(records(memory)) == ["DEC-0001"]
    assert (memory / "registers" / "decision-log" / "DEC-0001.json").read_bytes() == before
    assert (memory / "views" / "decision-log.md").read_bytes() == views

    rejected = entry(memory, "ART-0002")
    assert rejected["status"] == "processed" and rejected["produced"] == []
    first = {
        "register": "decision-log",
        "stage": "comparison",
        "run_id": RUN_ID,
        "attempts": 2,
        "prompt_version": COMPARATOR_RETRY,
        "error_paths": ["$.target_id"],
    }
    assert rejected["rejected"] == [first]

    build = FakeBuild(LADDER, answer("new"), run_id=OTHER_RUN_ID)
    assert record(build, clock, memory, "ART-0002") == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "Rerunning ART-0002: its earlier run recorded nothing."
    assert out[1] == f"Run ID: {OTHER_RUN_ID}"
    rerun = entry(memory, "ART-0002")
    assert validate_ledger_entry(rerun).ok
    assert rerun["rejected"] == [first]
    assert rerun["produced"][0]["record_id"] == "DEC-0002"
    assert [step["status"] for step in rerun["history"]][-2:] == ["processed", "processed"]
    assert rerun["history"][-1]["reason"] == "Rerun: the earlier run recorded nothing"
    assert rerun["history"][-1]["run_id"] == OTHER_RUN_ID


def test_rejected_drafts_accumulate_and_survive_a_failed_rerun(memory, clock, capsys):
    bad_draft = FLUTTER | {"evidence": ["We chose React Native."]}
    assert record(FakeBuild(bad_draft, bad_draft), clock, memory, "ART-0001") == 1
    first = entry(memory, "ART-0001")["rejected"]
    assert [(item["stage"], item["run_id"]) for item in first] == [("draft", RUN_ID)]

    error = LLMRateLimitError("slow down")
    assert record(FakeBuild(error, run_id=OTHER_RUN_ID), clock, memory, "ART-0001") == 3
    failed = entry(memory, "ART-0001")
    assert failed["status"] == "failed" and failed["rejected"] == first
    assert failed["history"][-1]["reason"] == "Rerun: the earlier run recorded nothing"
    assert validate_ledger_entry(failed).ok

    assert record(FakeBuild(bad_draft, bad_draft), clock, memory, "ART-0001") == 1
    assert record(FakeBuild(FLUTTER, run_id=OTHER_RUN_ID), clock, memory, "ART-0001") == 0
    done = entry(memory, "ART-0001")
    assert validate_ledger_entry(done).ok
    assert [item["stage"] for item in done["rejected"]] == ["draft", "draft"]
    assert done["rejected"][0] == first[0]
    assert done["produced"][0]["record_id"] == "DEC-0001"
    assert [step["status"] for step in done["history"]] == [
        "received",
        "accepted",
        "processed",
        "failed",
        "processed",
        "processed",
    ]
    # From failed it is a retry, not a rerun of a processed entry.
    assert "reason" not in done["history"][-2]
    assert done["history"][-1]["reason"] == "Rerun: the earlier run recorded nothing"


def test_an_artifact_that_produced_a_record_is_not_rerun(memory, clock, capsys):
    record_first_two(memory, clock)
    capsys.readouterr()
    build = FakeBuild(LADDER)
    assert record(build, clock, memory, "ART-0002") == 2
    assert "ART-0002 is already processed (recorded in DEC-0002)" in capsys.readouterr().err
    assert build.settings == []


def test_an_interrupted_supersession_stops_record_decision_and_views(
    memory, clock, monkeypatch, capsys
):
    record_first_two(memory, clock)

    def interrupted(self, old, new, spec):
        raise OSError(28, "No space left on device", "DEC-0001.json")

    with monkeypatch.context() as patch:
        patch.setattr(RecordStore, "save_revision", interrupted)
        build = FakeBuild(NATIVE, answer("supersession", "DEC-0001"))
        assert record(build, clock, memory, "ART-0005") == 2
    stored = records(memory)
    assert stored["DEC-0003"]["relations"] == {"supersedes": ["DEC-0001"]}
    assert stored["DEC-0001"]["record_status"] == "active"
    assert entry(memory, "ART-0005")["status"] == "accepted"
    capsys.readouterr()

    expected = (
        "DEC-0003 supersedes DEC-0001, but DEC-0001 is still active: a supersession was "
        "interrupted. Finish it by marking DEC-0001 superseded by DEC-0003"
    )
    for artifact_id in ("ART-0005", "ART-0003"):
        build = FakeBuild(FLUTTER_AGAIN)
        assert record(build, clock, memory, artifact_id) == 2
        err = capsys.readouterr().err
        assert expected in err and "nothing was sent to the model" in err
        assert build.settings == []

    for extra in ([], ["--check"]):
        assert run(FakeBuild(), clock, "views", "--memory", str(memory), *extra) == 2
        err = capsys.readouterr().err
        assert expected in err and "No view was written or checked." in err


@pytest.mark.parametrize("stage", ["embed", "chat"])
def test_a_provider_error_during_the_comparison_marks_the_artifact_failed(
    memory, clock, capsys, stage
):
    assert record(FakeBuild(FLUTTER), clock, memory, "ART-0001") == 0
    before = (memory / "registers" / "decision-log" / "DEC-0001.json").read_bytes()
    error = LLMRateLimitError("slow down")
    if stage == "embed":
        build = FakeBuild(FLUTTER_AGAIN, embed_error=error)
    else:
        build = FakeBuild(FLUTTER_AGAIN, error)
    assert record(build, clock, memory, "ART-0003") == 3
    assert "ART-0003 is now failed in the Ledger" in capsys.readouterr().err
    failed = entry(memory, "ART-0003")
    assert failed["status"] == "failed"
    assert failed["history"][-1]["error_type"] == "LLMRateLimitError"
    assert (memory / "registers" / "decision-log" / "DEC-0001.json").read_bytes() == before
    assert list(records(memory)) == ["DEC-0001"]


@pytest.mark.parametrize(
    ("env", "fragment"),
    [
        ({"KA_COMPARATOR_TOP_K": "0"}, "KA_COMPARATOR_TOP_K must be a whole number"),
        ({"KA_COMPARATOR_TOP_N": "many"}, "KA_COMPARATOR_TOP_N must be a whole number"),
        (
            {"KA_COMPARATOR_TOP_K": "2"},
            "KA_COMPARATOR_TOP_N (3) cannot be greater than KA_COMPARATOR_TOP_K (2)",
        ),
    ],
)
def test_bad_comparator_settings_exit_2_with_no_call(
    memory, clock, monkeypatch, capsys, env, fragment
):
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    build = FakeBuild(FLUTTER)
    assert record(build, clock, memory, "ART-0001") == 2
    assert fragment in capsys.readouterr().err
    assert build.settings == []
    assert entry(memory, "ART-0001")["status"] == "accepted"


def test_comparator_settings_reach_retrieval(memory, clock, monkeypatch, capsys):
    record_first_two(memory, clock)
    monkeypatch.setenv("KA_COMPARATOR_TOP_K", "1")
    monkeypatch.setenv("KA_COMPARATOR_TOP_N", "1")
    build = FakeBuild(FLUTTER_AGAIN, answer("new"))
    assert record(build, clock, memory, "ART-0003") == 0
    rerank = next(call for call in build.fake.calls if call.operation == "rerank")
    assert len(rerank.inputs["documents"]) == 1 and rerank.inputs["top_n"] == 1
    user = build.fake.calls[-1].inputs["user"]
    shown = json.loads(user.removeprefix("<comparison>\n").removesuffix("\n</comparison>"))
    assert len(shown["existing_records"]) == 1
    assert "candidates: DEC-000" in capsys.readouterr().out


def test_no_output_contains_the_artifact_text(memory, clock, capsys):
    record_first_two(memory, clock)
    bad = answer("update", "DEC-0009")
    reaffirm = answer("reaffirmation", "DEC-0001")
    record(FakeBuild(FLUTTER_AGAIN, reaffirm), clock, memory, "ART-0003")
    record(FakeBuild(LADDER_DETAIL, bad, bad), clock, memory, "ART-0004")
    record(FakeBuild(NATIVE, LLMRateLimitError("slow down")), clock, memory, "ART-0005")
    run(FakeBuild(), clock, "ledger", "--memory", str(memory))
    out, err = capsys.readouterr()
    for text in (out, err):
        assert SENTINEL not in text
        for _, _, artifact in ARTIFACTS:
            for line in artifact.splitlines()[1:]:
                assert line not in text
