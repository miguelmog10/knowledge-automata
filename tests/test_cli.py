import json
from datetime import UTC, datetime

import pytest

from knowledge_automata import cli, pipeline
from knowledge_automata.agents.registrar import Registrar
from knowledge_automata.core.prompts import Prompt
from knowledge_automata.core.validation import validate_record
from knowledge_automata.domains.project_management.registers import DECISION_LOG
from knowledge_automata.llm import (
    LLMAuthError,
    LLMRateLimitError,
    LLMResponseError,
    MemorySink,
    ObservedLLM,
)
from knowledge_automata.llm.fake import FakeLLM
from knowledge_automata.llm.settings import MISSING_KEY_HINT
from knowledge_automata.storage.ledger_store import LedgerStore

RUN_ID = "7d1c6a52-3b0e-4c47-9a57-0e6f2d1f9a10"
NOW = datetime(2026, 10, 26, 14, 3, 12, tzinfo=UTC)
ARTIFACT_SENTINEL = "SENTINEL-ARTIFACT-4b81 do not print this line"
PROMPT_SENTINEL = "SENTINEL-PROMPT-c27e"
RETRY_VERSION = "decision-registrar.v1+registrar-retry.v1"


class FakeBuild:
    """Stands in for build_llm: FakeLLM behind ObservedLLM, events in memory."""

    def __init__(self, *responses):
        self.fake = FakeLLM(responses)
        self.sink = MemorySink()
        self.settings = []

    def __call__(self, settings):
        self.settings.append(settings)
        return ObservedLLM(self.fake, provider="fake", sink=self.sink, run_id=RUN_ID)


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
def memory(tmp_path):
    return tmp_path / "memory"


@pytest.fixture
def inbox(tmp_path):
    folder = tmp_path / "inbox"
    folder.mkdir()
    return folder


@pytest.fixture
def artifact(inbox, artifact_text):
    path = inbox / "steering-group.md"
    path.write_text(artifact_text + "\n" + ARTIFACT_SENTINEL + "\n", encoding="utf-8")
    return path


@pytest.fixture
def ingested(artifact, memory, capsys):
    assert ingest(artifact, memory, "--artifact-date", "2026-03-12") == 0
    capsys.readouterr()
    return "ART-0001"


def bad(draft):
    return draft | {"evidence": ["The group chose supplier C."]}


def run(build, *args):
    return cli.main(list(args), build=build, clock=lambda: NOW)


def ingest(path, memory, *extra):
    return run(FakeBuild(), "ingest", str(path), "--memory", str(memory), *extra)


def record(build, memory, artifact_id="ART-0001"):
    return run(build, "record-decision", artifact_id, "--memory", str(memory))


def entry(memory, artifact_id="ART-0001"):
    return LedgerStore(memory).load(artifact_id)


def write(inbox, name, raw):
    path = inbox / name
    path.write_bytes(raw)
    return path


# ingest


def test_ingest_accepts_a_file_and_prints_one_line(artifact, memory, capsys):
    assert ingest(artifact, memory) == 0
    out, err = capsys.readouterr()
    size = artifact.stat().st_size
    assert out == f"Accepted ART-0001 (steering-group.md, {size:,} bytes)\n"
    assert err == ""
    copy = memory / "artifacts" / "ART-0001-steering-group.md"
    assert copy.read_bytes() == artifact.read_bytes()
    assert entry(memory)["status"] == "accepted"


def test_ingest_a_duplicate_writes_nothing(artifact, memory, capsys):
    lf = artifact.read_bytes().replace(b"\r\n", b"\n")
    artifact.write_bytes(lf)
    assert ingest(artifact, memory) == 0
    copy = write(artifact.parent, "copy.txt", lf.replace(b"\n", b"\r\n"))
    capsys.readouterr()
    assert ingest(copy, memory) == 0
    out = capsys.readouterr().out
    assert out == "Already in the Ledger as ART-0001 (accepted); nothing was written\n"
    assert [path.name for path in (memory / "ledger").iterdir()] == ["ART-0001.json"]


