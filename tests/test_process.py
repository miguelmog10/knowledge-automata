"""process with the Governor (orchestrator), the Decision Registrar and the Comparator
(reconciliation), end to end in a temporary folder."""

import dataclasses
import io
import itertools
import json
import re
import sys
from datetime import UTC, datetime, timedelta

import pytest

from knowledge_automata import cli, pipeline
from knowledge_automata.core.validation import (
    validate_ledger_entry,
    validate_record,
    validate_work_orders_file,
)
from knowledge_automata.domains.project_management.registers import DECISION_LOG
from knowledge_automata.llm import (
    LLMRateLimitError,
    LLMResponseError,
    MemorySink,
    ObservedLLM,
    RankedDocument,
    Usage,
)
from knowledge_automata.llm.fake import FakeLLM
from knowledge_automata.storage.ledger_store import LedgerStore
from knowledge_automata.storage.record_store import RecordStore
from knowledge_automata.storage.work_order_store import WorkOrderStore

RUN_ID = "7d1c6a52-3b0e-4c47-9a57-0e6f2d1f9a10"
OTHER_RUN_ID = "0b6c1f0e-8c1d-4f57-b3a2-5d9e6c4a7f21"
SENTINEL = "SENTINEL-ARTIFACT-91c3 do not print this line"
COMPARATOR_RETRY = "decision-comparator.v2+comparator-retry.v2"
FOUND = (
    "in 1 attempt (model fake-chat, prompt governor.v2, definitions decision-log.v1, "
    "risk-register.v1, thinking enabled)"
)

