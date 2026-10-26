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
    MemorySink,
    ObservedLLM,
)
from knowledge_automata.llm.fake import FakeLLM
from knowledge_automata.llm.settings import MISSING_KEY_HINT

RUN_ID = "7d1c6a52-3b0e-4c47-9a57-0e6f2d1f9a10"
NOW = datetime(2026, 10, 26, 14, 3, 12, tzinfo=UTC)
ARTIFACT_SENTINEL = "SENTINEL-ARTIFACT-4b81 do not print this line"
PROMPT_SENTINEL = "SENTINEL-PROMPT-c27e"


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
    for name in ["CO_API_KEY", "KA_CHAT_THINKING", "KA_CHAT_MODEL", "KA_EVENT_LOG"]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def memory(tmp_path):
    return tmp_path / "memory"


@pytest.fixture
def artifact(memory, artifact_text):
    folder = memory / "artifacts"
    folder.mkdir(parents=True)
    path = folder / "ART-0001-steering-group.md"
    path.write_text(artifact_text + "\n" + ARTIFACT_SENTINEL + "\n", encoding="utf-8")
    return path


def bad(draft):
    return draft | {"evidence": ["The group chose supplier C."]}


def run(build, *args):
    return cli.main(list(args), build=build, clock=lambda: NOW)


def record(build, artifact, memory, *extra):
    return run(
        build,
        "record-decision",
        str(artifact),
        "--artifact-id",
        "ART-0001",
        "--artifact-date",
        "2026-03-12",
        "--memory",
        str(memory),
        *extra,
    )


def test_record_decision_stores_the_record_and_writes_the_views(
    artifact, memory, decision_draft, capsys
):
    build = FakeBuild(decision_draft)
    assert record(build, artifact, memory) == 0

    out, err = capsys.readouterr()
    assert err == ""
    assert f"Run ID: {RUN_ID}" in out
    assert (
        "Recorded DEC-0001 from ART-0001 in 1 attempt "
        "(model fake-chat, prompt decision-registrar.v1, thinking disabled)"
    ) in out
    assert "Billed tokens: " in out and " input, " in out
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


def test_retry_is_reported_with_its_prompt_version(artifact, memory, decision_draft, capsys):
    build = FakeBuild(bad(decision_draft), decision_draft)
    assert record(build, artifact, memory) == 0
    out = capsys.readouterr().out
    assert "in 2 attempts" in out
    assert "prompt decision-registrar.v1+registrar-retry.v1" in out
    stored = json.loads(
        (memory / "registers" / "decision-log" / "DEC-0001.json").read_text(encoding="utf-8")
    )
    assert stored["history"][0]["prompt_version"] == "decision-registrar.v1+registrar-retry.v1"


def test_a_second_run_on_the_same_artifact_makes_no_call(artifact, memory, decision_draft, capsys):
    assert record(FakeBuild(decision_draft), artifact, memory) == 0
    capsys.readouterr()
    second = FakeBuild(decision_draft)
    assert record(second, artifact, memory) == 2
    assert second.fake.calls == []
    assert "ART-0001 is already recorded in DEC-0001" in capsys.readouterr().err


def test_a_missing_key_exits_2_with_the_hint(artifact, memory, capsys):
    assert (
        cli.main(
            ["record-decision", str(artifact), "--artifact-id", "ART-0001", "--memory", str(memory)]
        )
        == 2
    )
    out, err = capsys.readouterr()
    assert MISSING_KEY_HINT in err
    assert out == ""
    assert not (memory / "registers").exists()


def test_a_rejected_draft_exits_1_and_writes_nothing(artifact, memory, decision_draft, capsys):
    build = FakeBuild(bad(decision_draft), bad(decision_draft))
    assert record(build, artifact, memory) == 1
    out, err = capsys.readouterr()
    assert "Rejected the draft from ART-0001 after 2 attempts" in err
    assert "nothing was written" in err
    assert "- $.evidence[0]: " in err
    assert "Billed tokens: " in out
    assert len(build.fake.calls) == 2
    assert not (memory / "registers").exists()
    assert not (memory / "views").exists()


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("--artifact-id", "ART-1"),
        ("--artifact-id", "art-0001"),
        ("--artifact-id", "ART-0001 "),
        ("--artifact-date", "2026-02-30"),
        ("--artifact-date", "2026-2-3"),
        ("--artifact-date", "03/02/2026"),
    ],
)
def test_bad_artifact_arguments_exit_2_before_building(artifact, memory, option, value, capsys):
    args = {"--artifact-id": "ART-0001", "--artifact-date": "2026-03-12"} | {option: value}
    build = FakeBuild()
    code = run(
        build,
        "record-decision",
        str(artifact),
        "--memory",
        str(memory),
        *[item for pair in args.items() for item in pair],
    )
    assert code == 2
    assert build.settings == []
    assert option in capsys.readouterr().err