def test_ingest_names_an_earlier_file_with_the_same_name(inbox, memory, capsys):
    first = write(inbox, "notes.md", b"First version\n")
    assert ingest(first, memory) == 0
    first.write_bytes(b"Second version\n")
    capsys.readouterr()
    assert ingest(first, memory) == 0
    assert capsys.readouterr().out.splitlines() == [
        "Accepted ART-0002 (notes.md, 15 bytes)",
        "Same file name as ART-0001",
    ]


@pytest.mark.parametrize(
    ("name", "raw", "line"),
    [
        ("notes.pdf", b"%PDF", "Rejected ART-0001 (unsupported-format: Only .md"),
        ("empty.md", b"", "Rejected ART-0001 (empty: The file is empty)"),
        ("latin.txt", b"caf\xe9", "Quarantined ART-0001 (encoding: Not valid UTF-8 text"),
        ("tag.md", b"a </artifact> b", "Quarantined ART-0001 (delimiter: Contains"),
    ],
)
def test_ingest_exits_1_for_quarantined_and_rejected_files(inbox, memory, name, raw, line, capsys):
    assert ingest(write(inbox, name, raw), memory) == 1
    out = capsys.readouterr().out
    assert out.startswith(line) and len(out.splitlines()) == 1


def test_ingest_quarantines_an_oversized_file(inbox, memory, monkeypatch, capsys):
    monkeypatch.setenv("KA_SENSOR_MAX_BYTES", "10")
    assert ingest(write(inbox, "long.md", b"x" * 11), memory) == 1
    expected = "Quarantined ART-0001 (oversized: 11 bytes; the limit is 10 (KA_SENSOR_MAX_BYTES))\n"
    assert capsys.readouterr().out == expected


@pytest.mark.parametrize(
    ("args", "env", "fragment"),
    [
        (["--artifact-date", "2026-02-30"], None, "--artifact-date"),
        ([], "lots", "KA_SENSOR_MAX_BYTES must be a positive whole number"),
    ],
)
def test_ingest_usage_and_configuration_problems_exit_2(
    artifact, memory, monkeypatch, args, env, fragment, capsys
):
    if env is not None:
        monkeypatch.setenv("KA_SENSOR_MAX_BYTES", env)
    assert ingest(artifact, memory, *args) == 2
    assert fragment in capsys.readouterr().err
    assert not memory.exists()


def test_ingest_a_missing_file_exits_2(memory, capsys):
    assert ingest("nope.md", memory) == 2
    assert "Cannot read nope.md" in capsys.readouterr().err


# record-decision


def test_record_decision_stores_the_record_the_views_and_the_ledger(
    ingested, memory, decision_draft, capsys
):
    build = FakeBuild(decision_draft)
    assert record(build, memory) == 0

    out, err = capsys.readouterr()
    assert err == ""
    assert f"Run ID: {RUN_ID}" in out
    assert (
        "Drafted a decision from ART-0001 in 1 attempt "
        "(model fake-chat, prompt decision-registrar.v1, thinking disabled)"
    ) in out
    assert "No active decisions to compare with: recorded as new without a comparison." in out
    assert "Recorded DEC-0001 as a new decision" in out
    assert "Billed: draft (input tokens " in out
    assert "memory/registers/decision-log/DEC-0001.json" in out
    assert "memory/views/decision-log.md" in out

    path = memory / "registers" / "decision-log" / "DEC-0001.json"
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert validate_record(stored, DECISION_LOG).ok
    assert stored["content"] == decision_draft["content"]
    assert stored["created_at"] == "2026-10-26T14:03:12Z"
    assert stored["sources"][0]["artifact_date"] == "2026-03-12"
    assert stored["history"][0]["model"] == "fake-chat"

    page = (memory / "views" / "decision-log" / "DEC-0001.md").read_text(encoding="utf-8")
    assert "From [ART-0001](../../artifacts/ART-0001-steering-group.md), 2026-03-12." in page
    assert (memory / "views" / "decision-log.md").is_file()
    assert [event["artifact_id"] for event in build.sink.events] == ["ART-0001"]

    processed = entry(memory)
    assert processed["status"] == "processed"
    assert processed["history"][-1] == {
        "at": "2026-10-26T14:03:12Z",
        "status": "processed",
        "by": "pipeline",
        "run_id": RUN_ID,
    }
    assert processed["produced"] == [
        {
            "register": "decision-log",
            "record_id": "DEC-0001",
            "change": "new",
            "model": "fake-chat",
            "prompt_version": "decision-registrar.v1",
            "schema_version": stored["schema_version"],
        }
    ]
    assert processed["rejected"] == []