REPORTS_QUOTE = "We adopt weekly harvest reports from May."
STALL_QUOTE = "We move the market stall to Saturdays."
VAN_QUOTE = "The van may fail its spring inspection."
KEEP_QUOTE = "We keep one Flutter app because one team maintains it."
AGAIN_QUOTE = "Once more, one Flutter app for both stores."

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
    (
        "board-2026-04-28.md",
        "2026-04-28",
        "# Board, 28 April\n"
        + "".join(
            f"{quote}\n"
            for quote in (REPORTS_QUOTE, STALL_QUOTE, VAN_QUOTE, KEEP_QUOTE, AGAIN_QUOTE)
        ),
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
REPORTS = {
    "content": {"title": "Weekly harvest reports", "statement": "Adopt weekly harvest reports."},
    "evidence": [REPORTS_QUOTE],
}
STALL = {
    "content": {"title": "Market stall on Saturdays", "statement": "Move the stall to Saturdays."},
    "evidence": [STALL_QUOTE],
}
KEEP = {
    "content": {"title": "Keep one Flutter app", "statement": "Keep one Flutter app."},
    "evidence": [KEEP_QUOTE],
}
AGAIN = {
    "content": {"title": "Keep one Flutter app", "statement": "One Flutter app for both stores."},
    "evidence": [AGAIN_QUOTE],
}
# A draft quoting text that is not in the artifact (nor in its work order).
BAD = {"content": {"title": "React Native", "statement": "Use React Native."}, "evidence": ["x"]}


def decisions(*quotes):
    """The Governor's reply: one decision-log work order per quote."""
    return {"items": [{"register": "decision-log", "evidence": [quote]} for quote in quotes]}


def order(draft):
    """The Governor's reply for an artifact with the one decision ``draft`` quotes."""
    return decisions(*draft["evidence"])


# ART-0006: two decisions and a risk, the risk listed between them; sorted by position.
MIXED = {
    "items": [
        {"register": "decision-log", "evidence": [REPORTS_QUOTE]},
        {"register": "risk-register", "evidence": [VAN_QUOTE]},
        {"register": "decision-log", "evidence": [STALL_QUOTE]},
    ]
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

    @property
    def agents(self):
        return [event["agent"] for event in self.sink.events]


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
        "KA_GOVERNOR_MAX_ITEMS",
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
    """A memory folder with the six artifacts ingested, ART-0001 to ART-0006."""
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


def process(build, clock, memory, artifact_id):
    return run(build, clock, "process", artifact_id, "--memory", str(memory))


def entry(memory, artifact_id):
    return LedgerStore(memory).load(artifact_id)


def work_orders(memory, artifact_id):
    return WorkOrderStore(memory).load(artifact_id)


def states(memory, artifact_id):
    return [item["state"] for item in work_orders(memory, artifact_id)["orders"]]


def statuses(memory, artifact_id):
    return [step["status"] for step in entry(memory, artifact_id)["history"]]


def listed(items):
    """``(record_id, work_order)`` or ``(stage, work_order)`` for each Ledger list item."""
    return [(item.get("record_id", item.get("stage")), item.get("work_order")) for item in items]


def records(memory):
    return {item["id"]: item for item in RecordStore(memory).load_all(DECISION_LOG)}


def valid(memory, artifact_id):
    """The Ledger entry and the work orders file (if any) pass their checks."""
    result = validate_ledger_entry(entry(memory, artifact_id))
    assert result.ok, result.errors
    file = work_orders(memory, artifact_id)
    if file is not None:
        result = validate_work_orders_file(file)
        assert result.ok, result.errors
    return True


def record_first_two(memory, clock):
    assert process(FakeBuild(order(FLUTTER), FLUTTER), clock, memory, "ART-0001") == 0
    build = FakeBuild(order(LADDER), LADDER, answer("new", reason="Another topic."))
    assert process(build, clock, memory, "ART-0002") == 0


def failing_after(count, error):
    """A replacement for a method that runs the real one ``count`` times, then raises."""
    calls = itertools.count(1)

    def wrap(real):
        def replacement(*args, **kwargs):
            if next(calls) > count:
                raise error
            return real(*args, **kwargs)

        return replacement

    return wrap


DISK_FULL = OSError(28, "No space left on device", "ART-0006.json")


# One decision per artifact (the record-decision scenarios, now through process)


def test_the_four_classifications_from_an_empty_memory_folder(memory, clock, capsys):
    build = FakeBuild(order(FLUTTER), FLUTTER)
    assert process(build, clock, memory, "ART-0001") == 0
    out = capsys.readouterr().out.splitlines()
    assert out[1:7] == [
        f"Found 1 work order in ART-0001 {FOUND}: 1 decision-log",
        'Work order 1 of 1, decision-log: "We agreed to build one Flutter app for iOS and '
        'Android."',
        "  Drafted in 1 attempt (prompt decision-registrar.v3)",
        "  No active decisions to compare with: recorded as new without a comparison",
        "  Recorded DEC-0001 as a new decision",
        "Recorded 1 of 1 routed work order; 0 rejected; 0 not routed",
    ]
    assert out[7].startswith("Billed: governor (input tokens ")
    assert "; drafts (input tokens " in out[7] and "embed" not in out[7]
    assert [call.operation for call in build.fake.calls] == ["chat", "chat"]

    build = FakeBuild(order(LADDER), LADDER, answer("new", reason="Another topic."))
    assert process(build, clock, memory, "ART-0002") == 0
    out = capsys.readouterr().out.splitlines()
    assert out[4:7] == [
        "  Compared with 1 active decision; candidates: DEC-0001 (0.08)",
        "  Classified as new in 1 attempt (prompt decision-comparator.v2): Another topic.",
        "  Recorded DEC-0002 as a new decision",
    ]
    assert [call.operation for call in build.fake.calls] == [
        "chat",
        "chat",
        "embed",
        "embed",
        "rerank",
        "chat",
    ]
    assert build.agents == [
        "governor",
        "decision-registrar",
        "comparator",
        "comparator",
        "comparator",
        "comparator",
    ]

    reaffirm = answer("reaffirmation", "DEC-0001", "Says it again.")
    build = FakeBuild(order(FLUTTER_AGAIN), FLUTTER_AGAIN, reaffirm)
    assert process(build, clock, memory, "ART-0003") == 0
    out = capsys.readouterr().out.splitlines()
    assert out[4:7] == [
        "  Compared with 2 active decisions; candidates: DEC-0002 (0.93), DEC-0001 (0.08)",
        "  Classified as reaffirmation of DEC-0001 in 1 attempt "
        "(prompt decision-comparator.v2): Says it again.",
        "  Reaffirmed DEC-0001 (revision 2): added 1 source",
    ]

    update = answer("update", "DEC-0002", "Same ladder,\nwith a reason.")
    build = FakeBuild(order(LADDER_DETAIL), LADDER_DETAIL, update)
    assert process(build, clock, memory, "ART-0004") == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == f"Run ID: {RUN_ID}"
    assert out[4:9] == [
        "  Compared with 2 active decisions; candidates: DEC-0002 (0.93), DEC-0001 (0.08)",
        "  Classified as update of DEC-0002 in 1 attempt "
        "(prompt decision-comparator.v2): Same ladder, with a reason.",
        "  Updated DEC-0002 to revision 2: filled rationale",
        "  Kept the existing statement in DEC-0002 (the draft's wording differs; a change of "
        "substance would be a supersession)",
        "Recorded 1 of 1 routed work order; 0 rejected; 0 not routed",
    ]
    billed = out[9]
    assert billed.startswith("Billed: governor (input tokens ")
    assert "; drafts (input tokens " in billed
    assert "; comparisons (input tokens " in billed
    assert "; embed (input tokens " in billed
    assert billed.endswith("; rerank (search units 1)")
    assert out[10] == f"Index: {(memory / 'views' / 'decision-log.md').as_posix()}"

    build = FakeBuild(order(NATIVE), NATIVE, answer("supersession", "DEC-0001", "Dropped."))
    assert process(build, clock, memory, "ART-0005") == 0
    out = capsys.readouterr().out.splitlines()
    assert out[6] == "  Recorded DEC-0003, superseding DEC-0001 (now superseded)"

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
    assert flutter["history"][0]["prompt_version"] == "decision-registrar.v3"

    assert ladder["revision"] == 2 and ladder["record_status"] == "active"
    assert ladder["content"] == LADDER["content"] | {"rationale": "Growers learn one screen."}
    assert ladder["history"][-1]["fields"] == ["rationale"]
    assert ladder["sources"][-1]["artifact_date"] == "2026-03-31"

    assert native["relations"] == {"supersedes": ["DEC-0001"]}
    assert native["history"][0]["change"] == "supersession"
    assert native["history"][0]["related_id"] == "DEC-0001"

    assert pipeline.supersession_link_problems(memory) == []
    for artifact_id in ("ART-0001", "ART-0002", "ART-0003", "ART-0004", "ART-0005"):
        assert valid(memory, artifact_id)
        assert entry(memory, artifact_id)["schema_version"] == "1.2"
        assert states(memory, artifact_id) == ["recorded"]

    assert entry(memory, "ART-0001")["produced"] == [
        {
            "register": "decision-log",
            "record_id": "DEC-0001",
            "change": "new",
            "model": "fake-chat",
            "prompt_version": "decision-registrar.v3",
            "schema_version": "1.0",
            "work_order": 1,
        }
    ]
    (superseding,) = entry(memory, "ART-0005")["produced"]
    assert list(superseding) == [
        "register",
        "work_order",
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
        "prompt_version": "decision-comparator.v2",
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
    pages = memory / "views" / "decision-log"
    flutter_page = (pages / "DEC-0001.md").read_text(encoding="utf-8")
    assert "### [ART-0001](../../artifacts/ART-0001-tech-sync-2026-02-03.md), 2026-02-03\n" in (
        flutter_page
    )
    assert "### [ART-0003](../../artifacts/ART-0003-tech-sync-2026-03-17.md), 2026-03-17\n" in (
        flutter_page
    )
    assert "| superseded | Superseded by [DEC-0003](DEC-0003.md) | ART-0005 |" in flutter_page
    assert "| update | Filled: rationale | ART-0004 |" in (pages / "DEC-0002.md").read_text(
        encoding="utf-8"
    )
    assert "| supersession | Supersedes [DEC-0001](DEC-0001.md) | ART-0005 |" in (
        pages / "DEC-0003.md"
    ).read_text(encoding="utf-8")
    assert run(FakeBuild(), clock, "ledger", "--memory", str(memory)) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].endswith("(new DEC-0001)")
    assert lines[2].endswith("(reaffirmation DEC-0001)")
    assert lines[3].endswith("(update DEC-0002)")
    assert lines[4].endswith("(supersession DEC-0003, superseding DEC-0001)")


def test_a_rejected_comparison_writes_nothing_and_a_rerun_keeps_it(memory, clock, capsys):
    assert process(FakeBuild(order(FLUTTER), FLUTTER), clock, memory, "ART-0001") == 0
    before = (memory / "registers" / "decision-log" / "DEC-0001.json").read_bytes()
    views = (memory / "views" / "decision-log.md").read_bytes()
    capsys.readouterr()

    bad = answer("update", "DEC-0009")
    assert process(FakeBuild(order(LADDER), LADDER, bad, bad), clock, memory, "ART-0002") == 1
    out = capsys.readouterr().out
    assert (
        f"  Rejected the comparison after 2 attempts (prompt {COMPARATOR_RETRY}); the Ledger "
        "lists it. Errors of the last attempt:"
    ) in out
    assert "  - $.target_id: 'DEC-0009' was not one of the candidates" in out
    assert "  Compared with 1 active decision; candidates: DEC-0001 (0.08)" in out
    assert "Recorded 0 of 1 routed work order; 1 rejected; 0 not routed" in out
    assert "; rerank (search units 1)" in out
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
        "work_order": 1,
    }
    assert rejected["rejected"] == [first]
    assert states(memory, "ART-0002") == ["rejected"]

    # The rerun drafts the saved work order again; the Governor is not called.
    build = FakeBuild(LADDER, answer("new"), run_id=OTHER_RUN_ID)
    assert process(build, clock, memory, "ART-0002") == 0
    out = capsys.readouterr().out.splitlines()
    assert out[:3] == [
        "Rerunning ART-0002: its earlier run recorded nothing.",
        f"Run ID: {OTHER_RUN_ID}",
        f"Using 1 saved work order from run {RUN_ID}; the Governor was not called.",
    ]
    assert "governor" not in build.agents
    rerun = entry(memory, "ART-0002")
    assert valid(memory, "ART-0002")
    assert rerun["rejected"] == [first]
    assert rerun["produced"][0]["record_id"] == "DEC-0002"
    assert statuses(memory, "ART-0002")[-2:] == ["processed", "processed"]
    assert rerun["history"][-1]["reason"] == "Rerun: the earlier run recorded nothing"
    assert rerun["history"][-1]["run_id"] == OTHER_RUN_ID
    assert rerun["governor"]["run_id"] == RUN_ID
    # A recorded order keeps the rejection that came before it.
    (saved,) = work_orders(memory, "ART-0002")["orders"]
    assert saved["state"] == "recorded" and len(saved["rejected"]) == 1


def test_rejected_drafts_accumulate_and_survive_a_failed_rerun(memory, clock, capsys):
    bad_draft = FLUTTER | {"evidence": ["We chose React Native."]}
    build = FakeBuild(order(FLUTTER), bad_draft, bad_draft)
    assert process(build, clock, memory, "ART-0001") == 1
    first = entry(memory, "ART-0001")["rejected"]
    assert [(item["stage"], item["run_id"]) for item in first] == [("draft", RUN_ID)]

    error = LLMRateLimitError("slow down")
    assert process(FakeBuild(error, run_id=OTHER_RUN_ID), clock, memory, "ART-0001") == 3
    failed = entry(memory, "ART-0001")
    assert failed["status"] == "failed" and failed["rejected"] == first
    assert failed["history"][-1]["reason"] == "Rerun: the earlier run recorded nothing"
    assert valid(memory, "ART-0001")

    # The same rejection again, with the same run ID: the Ledger lists it twice.
    assert process(FakeBuild(bad_draft, bad_draft), clock, memory, "ART-0001") == 1
    assert process(FakeBuild(FLUTTER, run_id=OTHER_RUN_ID), clock, memory, "ART-0001") == 0
    done = entry(memory, "ART-0001")
    assert valid(memory, "ART-0001")
    assert [item["stage"] for item in done["rejected"]] == ["draft", "draft"]
    assert done["rejected"][0] == first[0] == done["rejected"][1]
    assert done["produced"][0]["record_id"] == "DEC-0001"
    assert statuses(memory, "ART-0001") == [
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
    assert all(step["by"] == "governor" for step in done["history"][2:])


def test_an_artifact_that_produced_a_record_is_not_rerun(memory, clock, capsys):
    record_first_two(memory, clock)
    capsys.readouterr()
    build = FakeBuild(order(LADDER), LADDER)
    assert process(build, clock, memory, "ART-0002") == 2
    assert "ART-0002 is already processed (recorded in DEC-0002)" in capsys.readouterr().err
    assert build.settings == []


def test_an_interrupted_supersession_stops_process_and_views(memory, clock, monkeypatch, capsys):
    record_first_two(memory, clock)

    def interrupted(self, old, new, spec):
        raise OSError(28, "No space left on device", "DEC-0001.json")

    with monkeypatch.context() as patch:
        patch.setattr(RecordStore, "save_revision", interrupted)
        build = FakeBuild(order(NATIVE), NATIVE, answer("supersession", "DEC-0001"))
        assert process(build, clock, memory, "ART-0005") == 2
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
        build = FakeBuild(order(FLUTTER_AGAIN), FLUTTER_AGAIN)
        assert process(build, clock, memory, artifact_id) == 2
        err = capsys.readouterr().err
        assert expected in err and "nothing was sent to the model" in err
        assert build.settings == []

    for extra in ([], ["--check"]):
        assert run(FakeBuild(), clock, "views", "--memory", str(memory), *extra) == 2
        err = capsys.readouterr().err
        assert expected in err and "No view was written or checked." in err


def rewrite(memory, record_id, change):
    path = memory / "registers" / "decision-log" / f"{record_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def test_a_supersession_the_old_record_would_refuse_writes_nothing(memory, clock, capsys):
    record_first_two(memory, clock)

    def from_the_future(data):
        later = "2027-01-01T00:00:00Z"
        data["created_at"] = data["updated_at"] = later
        for item in data["sources"] + data["history"]:
            item["added_at" if "added_at" in item else "at"] = later

    path = rewrite(memory, "DEC-0001", from_the_future)
    before_record, before_entry = path.read_bytes(), entry(memory, "ART-0005")
    capsys.readouterr()

    build = FakeBuild(order(NATIVE), NATIVE, answer("supersession", "DEC-0001"))
    assert process(build, clock, memory, "ART-0005") == 2
    err = capsys.readouterr().err
    assert "DEC-0001 cannot be marked superseded, so nothing was written" in err
    assert "$.updated_at: earlier than the previous revision" in err
    assert list(records(memory)) == ["DEC-0001", "DEC-0002"]
    assert path.read_bytes() == before_record
    assert entry(memory, "ART-0005") == before_entry
    assert states(memory, "ART-0005") == ["pending"]
    assert pipeline.supersession_link_problems(memory) == []


def test_an_active_record_with_a_replacement_stops_process_and_views(memory, clock, capsys):
    record_first_two(memory, clock)
    build = FakeBuild(order(NATIVE), NATIVE, answer("supersession", "DEC-0001"))
    assert process(build, clock, memory, "ART-0005") == 0
    rewrite(memory, "DEC-0001", lambda data: data.update(record_status="active"))
    capsys.readouterr()

    expected = (
        "DEC-0001 names DEC-0003 in relations.superseded_by but is still active: set "
        "DEC-0001's record_status to superseded"
    )
    build = FakeBuild(order(FLUTTER_AGAIN), FLUTTER_AGAIN)
    assert process(build, clock, memory, "ART-0003") == 2
    err = capsys.readouterr().err
    assert expected in err and "nothing was sent to the model" in err
    assert "The decision log has an inconsistent supersession link" in err
    assert build.settings == []
    for extra in ([], ["--check"]):
        assert run(FakeBuild(), clock, "views", "--memory", str(memory), *extra) == 2
        err = capsys.readouterr().err
        assert expected in err and "No view was written or checked." in err
        assert "The decision log has an inconsistent supersession link:" in err


@pytest.mark.parametrize("stage", ["embed", "chat"])
def test_a_provider_error_during_the_comparison_marks_the_artifact_failed(
    memory, clock, capsys, stage
):
    assert process(FakeBuild(order(FLUTTER), FLUTTER), clock, memory, "ART-0001") == 0
    before = (memory / "registers" / "decision-log" / "DEC-0001.json").read_bytes()
    error = LLMRateLimitError("slow down")
    if stage == "embed":
        build = FakeBuild(order(FLUTTER_AGAIN), FLUTTER_AGAIN, embed_error=error)
    else:
        build = FakeBuild(order(FLUTTER_AGAIN), FLUTTER_AGAIN, error)
    assert process(build, clock, memory, "ART-0003") == 3
    assert "ART-0003 is now failed in the Ledger" in capsys.readouterr().err
    failed = entry(memory, "ART-0003")
    assert failed["status"] == "failed"
    assert failed["history"][-1]["error_type"] == "LLMRateLimitError"
    assert (memory / "registers" / "decision-log" / "DEC-0001.json").read_bytes() == before
    assert list(records(memory)) == ["DEC-0001"]
    assert states(memory, "ART-0003") == ["pending"]
    assert valid(memory, "ART-0003")


class BilledRerank(ScoredLLM):
    def __init__(self, responses, usage):
        super().__init__(responses)
        self.rerank_usage = usage

    def rerank(self, query, documents, *, top_n, context):
        result = super().rerank(query, documents, top_n=top_n, context=context)
        return dataclasses.replace(result, usage=self.rerank_usage)


@pytest.mark.parametrize(
    ("usage", "expected"),
    [
        (Usage(input_tokens=162), "; rerank (input tokens 162)"),
        (Usage(input_tokens=162, search_units=1), "; rerank (input tokens 162, search units 1)"),
        (Usage(search_units=1), "; rerank (search units 1)"),
        (Usage(), "; rerank (not reported)"),
    ],
)
def test_the_billing_line_shows_the_units_rerank_reports(memory, clock, capsys, usage, expected):
    assert process(FakeBuild(order(FLUTTER), FLUTTER), clock, memory, "ART-0001") == 0
    capsys.readouterr()
    build = FakeBuild()
    build.fake = BilledRerank([order(LADDER), LADDER, answer("new", reason="Another.")], usage)
    assert process(build, clock, memory, "ART-0002") == 0
    billed = next(
        line for line in capsys.readouterr().out.splitlines() if line.startswith("Billed")
    )
    assert billed.endswith(expected)


def test_the_billing_line_adds_up_every_work_order(memory, clock, capsys):
    record_first_two(memory, clock)
    capsys.readouterr()
    build = FakeBuild()
    another = answer("new", reason="Another topic.")
    build.fake = BilledRerank(
        [MIXED, REPORTS, another, STALL, another], Usage(input_tokens=100, search_units=1)
    )
    assert process(build, clock, memory, "ART-0006") == 0
    billed = next(
        line for line in capsys.readouterr().out.splitlines() if line.startswith("Billed")
    )
    events = build.sink.events
    assert [(event["agent"], event["operation"]) for event in events] == [
        ("governor", "chat"),
        *[
            ("decision-registrar", "chat"),
            ("comparator", "embed"),
            ("comparator", "embed"),
            ("comparator", "rerank"),
            ("comparator", "chat"),
        ]
        * 2,
    ]

    def total(agent, operation, unit):
        values = [
            event[unit]
            for event in events
            if (event["agent"], event["operation"]) == (agent, operation)
        ]
        assert values and all(value > 0 for value in values)
        return f"{sum(values):,}"

    def chat(agent):
        return (
            f"input tokens {total(agent, 'chat', 'input_tokens')}, "
            f"output tokens {total(agent, 'chat', 'output_tokens')}"
        )

    assert billed == (
        f"Billed: governor ({chat('governor')}); drafts ({chat('decision-registrar')}); "
        f"comparisons ({chat('comparator')}); "
        f"embed (input tokens {total('comparator', 'embed', 'input_tokens')}); "
        "rerank (input tokens 200, search units 2)"
    )


def test_a_reason_cp1252_cannot_encode_prints_as_utf8(memory, clock, monkeypatch):
    assert process(FakeBuild(order(FLUTTER), FLUTTER), clock, memory, "ART-0001") == 0
    out = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    err = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    reason = "A non\u2011breaking hyphen and \u2192 an arrow."
    build = FakeBuild(order(LADDER), LADDER, answer("new", reason=reason))
    assert process(build, clock, memory, "ART-0002") == 0
    out.flush()
    printed = out.buffer.getvalue().decode("utf-8")
    assert f"(prompt decision-comparator.v2): {reason}" in printed
    assert "Recorded DEC-0002 as a new decision" in printed
    assert out.encoding == err.encoding == "utf-8"


class MixedDimensions(ScoredLLM):
    def embed(self, texts, *, input_type, context):
        result = super().embed(texts, input_type=input_type, context=context)
        if input_type == "document":
            return result
        return dataclasses.replace(result, vectors=[[*vector, 0.0] for vector in result.vectors])


def test_embed_vectors_of_different_lengths_mark_the_artifact_failed(memory, clock, capsys):
    assert process(FakeBuild(order(FLUTTER), FLUTTER), clock, memory, "ART-0001") == 0
    before = (memory / "registers" / "decision-log" / "DEC-0001.json").read_bytes()
    build = FakeBuild()
    build.fake = MixedDimensions([order(FLUTTER_AGAIN), FLUTTER_AGAIN])
    assert process(build, clock, memory, "ART-0003") == 3
    assert "ART-0003 is now failed in the Ledger" in capsys.readouterr().err
    failed = entry(memory, "ART-0003")
    assert failed["status"] == "failed"
    assert failed["history"][-1]["error_type"] == "LLMResponseError"
    assert (memory / "registers" / "decision-log" / "DEC-0001.json").read_bytes() == before
    assert [call.operation for call in build.fake.calls] == ["chat", "chat", "embed", "embed"]


@pytest.mark.parametrize(
    ("env", "fragment"),
    [
        ({"KA_COMPARATOR_TOP_K": "0"}, "KA_COMPARATOR_TOP_K must be a whole number"),
        ({"KA_COMPARATOR_TOP_N": "many"}, "KA_COMPARATOR_TOP_N must be a whole number"),
        (
            {"KA_COMPARATOR_TOP_K": "2"},
            "KA_COMPARATOR_TOP_N (3) cannot be greater than KA_COMPARATOR_TOP_K (2)",
        ),
        ({"KA_GOVERNOR_MAX_ITEMS": "none"}, "KA_GOVERNOR_MAX_ITEMS must be a whole number"),
    ],
)
def test_bad_settings_exit_2_with_no_call(memory, clock, monkeypatch, capsys, env, fragment):
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    build = FakeBuild(order(FLUTTER), FLUTTER)
    assert process(build, clock, memory, "ART-0001") == 2
    assert fragment in capsys.readouterr().err
    assert build.settings == []
    assert entry(memory, "ART-0001")["status"] == "accepted"


def test_comparator_settings_reach_retrieval(memory, clock, monkeypatch, capsys):
    record_first_two(memory, clock)
    monkeypatch.setenv("KA_COMPARATOR_TOP_K", "1")
    monkeypatch.setenv("KA_COMPARATOR_TOP_N", "1")
    build = FakeBuild(order(FLUTTER_AGAIN), FLUTTER_AGAIN, answer("new"))
    assert process(build, clock, memory, "ART-0003") == 0
    rerank = next(call for call in build.fake.calls if call.operation == "rerank")
    assert len(rerank.inputs["documents"]) == 1 and rerank.inputs["top_n"] == 1
    user = build.fake.calls[-1].inputs["user"]
    shown = json.loads(user.removeprefix("<comparison>\n").removesuffix("\n</comparison>"))
    assert len(shown["existing_records"]) == 1
    assert "candidates: DEC-000" in capsys.readouterr().out


# Several work orders in one artifact (ART-0006)


def test_two_decisions_and_a_risk_record_both_decisions_and_list_the_risk(memory, clock, capsys):
    build = FakeBuild(MIXED, REPORTS, STALL, answer("new", reason="Another topic."))
    assert process(build, clock, memory, "ART-0006") == 0
    out = capsys.readouterr().out.splitlines()
    assert out[1:13] == [
        f"Found 3 work orders in ART-0006 {FOUND}: 2 decision-log, 1 risk-register "
        "(no Registrar yet, not routed)",
        f'Work order 1 of 3, decision-log: "{REPORTS_QUOTE}"',
        "  Drafted in 1 attempt (prompt decision-registrar.v3)",
        "  No active decisions to compare with: recorded as new without a comparison",
        "  Recorded DEC-0001 as a new decision",
        f'Work order 2 of 3, decision-log: "{STALL_QUOTE}"',
        "  Drafted in 1 attempt (prompt decision-registrar.v3)",
        "  Compared with 1 active decision; candidates: DEC-0001 (0.01)",
        "  Classified as new in 1 attempt (prompt decision-comparator.v2): Another topic.",
        "  Recorded DEC-0002 as a new decision",
        "Work order 3 of 3, risk-register: not routed (no Registrar yet)",
        "Recorded 2 of 2 routed work orders; 0 rejected; 1 not routed",
    ]
    # Each draft call carries its own work order.
    drafts = [call for call in build.fake.calls if "<work-order>" in call.inputs.get("user", "")]
    assert [REPORTS_QUOTE in call.inputs["user"].split("<work-order>")[1] for call in drafts] == [
        True,
        False,
    ]

    done = entry(memory, "ART-0006")
    assert valid(memory, "ART-0006")
    assert done["status"] == "processed"
    assert listed(done["produced"]) == [("DEC-0001", 1), ("DEC-0002", 2)]
    assert done["governor"]["work_orders"] == [
        {"register": "decision-log", "count": 2, "routed": True},
        {"register": "risk-register", "count": 1, "routed": False},
    ]
    assert states(memory, "ART-0006") == ["recorded", "recorded", "not-routed"]
    assert [item["artifact_id"] for item in records(memory)["DEC-0002"]["sources"]] == ["ART-0006"]

    assert run(FakeBuild(), clock, "ledger", "--memory", str(memory)) == 0
    line = capsys.readouterr().out.splitlines()[5]
    assert line.endswith("(new DEC-0001)  (new DEC-0002)  (1 risk-register not routed)")

    assert process(FakeBuild(), clock, memory, "ART-0006") == 2
    assert "ART-0006 is already processed (recorded in DEC-0001, DEC-0002)" in (
        capsys.readouterr().err
    )


def test_a_provider_error_on_the_second_order_keeps_the_first_and_the_rerun_drafts_only_it(
    memory, clock, capsys
):
    build = FakeBuild(MIXED, REPORTS, LLMRateLimitError("slow down"))
    assert process(build, clock, memory, "ART-0006") == 3
    out, err = capsys.readouterr()
    assert f"Run ID: {RUN_ID}" in out
    assert (
        "ART-0006 is now failed in the Ledger, with the results so far; run it again to continue."
    ) in err
    failed = entry(memory, "ART-0006")
    assert valid(memory, "ART-0006")
    assert failed["status"] == "failed"
    assert failed["history"][-1]["error_type"] == "LLMRateLimitError"
    assert listed(failed["produced"]) == [("DEC-0001", 1)]
    assert failed["governor"]["run_id"] == RUN_ID
    assert states(memory, "ART-0006") == ["recorded", "pending", "not-routed"]

    build = FakeBuild(STALL, answer("new"), run_id=OTHER_RUN_ID)
    assert process(build, clock, memory, "ART-0006") == 0
    out = capsys.readouterr().out.splitlines()
    assert out[:5] == [
        f"Run ID: {OTHER_RUN_ID}",
        f"Using 3 saved work orders from run {RUN_ID}; the Governor was not called.",
        f'Work order 1 of 3, decision-log: "{REPORTS_QUOTE}"',
        "  Recorded by an earlier run: new DEC-0001",
        f'Work order 2 of 3, decision-log: "{STALL_QUOTE}"',
    ]
    assert build.agents == ["decision-registrar"] + ["comparator"] * 4
    assert next(line for line in out if line.startswith("Billed")).startswith(
        "Billed: drafts (input tokens "
    )
    done = entry(memory, "ART-0006")
    assert valid(memory, "ART-0006")
    assert listed(done["produced"]) == [("DEC-0001", 1), ("DEC-0002", 2)]
    assert statuses(memory, "ART-0006") == ["received", "accepted", "failed", "processed"]


def test_rejected_then_recorded_then_failed_and_the_rerun_records_orders_1_and_3(
    memory, clock, capsys
):
    three = decisions(REPORTS_QUOTE, STALL_QUOTE, KEEP_QUOTE)
    build = FakeBuild(three, BAD, BAD, STALL, LLMRateLimitError("slow down"))
    assert process(build, clock, memory, "ART-0006") == 3
    failed = entry(memory, "ART-0006")
    assert valid(memory, "ART-0006")
    assert failed["status"] == "failed"
    assert listed(failed["produced"]) == [("DEC-0001", 2)]
    assert listed(failed["rejected"]) == [("draft", 1)]
    assert states(memory, "ART-0006") == ["rejected", "recorded", "pending"]

    build = FakeBuild(REPORTS, answer("new"), KEEP, answer("new"), run_id=OTHER_RUN_ID)
    assert process(build, clock, memory, "ART-0006") == 0
    out = capsys.readouterr().out
    assert "Work order 2 of 3, decision-log" in out
    assert "  Recorded by an earlier run: new DEC-0001" in out
    assert "Recorded 3 of 3 routed work orders; 0 rejected; 0 not routed" in out
    done = entry(memory, "ART-0006")
    assert valid(memory, "ART-0006")
    # Existing items stay first and in place; new ones follow in order number.
    assert listed(done["produced"]) == [("DEC-0001", 2), ("DEC-0002", 1), ("DEC-0003", 3)]
    assert done["produced"][0] == failed["produced"][0]
    assert done["rejected"] == failed["rejected"]
    assert statuses(memory, "ART-0006") == ["received", "accepted", "failed", "processed"]
    first = work_orders(memory, "ART-0006")["orders"][0]
    assert first["state"] == "recorded" and len(first["rejected"]) == 1


def test_order_1_rejected_and_order_2_failing_then_the_rerun_retries_both(memory, clock, capsys):
    build = FakeBuild(MIXED, BAD, BAD, LLMRateLimitError("slow down"))
    assert process(build, clock, memory, "ART-0006") == 3
    failed = entry(memory, "ART-0006")
    assert valid(memory, "ART-0006")
    assert failed["status"] == "failed" and failed["produced"] == []
    assert listed(failed["rejected"]) == [("draft", 1)]

    build = FakeBuild(REPORTS, STALL, answer("new"), run_id=OTHER_RUN_ID)
    assert process(build, clock, memory, "ART-0006") == 0
    done = entry(memory, "ART-0006")
    assert valid(memory, "ART-0006")
    assert listed(done["produced"]) == [("DEC-0001", 1), ("DEC-0002", 2)]
    assert done["rejected"] == failed["rejected"]
    assert states(memory, "ART-0006") == ["recorded", "recorded", "not-routed"]


def test_a_rejected_order_and_a_recorded_order_in_one_run_are_final(memory, clock, capsys):
    build = FakeBuild(MIXED, BAD, BAD, STALL)
    assert process(build, clock, memory, "ART-0006") == 1
    out = capsys.readouterr().out
    assert "Recorded 1 of 2 routed work orders; 1 rejected; 1 not routed" in out
    done = entry(memory, "ART-0006")
    assert valid(memory, "ART-0006")
    assert done["status"] == "processed"
    assert listed(done["produced"]) == [("DEC-0001", 2)]
    assert listed(done["rejected"]) == [("draft", 1)]

    build = FakeBuild()
    assert process(build, clock, memory, "ART-0006") == 2
    assert "ART-0006 is already processed (recorded in DEC-0001)" in capsys.readouterr().err
    assert build.settings == []


def test_a_run_interrupted_after_order_1_was_rejected_continues_with_order_2_only(
    memory, clock, monkeypatch, capsys
):
    with monkeypatch.context() as patch:
        patch.setattr(pipeline, "draft_record", failing_after(1, DISK_FULL)(pipeline.draft_record))
        assert process(FakeBuild(MIXED, BAD, BAD), clock, memory, "ART-0006") == 2
    assert entry(memory, "ART-0006")["status"] == "accepted"
    assert states(memory, "ART-0006") == ["rejected", "pending", "not-routed"]
    capsys.readouterr()

    build = FakeBuild(STALL, run_id=OTHER_RUN_ID)
    assert process(build, clock, memory, "ART-0006") == 1
    out = capsys.readouterr().out.splitlines()
    assert out[2:4] == [
        f'Work order 1 of 3, decision-log: "{REPORTS_QUOTE}"',
        "  Rejected by an earlier run, which was interrupted; the Ledger lists it",
    ]
    assert "Recorded 1 of 2 routed work orders; 1 rejected; 1 not routed" in out
    assert build.agents == ["decision-registrar"]
    done = entry(memory, "ART-0006")
    assert valid(memory, "ART-0006")
    assert done["status"] == "processed"
    assert listed(done["produced"]) == [("DEC-0001", 2)]
    assert [(item["stage"], item["run_id"]) for item in done["rejected"]] == [("draft", RUN_ID)]


def test_a_crash_after_the_records_and_before_the_order_result_is_caught_before_any_call(
    memory, clock, monkeypatch, capsys
):
    with monkeypatch.context() as patch:
        save = failing_after(0, DISK_FULL)(WorkOrderStore.save_progress)
        patch.setattr(WorkOrderStore, "save_progress", save)
        assert process(FakeBuild(MIXED, REPORTS), clock, memory, "ART-0006") == 2
    assert "No space left on device" in capsys.readouterr().err
    assert list(records(memory)) == ["DEC-0001"]
    assert (memory / "views" / "decision-log" / "DEC-0001.md").is_file()
    assert states(memory, "ART-0006") == ["pending", "pending", "not-routed"]
    assert entry(memory, "ART-0006")["status"] == "accepted"

    build = FakeBuild()
    assert process(build, clock, memory, "ART-0006") == 2
    err = capsys.readouterr().err
    assert "The work orders file of ART-0006 is behind the records" in err
    assert "nothing was sent to the model" in err and "DEC-0001" in err
    assert build.settings == []


def test_an_interrupted_reaffirmation_of_a_record_an_earlier_order_wrote_is_caught(
    memory, clock, monkeypatch, capsys
):
    split = decisions(KEEP_QUOTE, AGAIN_QUOTE)
    with monkeypatch.context() as patch:
        save = failing_after(1, DISK_FULL)(WorkOrderStore.save_progress)
        patch.setattr(WorkOrderStore, "save_progress", save)
        reaffirm = answer("reaffirmation", "DEC-0001")
        assert process(FakeBuild(split, KEEP, AGAIN, reaffirm), clock, memory, "ART-0006") == 2
    assert records(memory)["DEC-0001"]["revision"] == 2
    assert states(memory, "ART-0006") == ["recorded", "pending"]
    capsys.readouterr()

    build = FakeBuild()
    assert process(build, clock, memory, "ART-0006") == 2
    assert "The work orders file of ART-0006 is behind the records" in capsys.readouterr().err
    assert build.settings == []


def test_a_split_duplicate_becomes_a_reaffirmation_of_the_record_from_the_same_artifact(
    memory, clock, capsys
):
    split = decisions(KEEP_QUOTE, AGAIN_QUOTE)
    reaffirm = answer("reaffirmation", "DEC-0001", "Says it again.")
    assert process(FakeBuild(split, KEEP, AGAIN, reaffirm), clock, memory, "ART-0006") == 0
    out = capsys.readouterr().out
    assert "  Compared with 1 active decision; candidates: DEC-0001 (0.08)" in out
    assert "  Reaffirmed DEC-0001 (revision 2): added 1 source" in out
    done = entry(memory, "ART-0006")
    assert valid(memory, "ART-0006")
    assert [
        (item["change"], item["record_id"], item["work_order"]) for item in done["produced"]
    ] == [
        ("new", "DEC-0001", 1),
        ("reaffirmation", "DEC-0001", 2),
    ]
    stored = records(memory)
    assert list(stored) == ["DEC-0001"]
    assert [source["artifact_id"] for source in stored["DEC-0001"]["sources"]] == [
        "ART-0006",
        "ART-0006",
    ]


def test_a_ledger_left_behind_after_a_governor_rejection_is_rebuilt_with_no_call(
    memory, clock, monkeypatch, capsys
):
    unusable = LLMResponseError("truncated")
    assert process(FakeBuild(unusable, unusable), clock, memory, "ART-0006") == 1
    (governor_item,) = entry(memory, "ART-0006")["rejected"]

    def interrupted(self, old, new):
        raise DISK_FULL

    with monkeypatch.context() as patch:
        patch.setattr(LedgerStore, "save_transition", interrupted)
        build = FakeBuild(MIXED, REPORTS, STALL, answer("new"), run_id=OTHER_RUN_ID)
        assert process(build, clock, memory, "ART-0006") == 2
    assert states(memory, "ART-0006") == ["recorded", "recorded", "not-routed"]
    assert entry(memory, "ART-0006")["produced"] == []
    capsys.readouterr()

    build = FakeBuild()
    assert process(build, clock, memory, "ART-0006") == 0
    out = capsys.readouterr().out.splitlines()
    assert build.settings == []
    assert out == [
        f"Run ID: {out[0].removeprefix('Run ID: ')}",
        f"Rebuilt the Ledger entry of ART-0006 from its work orders file (run {OTHER_RUN_ID}); "
        "no call was made.",
        "Recorded 2 of 2 routed work orders; 0 rejected; 1 not routed",
    ]
    done = entry(memory, "ART-0006")
    assert valid(memory, "ART-0006")
    assert done["rejected"] == [governor_item]
    assert listed(done["produced"]) == [("DEC-0001", 1), ("DEC-0002", 2)]
    assert done["governor"]["run_id"] == OTHER_RUN_ID
    assert statuses(memory, "ART-0006") == ["received", "accepted", "processed", "processed"]
    assert done["history"][-1]["reason"] == "Rebuilt from the work orders file"
    assert done["history"][-1]["by"] == "governor"


def test_a_rebuilt_ledger_with_a_rejected_order_exits_1(memory, clock, monkeypatch, capsys):
    def interrupted(self, old, new):
        raise DISK_FULL

    with monkeypatch.context() as patch:
        patch.setattr(LedgerStore, "save_transition", interrupted)
        assert process(FakeBuild(MIXED, BAD, BAD, STALL), clock, memory, "ART-0006") == 2
    assert states(memory, "ART-0006") == ["rejected", "recorded", "not-routed"]
    assert entry(memory, "ART-0006")["status"] == "accepted"
    capsys.readouterr()

    build = FakeBuild()
    assert process(build, clock, memory, "ART-0006") == 1
    out = capsys.readouterr().out.splitlines()
    assert build.settings == []
    assert out[1:] == [
        f"Rebuilt the Ledger entry of ART-0006 from its work orders file (run {RUN_ID}); "
        "no call was made.",
        "Recorded 1 of 2 routed work orders; 1 rejected; 1 not routed",
    ]
    done = entry(memory, "ART-0006")
    assert valid(memory, "ART-0006")
    assert done["status"] == "processed"
    assert listed(done["produced"]) == [("DEC-0001", 2)]
    assert listed(done["rejected"]) == [("draft", 1)]


MISSING_FILE = "is missing; nothing was sent to the model. Restore the file."


def test_a_missing_work_orders_file_after_every_order_was_rejected_is_refused(
    memory, clock, capsys
):
    assert process(FakeBuild(order(FLUTTER), BAD, BAD), clock, memory, "ART-0001") == 1
    rejected = entry(memory, "ART-0001")
    assert rejected["status"] == "processed" and rejected["produced"] == []
    assert listed(rejected["rejected"]) == [("draft", 1)]
    WorkOrderStore(memory).path("ART-0001").unlink()  # deleted by hand
    capsys.readouterr()

    build = FakeBuild(order(FLUTTER), FLUTTER)
    assert process(build, clock, memory, "ART-0001") == 2
    err = capsys.readouterr().err
    assert "The Ledger entry of ART-0001 lists results of a Governor run, but its work" in err
    assert MISSING_FILE in err
    assert build.settings == []
    assert entry(memory, "ART-0001") == rejected
    assert not (memory / "registers").exists()


# Held for the Operator


def test_more_orders_than_the_limit_hold_the_artifact_with_no_draft(
    memory, clock, monkeypatch, capsys
):
    monkeypatch.setenv("KA_GOVERNOR_MAX_ITEMS", "1")
    build = FakeBuild(MIXED)
    assert process(build, clock, memory, "ART-0006") == 1
    out, err = capsys.readouterr()
    assert out.splitlines()[1].startswith("Found 3 work orders in ART-0006")
    assert out.splitlines()[2].startswith("Billed: governor (input tokens ")
    assert (
        "The Governor found 2 work orders for registers with a Registrar, more than "
        "KA_GOVERNOR_MAX_ITEMS (1); nothing was drafted. Review the artifact, then release it."
    ) in err
    assert "release it with `knowledge-automata release ART-0006 --reason TEXT`" in err
    assert build.agents == ["governor"]
    assert not (memory / "registers").exists()

    held = entry(memory, "ART-0006")
    assert valid(memory, "ART-0006")
    assert held["status"] == "held"
    assert (held["history"][-1]["by"], held["history"][-1]["run_id"]) == ("governor", RUN_ID)
    assert held["governor"]["run_id"] == RUN_ID
    file = work_orders(memory, "ART-0006")
    assert file["max_items"] == 1
    assert states(memory, "ART-0006") == ["pending", "pending", "not-routed"]

    build = FakeBuild()
    assert process(build, clock, memory, "ART-0006") == 2
    err = capsys.readouterr().err
    assert "ART-0006 is held (The Governor found 2 work orders" in err
    assert "release ART-0006" in err
    assert build.settings == []


def test_a_saved_file_over_its_limit_is_held_again_with_no_call(memory, clock, monkeypatch, capsys):
    def interrupted(self, old, new):
        raise DISK_FULL

    monkeypatch.setenv("KA_GOVERNOR_MAX_ITEMS", "1")
    with monkeypatch.context() as patch:
        patch.setattr(LedgerStore, "save_transition", interrupted)
        assert process(FakeBuild(MIXED), clock, memory, "ART-0006") == 2
    assert entry(memory, "ART-0006")["status"] == "accepted"
    capsys.readouterr()

    # Judged by the file's max_items, not the current setting.
    monkeypatch.setenv("KA_GOVERNOR_MAX_ITEMS", "50")
    build = FakeBuild()
    assert process(build, clock, memory, "ART-0006") == 1
    out, err = capsys.readouterr()
    assert build.settings == []
    assert out.splitlines() == [
        f"Run ID: {RUN_ID}",
        f"Using 3 saved work orders from run {RUN_ID}; the Governor was not called.",
    ]
    assert "more than KA_GOVERNOR_MAX_ITEMS (1)" in err
    held = entry(memory, "ART-0006")
    assert valid(memory, "ART-0006")
    assert held["status"] == "held" and held["history"][-1]["run_id"] == RUN_ID


def release(clock, memory, artifact_id, reason="Reviewed by Miguel: two real decisions"):
    return run(
        FakeBuild(), clock, "release", artifact_id, "--reason", reason, "--memory", str(memory)
    )


def test_a_released_artifact_runs_every_saved_order_with_no_governor_call(
    memory, clock, monkeypatch, capsys
):
    monkeypatch.setenv("KA_GOVERNOR_MAX_ITEMS", "1")
    assert process(FakeBuild(MIXED), clock, memory, "ART-0006") == 1
    capsys.readouterr()

    def no_read(*args):
        raise AssertionError("a held artifact is released without reading its copy")

    with monkeypatch.context() as patch:
        patch.setattr(pipeline.artifact_files, "read_copy", no_read)
        assert release(clock, memory, "ART-0006") == 0
    assert capsys.readouterr().out == (
        "Released ART-0006: it is now accepted; process ART-0006 runs its saved work orders\n"
    )
    released = entry(memory, "ART-0006")
    assert valid(memory, "ART-0006")
    assert released["status"] == "accepted"
    assert released["history"][-1] == {
        "at": released["history"][-1]["at"],
        "status": "accepted",
        "by": "operator",
        "reason": "Reviewed by Miguel: two real decisions",
    }
    assert released["governor"]["run_id"] == RUN_ID

    # The limit is still 1: the release covers this file, so every order runs.
    build = FakeBuild(REPORTS, STALL, answer("new", reason="Another topic."))
    assert process(build, clock, memory, "ART-0006") == 0
    out = capsys.readouterr().out.splitlines()
    assert out[1] == f"Using 3 saved work orders from run {RUN_ID}; the Governor was not called."
    assert "governor" not in build.agents
    assert states(memory, "ART-0006") == ["recorded", "recorded", "not-routed"]
    done = entry(memory, "ART-0006")
    assert valid(memory, "ART-0006")
    assert done["status"] == "processed"
    assert listed(done["produced"]) == [("DEC-0001", 1), ("DEC-0002", 2)]
    assert statuses(memory, "ART-0006") == [
        "received",
        "accepted",
        "held",
        "accepted",
        "processed",
    ]


def test_a_work_orders_file_deleted_after_a_release_is_refused(memory, clock, monkeypatch, capsys):
    # The Governor is not called again: a new file would get a new run ID, which the
    # release does not cover (test_work_order_file.py), and could record items twice.
    monkeypatch.setenv("KA_GOVERNOR_MAX_ITEMS", "1")
    assert process(FakeBuild(MIXED), clock, memory, "ART-0006") == 1
    assert release(clock, memory, "ART-0006") == 0
    released = entry(memory, "ART-0006")
    WorkOrderStore(memory).path("ART-0006").unlink()  # deleted by hand
    capsys.readouterr()

    build = FakeBuild(MIXED, run_id=OTHER_RUN_ID)
    assert process(build, clock, memory, "ART-0006") == 2
    err = capsys.readouterr().err
    assert "The Ledger entry of ART-0006 lists results of a Governor run, but its work" in err
    assert MISSING_FILE in err
    assert build.settings == []
    assert entry(memory, "ART-0006") == released
    assert not (memory / "registers").exists()


def test_releasing_an_artifact_that_is_not_held_or_quarantined_is_refused(memory, clock, capsys):
    assert release(clock, memory, "ART-0006") == 2
    assert (
        "ART-0006 is accepted; only a quarantined or held artifact can be released"
        in capsys.readouterr().err
    )
    assert statuses(memory, "ART-0006") == ["received", "accepted"]


def test_a_governor_rejection_survives_a_hold_a_release_and_the_run_after_it(
    memory, clock, monkeypatch, capsys
):
    unusable = LLMResponseError("truncated")
    assert process(FakeBuild(unusable, unusable), clock, memory, "ART-0006") == 1
    (governor_item,) = entry(memory, "ART-0006")["rejected"]
    assert governor_item["stage"] == "governor"

    monkeypatch.setenv("KA_GOVERNOR_MAX_ITEMS", "1")
    assert process(FakeBuild(MIXED, run_id=OTHER_RUN_ID), clock, memory, "ART-0006") == 1
    held = entry(memory, "ART-0006")
    assert valid(memory, "ART-0006")
    assert held["status"] == "held"
    assert held["rejected"] == [governor_item]
    assert held["history"][-1]["run_id"] == OTHER_RUN_ID

    assert release(clock, memory, "ART-0006") == 0
    released = entry(memory, "ART-0006")
    assert valid(memory, "ART-0006")
    assert released["rejected"] == [governor_item]

    build = FakeBuild(REPORTS, STALL, answer("new", reason="Another topic."))
    assert process(build, clock, memory, "ART-0006") == 0
    assert "governor" not in build.agents
    done = entry(memory, "ART-0006")
    assert valid(memory, "ART-0006")
    assert done["status"] == "processed"
    assert done["rejected"] == [governor_item]
    assert listed(done["produced"]) == [("DEC-0001", 1), ("DEC-0002", 2)]
    assert statuses(memory, "ART-0006") == [
        "received",
        "accepted",
        "processed",
        "held",
        "accepted",
        "processed",
    ]


# Output hygiene


HIRE_QUOTE = "We hire a second grower in June."
SHOP_QUOTE = "We open the farm shop on Sundays."
CRATES_QUOTE = "We buy reusable crates for the market."
FRESH = [
    ("board-2026-05-12.md", "2026-05-12", f"# Board, 12 May\n{HIRE_QUOTE}\n{SHOP_QUOTE}\n"),
    ("board-2026-05-26.md", "2026-05-26", f"# Board, 26 May\n{CRATES_QUOTE}\n"),
]
# The only place a label may appear: a work order's heading.
HEADING = re.compile(r'^Work order \d+ of \d+, [a-z-]+: "(?P<label>.*)"$')


def ingest(memory, clock, name, date, text):
    path = memory.parent / "inbox" / name
    path.write_bytes((text + SENTINEL + "\n").encode("utf-8"))
    args = ["ingest", str(path), "--artifact-date", date, "--memory", str(memory)]
    assert run(FakeBuild(), clock, *args) == 0


def without_labels(text, labels):
    """``text`` with each label removed from its heading line, and only there."""
    lines = []
    for line in text.splitlines():
        match = HEADING.match(line)
        if match is not None and match["label"] in labels:
            line = line[: match.start("label")] + line[match.end("label") :]
        lines.append(line)
    return "\n".join(lines)


def test_no_output_contains_artifact_text_other_than_titles_labels_and_reasons(
    memory, clock, monkeypatch, capsys
):
    record_first_two(memory, clock)
    for name, date, text in FRESH:
        ingest(memory, clock, name, date, text)
    bad = answer("update", "DEC-0009")
    reaffirm = answer("reaffirmation", "DEC-0001")
    build = FakeBuild(order(FLUTTER_AGAIN), FLUTTER_AGAIN, reaffirm)
    assert process(build, clock, memory, "ART-0003") == 0
    build = FakeBuild(order(LADDER_DETAIL), LADDER_DETAIL, bad, bad)
    assert process(build, clock, memory, "ART-0004") == 1
    build = FakeBuild(order(NATIVE), NATIVE, LLMRateLimitError("slow down"))
    assert process(build, clock, memory, "ART-0005") == 3
    build = FakeBuild(MIXED, BAD, BAD, STALL, answer("new"))
    assert process(build, clock, memory, "ART-0006") == 1
    # A fresh artifact over the limit is held.
    monkeypatch.setenv("KA_GOVERNOR_MAX_ITEMS", "1")
    assert process(FakeBuild(decisions(HIRE_QUOTE, SHOP_QUOTE)), clock, memory, "ART-0007") == 1
    assert entry(memory, "ART-0007")["status"] == "held"
    monkeypatch.delenv("KA_GOVERNOR_MAX_ITEMS")
    # Another fresh artifact: the Governor returns one item twice, so its reply is rejected.
    twice = decisions(CRATES_QUOTE, CRATES_QUOTE)
    assert process(FakeBuild(twice, twice), clock, memory, "ART-0008") == 1
    assert listed(entry(memory, "ART-0008")["rejected"]) == [("governor", None)]
    assert run(FakeBuild(), clock, "ledger", "--memory", str(memory)) == 0
    out, err = capsys.readouterr()

    labels = {
        item["label"]
        for number in range(1, 9)
        for item in (work_orders(memory, f"ART-{number:04d}") or {"orders": []})["orders"]
    }
    assert {HIRE_QUOTE, SHOP_QUOTE, REPORTS_QUOTE, STALL_QUOTE} <= labels
    assert f'Work order 1 of 3, decision-log: "{REPORTS_QUOTE}"' in out
    lines = [line for _, _, text in ARTIFACTS + FRESH for line in text.splitlines()[1:]]
    for text in (out, err):
        assert SENTINEL not in text
        text = without_labels(text, labels)
        for line in lines:
            assert line not in text