def test_missing_arguments_and_unknown_commands_exit_2(capsys):
    assert run(FakeBuild(), "record-decision", "a.md") == 2
    assert run(FakeBuild(), "forget") == 2
    assert run(FakeBuild()) == 2


def test_a_missing_artifact_exits_2(memory, capsys):
    code = run(FakeBuild(), "record-decision", "nope.md", "--artifact-id", "ART-0001")
    assert code == 2
    assert "Cannot read the artifact nope.md" in capsys.readouterr().err


def test_views_check_passes_then_fails_after_an_edit(artifact, memory, decision_draft, capsys):
    assert record(FakeBuild(decision_draft), artifact, memory) == 0
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


def test_thinking_defaults_to_disabled(artifact, memory, decision_draft):
    build = FakeBuild(decision_draft)
    record(build, artifact, memory)
    assert build.settings[0].chat_thinking == "disabled"


def test_ka_chat_thinking_overrides_the_default(
    artifact, memory, decision_draft, monkeypatch, capsys
):
    monkeypatch.setenv("KA_CHAT_THINKING", "enabled")
    build = FakeBuild(decision_draft)
    assert record(build, artifact, memory) == 0
    assert build.settings[0].chat_thinking == "enabled"
    assert "thinking enabled" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("error", "fragment"),
    [
        (LLMRateLimitError("Monthly call limit reached", monthly_cap=True), "resets next month"),
        (LLMAuthError("The provider rejected the API key"), "LLMAuthError"),
    ],
)
def test_provider_errors_exit_3(artifact, memory, error, fragment, capsys):
    assert record(FakeBuild(error), artifact, memory) == 3
    assert fragment in capsys.readouterr().err
    assert not (memory / "registers").exists()


def test_a_file_system_error_exits_2_naming_the_path(
    artifact, memory, decision_draft, monkeypatch, capsys
):
    def locked(source, target):
        raise PermissionError(13, "Permission denied", str(target))

    monkeypatch.setattr("knowledge_automata.storage.record_store.os.replace", locked)
    assert record(FakeBuild(decision_draft), artifact, memory) == 2
    err = capsys.readouterr().err
    assert "Cannot access " in err and "DEC-0001.json: Permission denied" in err
    assert "Traceback" not in err


def test_an_invalid_stored_record_exits_2_naming_the_file(artifact, memory, capsys):
    folder = memory / "registers" / "decision-log"
    folder.mkdir(parents=True)
    (folder / "DEC-0001.json").write_text("{}", encoding="utf-8")
    assert record(FakeBuild(), artifact, memory) == 2
    assert "DEC-0001.json" in capsys.readouterr().err


def test_no_output_contains_the_artifact_or_the_prompt(
    artifact, memory, decision_draft, artifact_text, monkeypatch, capsys
):
    real = pipeline.decision_registrar()

    def with_sentinel():
        prompt = Prompt(real.prompt.version, real.prompt.text + "\n" + PROMPT_SENTINEL + "\n")
        return Registrar(real.agent, real.spec, prompt, real.retry_prompt)

    monkeypatch.setattr(pipeline, "decision_registrar", with_sentinel)
    monkeypatch.setenv("CO_API_KEY", "secret-key-sentinel")

    build = FakeBuild(decision_draft)
    assert record(build, artifact, memory) == 0
    assert PROMPT_SENTINEL in build.fake.calls[0].inputs["system"]
    assert ARTIFACT_SENTINEL in build.fake.calls[0].inputs["user"]

    other = memory / "artifacts" / "ART-0002-other.md"
    other.write_text(artifact.read_text(encoding="utf-8"), encoding="utf-8")
    rejected = FakeBuild(bad(decision_draft), bad(decision_draft))
    assert (
        run(
            rejected,
            "record-decision",
            str(other),
            "--artifact-id",
            "ART-0002",
            "--memory",
            str(memory),
        )
        == 1
    )

    out, err = capsys.readouterr()
    for text in (out, err):
        assert ARTIFACT_SENTINEL not in text
        assert PROMPT_SENTINEL not in text
        assert "secret-key-sentinel" not in text
        assert artifact_text not in text
        assert "Decision Registrar" not in text