def test_retry_is_reported_with_its_prompt_version(ingested, memory, decision_draft, capsys):
    build = FakeBuild(bad(decision_draft), decision_draft)
    assert record(build, memory) == 0
    out = capsys.readouterr().out
    assert "in 2 attempts" in out
    assert f"prompt {RETRY_VERSION}" in out
    stored = json.loads(
        (memory / "registers" / "decision-log" / "DEC-0001.json").read_text(encoding="utf-8")
    )
    assert stored["history"][0]["prompt_version"] == RETRY_VERSION
    assert entry(memory)["produced"][0]["prompt_version"] == RETRY_VERSION


def test_a_second_run_on_a_processed_artifact_makes_no_call(
    ingested, memory, decision_draft, capsys
):
    assert record(FakeBuild(decision_draft), memory) == 0
    capsys.readouterr()
    second = FakeBuild(decision_draft)
    assert record(second, memory) == 2
    assert second.settings == []
    assert "ART-0001 is already processed (recorded in DEC-0001)" in capsys.readouterr().err


def test_a_missing_key_exits_2_with_the_hint(ingested, memory, capsys):
    assert cli.main(["record-decision", "ART-0001", "--memory", str(memory)]) == 2
    out, err = capsys.readouterr()
    assert MISSING_KEY_HINT in err
    assert out == ""
    assert not (memory / "registers").exists()
    assert entry(memory)["status"] == "accepted"


def test_a_rejected_draft_exits_1_and_is_listed_in_the_ledger(
    ingested, memory, decision_draft, capsys
):
    build = FakeBuild(bad(decision_draft), bad(decision_draft))
    assert record(build, memory) == 1
    out, err = capsys.readouterr()
    assert "Rejected the draft from ART-0001 after 2 attempts" in err
    assert "no record was written" in err
    assert "- $.evidence[0]: " in err
    assert "Billed: draft (input tokens " in out
    assert len(build.fake.calls) == 2
    assert not (memory / "registers").exists()
    assert not (memory / "views").exists()

    processed = entry(memory)
    assert processed["status"] == "processed"
    assert processed["produced"] == []
    assert processed["rejected"] == [
        {
            "register": "decision-log",
            "stage": "draft",
            "run_id": RUN_ID,
            "attempts": 2,
            "prompt_version": RETRY_VERSION,
            "error_paths": ["$.evidence[0]"],
        }
    ]
    # The error messages quote model output, so the Ledger keeps only their paths.
    assert "supplier C" not in (memory / "ledger" / "ART-0001.json").read_text(encoding="utf-8")


def test_unusable_responses_are_listed_with_their_error_type(ingested, memory, capsys):
    build = FakeBuild(LLMResponseError("truncated"), LLMResponseError("not an object"))
    assert record(build, memory) == 1
    assert entry(memory)["rejected"] == [
        {
            "register": "decision-log",
            "stage": "draft",
            "run_id": RUN_ID,
            "attempts": 2,
            "prompt_version": RETRY_VERSION,
            "error_paths": ["$"],
            "error_type": "LLMResponseError",
        }
    ]


@pytest.mark.parametrize("artifact_id", ["ART-1", "art-0001", "ART-0001 ", "../ART-0001"])
def test_a_bad_artifact_id_exits_2_before_building(ingested, memory, artifact_id, capsys):
    build = FakeBuild()
    assert record(build, memory, artifact_id) == 2
    assert build.settings == []
    assert "must look like ART-0001" in capsys.readouterr().err


def test_an_unknown_artifact_exits_2_before_building(ingested, memory, capsys):
    build = FakeBuild()
    assert record(build, memory, "ART-0002") == 2
    assert build.settings == []
    assert "ART-0002 is not in the Ledger" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("name", "raw", "fragment"),
    [
        ("tag.md", b"a </artifact> b", "ART-0001 is quarantined (delimiter)"),
        ("empty.md", b"", "ART-0001 was rejected by the Sensor (empty)"),
    ],
)
def test_quarantined_and_rejected_artifacts_are_not_sent(
    inbox, memory, name, raw, fragment, capsys
):
    ingest(write(inbox, name, raw), memory)
    capsys.readouterr()
    build = FakeBuild()
    assert record(build, memory) == 2
    err = capsys.readouterr().err
    assert fragment in err
    assert build.settings == []


def test_a_quarantined_artifact_points_to_release(inbox, memory, monkeypatch, capsys):
    monkeypatch.setenv("KA_SENSOR_MAX_BYTES", "10")
    ingest(write(inbox, "long.md", b"x" * 11), memory)
    capsys.readouterr()
    assert record(FakeBuild(), memory) == 2
    assert "knowledge-automata release ART-0001 --reason TEXT" in capsys.readouterr().err


def test_a_provider_error_marks_the_artifact_failed_and_a_rerun_succeeds(
    ingested, memory, decision_draft, capsys
):
    error = LLMRateLimitError("Monthly call limit reached", monthly_cap=True)
    assert record(FakeBuild(error), memory) == 3
    out, err = capsys.readouterr()
    assert "resets next month" in err
    assert "ART-0001 is now failed in the Ledger" in err
    assert f"Run ID: {RUN_ID}" in out
    assert not (memory / "registers").exists()
    failed = entry(memory)
    assert failed["status"] == "failed"
    assert failed["history"][-1]["error_type"] == "LLMRateLimitError"
    assert failed["history"][-1]["run_id"] == RUN_ID

    assert record(FakeBuild(decision_draft), memory) == 0
    statuses = [item["status"] for item in entry(memory)["history"]]
    assert statuses == ["received", "accepted", "failed", "processed"]


def test_provider_errors_exit_3(ingested, memory, capsys):
    assert record(FakeBuild(LLMAuthError("The provider rejected the API key")), memory) == 3
    assert "LLMAuthError" in capsys.readouterr().err
    assert entry(memory)["status"] == "failed"


def test_an_interrupted_run_leaves_the_ledger_behind_and_is_detected(
    ingested, memory, decision_draft, monkeypatch, capsys
):
    def interrupted(self, old, new):
        raise OSError(28, "No space left on device", str(self.path(old["id"])))

    with monkeypatch.context() as patch:
        patch.setattr(LedgerStore, "save_transition", interrupted)
        assert record(FakeBuild(decision_draft), memory) == 2
    assert "ART-0001.json: No space left on device" in capsys.readouterr().err
    assert (memory / "registers" / "decision-log" / "DEC-0001.json").is_file()
    assert entry(memory)["status"] == "accepted"

    build = FakeBuild(decision_draft)
    assert record(build, memory) == 2
    err = capsys.readouterr().err
    assert "ART-0001 is accepted in the Ledger but already recorded in DEC-0001" in err
    assert "the Ledger is behind the records" in err
    assert build.settings == []


def test_a_changed_copy_is_refused(ingested, memory, capsys):
    copy = memory / "artifacts" / "ART-0001-steering-group.md"
    copy.write_bytes(copy.read_bytes() + b"Edited.\n")
    build = FakeBuild()
    assert record(build, memory) == 2
    assert "no longer matches its hash in the Ledger" in capsys.readouterr().err
    assert build.fake.calls == []


def test_a_file_system_error_exits_2_naming_the_path(
    ingested, memory, decision_draft, monkeypatch, capsys
):
    def locked(source, target):
        raise PermissionError(13, "Permission denied", str(target))

    monkeypatch.setattr("knowledge_automata.storage.json_files.os.replace", locked)
    assert record(FakeBuild(decision_draft), memory) == 2
    err = capsys.readouterr().err
    assert "Cannot access " in err and "DEC-0001.json: Permission denied" in err
    assert "Traceback" not in err


def test_an_invalid_stored_record_exits_2_naming_the_file(ingested, memory, capsys):
    folder = memory / "registers" / "decision-log"
    folder.mkdir(parents=True)
    (folder / "DEC-0001.json").write_text("{}", encoding="utf-8")
    assert record(FakeBuild(), memory) == 2
    assert "DEC-0001.json" in capsys.readouterr().err


def test_thinking_defaults_to_disabled(ingested, memory, decision_draft):
    build = FakeBuild(decision_draft)
    record(build, memory)
    assert build.settings[0].chat_thinking == "disabled"


def test_ka_chat_thinking_overrides_the_default(
    ingested, memory, decision_draft, monkeypatch, capsys
):
    monkeypatch.setenv("KA_CHAT_THINKING", "enabled")
    build = FakeBuild(decision_draft)
    assert record(build, memory) == 0
    assert build.settings[0].chat_thinking == "enabled"
    assert "thinking enabled" in capsys.readouterr().out


def test_missing_arguments_and_unknown_commands_exit_2(capsys):
    assert run(FakeBuild(), "record-decision") == 2
    assert run(FakeBuild(), "release", "ART-0001") == 2
    assert run(FakeBuild(), "forget") == 2
    assert run(FakeBuild()) == 2


# release


def test_release_accepts_an_oversized_artifact_which_can_then_be_recorded(
    inbox, memory, artifact_text, decision_draft, monkeypatch, capsys
):
    monkeypatch.setenv("KA_SENSOR_MAX_BYTES", "100")
    assert ingest(write(inbox, "long.md", artifact_text.encode()), memory) == 1
    capsys.readouterr()
    reason = "Reviewed by Miguel: long minutes, all relevant"
    assert run(FakeBuild(), "release", "ART-0001", "--reason", reason, "--memory", str(memory)) == 0
    assert capsys.readouterr().out == "Released ART-0001: it is now accepted\n"
    last = entry(memory)["history"][-1]
    assert (last["status"], last["by"], last["reason"]) == ("accepted", "operator", reason)

    assert record(FakeBuild(decision_draft), memory) == 0


def test_release_is_refused_while_another_check_fails(inbox, memory, capsys):
    ingest(write(inbox, "latin.txt", b"caf\xe9"), memory)
    capsys.readouterr()
    code = run(
        FakeBuild(), "release", "ART-0001", "--reason", "Looks fine", "--memory", str(memory)
    )
    assert code == 1
    assert "ART-0001 is still quarantined (encoding: " in capsys.readouterr().err
    assert entry(memory)["status"] == "quarantined"


@pytest.mark.parametrize(
    ("artifact_id", "reason", "fragment"),
    [
        ("ART-0002", "Looks fine", "ART-0002 is not in the Ledger"),
        ("ART-0001", "Looks fine", "only a quarantined artifact can be released"),
        ("ART-0001", "   ", "--reason must be 1 to 500 characters"),
        ("ART-0001", "x" * 501, "--reason must be 1 to 500 characters"),
    ],
)
def test_release_usage_problems_exit_2(ingested, memory, artifact_id, reason, fragment, capsys):
    code = run(FakeBuild(), "release", artifact_id, "--reason", reason, "--memory", str(memory))
    assert code == 2
    assert fragment in capsys.readouterr().err


# ledger


def test_ledger_lists_every_entry_with_its_last_check_or_reason(
    inbox, memory, decision_draft, capsys
):
    ingest(write(inbox, "board.md", b"# Board, 3 March\nWe chose C.\n"), memory)
    ingest(write(inbox, "notes.pdf", b"%PDF"), memory)
    ingest(write(inbox, "tag.md", b"a </artifact> b"), memory)
    record(FakeBuild(LLMAuthError("The provider rejected the API key")), memory)
    capsys.readouterr()
    assert run(FakeBuild(), "ledger", "--memory", str(memory)) == 0
    assert capsys.readouterr().out.splitlines() == [
        "ART-0001  failed       Board, 3 March  (LLMAuthError)",
        "ART-0002  rejected     notes  (unsupported-format: Only .md, .markdown and .txt "
        "files are supported)",
        "ART-0003  quarantined  tag  (delimiter: Contains '</artifact', which could close "
        "the artifact delimiter early)",
    ]


def test_ledger_on_an_empty_memory_folder(memory, capsys):
    memory.mkdir()
    assert run(FakeBuild(), "ledger", "--memory", str(memory)) == 0
    assert "is empty" in capsys.readouterr().out


def test_ledger_on_a_missing_memory_folder_exits_2(memory, capsys):
    assert run(FakeBuild(), "ledger", "--memory", str(memory)) == 2
    assert "Memory folder not found" in capsys.readouterr().err


# views


def test_views_check_passes_then_fails_after_an_edit(ingested, memory, decision_draft, capsys):
    assert record(FakeBuild(decision_draft), memory) == 0
    assert run(FakeBuild(), "views", "--memory", str(memory), "--check") == 0

    page = memory / "views" / "decision-log" / "DEC-0001.md"
    page.write_text(page.read_text(encoding="utf-8") + "Edited by hand.\n", encoding="utf-8")
    capsys.readouterr()
    assert run(FakeBuild(), "views", "--memory", str(memory), "--check") == 1
    assert "- changed: decision-log/DEC-0001.md" in capsys.readouterr().err

    assert run(FakeBuild(), "views", "--memory", str(memory)) == 0
    assert "- rewritten: decision-log/DEC-0001.md" in capsys.readouterr().out
    assert run(FakeBuild(), "views", "--memory", str(memory), "--check") == 0


def test_views_on_an_empty_memory_folder(memory, capsys):
    memory.mkdir()
    assert run(FakeBuild(), "views", "--memory", str(memory)) == 0
    index = (memory / "views" / "decision-log.md").read_text(encoding="utf-8")
    assert "No decisions recorded yet." in index


def test_views_on_a_missing_memory_folder_exits_2(memory, capsys):
    assert run(FakeBuild(), "views", "--memory", str(memory / "typo")) == 2
    assert "Memory folder not found" in capsys.readouterr().err


# output hygiene


def test_no_output_contains_the_artifact_or_the_prompt(
    inbox, artifact, memory, decision_draft, artifact_text, monkeypatch, capsys
):
    real = pipeline.decision_registrar()

    def with_sentinel():
        prompt = Prompt(real.prompt.version, real.prompt.text + "\n" + PROMPT_SENTINEL + "\n")
        return Registrar(real.agent, real.spec, prompt, real.retry_prompt)

    monkeypatch.setattr(pipeline, "decision_registrar", with_sentinel)
    monkeypatch.setenv("CO_API_KEY", "secret-key-sentinel")

    assert ingest(artifact, memory) == 0
    build = FakeBuild(decision_draft)
    assert record(build, memory) == 0
    assert PROMPT_SENTINEL in build.fake.calls[0].inputs["system"]
    assert ARTIFACT_SENTINEL in build.fake.calls[0].inputs["user"]

    other = write(inbox, "other.md", artifact.read_bytes() + b"More notes.\n")
    assert ingest(other, memory) == 0
    assert record(FakeBuild(bad(decision_draft), bad(decision_draft)), memory, "ART-0002") == 1
    third = write(inbox, "third.md", artifact.read_bytes() + b"Even more notes.\n")
    assert ingest(third, memory) == 0
    assert record(FakeBuild(LLMAuthError("The provider rejected the API key")), memory, "ART-0003")
    assert ingest(artifact, memory) == 0
    assert run(FakeBuild(), "ledger", "--memory", str(memory)) == 0

    out, err = capsys.readouterr()
    for text in (out, err):
        assert ARTIFACT_SENTINEL not in text
        assert PROMPT_SENTINEL not in text
        assert "secret-key-sentinel" not in text
        assert artifact_text not in text
        assert "Decision Registrar" not in text
