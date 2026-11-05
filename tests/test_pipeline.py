from datetime import UTC, datetime

import pytest

from knowledge_automata import pipeline
from knowledge_automata.agents.comparator import ComparatorSettings
from knowledge_automata.agents.governor import GovernorSettings
from knowledge_automata.llm import LLMConfigError, LLMSettings, MemorySink, ObservedLLM
from knowledge_automata.llm.fake import FakeLLM
from knowledge_automata.storage.ledger_store import LedgerStore

NOW = datetime(2026, 10, 26, 14, 3, 12, tzinfo=UTC)


def test_decision_registrar_uses_the_v3_prompt_with_work_orders():
    registrar = pipeline.decision_registrar()
    assert registrar.agent == "decision-registrar"
    assert registrar.spec.name == "decision-log"
    assert registrar.prompt.version == "decision-registrar.v3"
    assert registrar.retry_version == "decision-registrar.v3+registrar-retry.v2"
    assert registrar.takes_work_order


def test_only_the_decision_log_has_a_registrar():
    assert list(pipeline.REGISTRARS) == ["decision-log"]
    assert pipeline.REGISTER_NAMES == ("decision-log", "risk-register")


def test_the_governor_uses_its_v2_prompts_and_every_definition():
    governor = pipeline.governor()
    assert governor.agent == "governor"
    assert governor.prompt.version == "governor.v2"
    assert governor.retry_version == "governor.v2+governor-retry.v2"
    assert governor.definition_versions == ("decision-log.v1", "risk-register.v1")


def test_the_comparator_uses_its_v2_prompts():
    comparator = pipeline.decision_comparator()
    assert comparator.agent == "comparator"
    assert comparator.spec.name == "decision-log"
    assert comparator.prompt.version == "decision-comparator.v2"
    assert comparator.retry_prompt.version == "comparator-retry.v2"


def test_thinking_defaults_to_enabled_unless_set():
    assert pipeline.CHAT_THINKING_DEFAULT == "enabled"
    assert pipeline.agent_chat_settings(LLMSettings()).chat_thinking == "enabled"
    disabled = LLMSettings(chat_thinking="disabled")
    assert pipeline.agent_chat_settings(disabled).chat_thinking == "disabled"


def ingest(memory, tmp_path, name, raw, **extra):
    path = tmp_path / name
    path.write_bytes(raw)
    return pipeline.ingest_file(
        path=path, memory=memory, artifact_date=None, max_bytes=1_000, now=NOW, **extra
    ).entry


def test_artifact_links_come_from_ledger_entries_with_a_copy(tmp_path):
    memory = tmp_path / "memory"
    ingest(memory, tmp_path, "board.md", b"Board notes\n")
    ingest(memory, tmp_path, "notes.pdf", b"%PDF")
    ingest(memory, tmp_path, "tag.md", b"a </artifact> b")
    # A file without a Ledger entry is never linked.
    (memory / "artifacts" / "ART-0009-stray.md").write_text("x", encoding="utf-8")
    assert pipeline.artifact_links(memory) == {
        "ART-0001": "artifacts/ART-0001-board.md",
        "ART-0003": "artifacts/ART-0003-tag.md",
    }


def test_artifact_links_without_a_ledger(tmp_path):
    assert pipeline.artifact_links(tmp_path) == {}


def test_the_stored_copy_is_read_without_bom_and_with_lf(tmp_path):
    memory = tmp_path / "memory"
    entry = ingest(memory, tmp_path, "a.md", b"\xef\xbb\xbfLine one\r\nLine two\rLine three\n")
    assert pipeline.read_artifact_text(memory, entry) == "Line one\nLine two\nLine three\n"


def test_a_copy_with_other_line_endings_still_matches_its_hash(tmp_path):
    # A Windows checkout may turn LF into CRLF; the hash ignores line endings.
    memory = tmp_path / "memory"
    entry = ingest(memory, tmp_path, "a.md", b"Line one\nLine two\n")
    copy = memory / entry["stored_path"]
    copy.write_bytes(b"Line one\r\nLine two\r\n")
    assert pipeline.read_artifact_text(memory, entry) == "Line one\nLine two\n"


def test_a_changed_copy_is_refused(tmp_path):
    memory = tmp_path / "memory"
    entry = ingest(memory, tmp_path, "a.md", b"Line one\n")
    (memory / entry["stored_path"]).write_bytes(b"Line two\n")
    with pytest.raises(pipeline.InputError, match="no longer matches its hash"):
        pipeline.read_artifact_text(memory, entry)


def process(memory, llm):
    return pipeline.process_artifact(
        artifact_id="ART-0001",
        memory=memory,
        llm=llm,
        now=NOW,
        comparator_settings=ComparatorSettings(),
        governor_settings=GovernorSettings(),
    )


def test_process_needs_a_run_id_before_any_call(tmp_path, decision_draft):
    memory = tmp_path / "memory"
    ingest(memory, tmp_path, "a.md", b"Line one\n")
    fake = FakeLLM([decision_draft])
    with pytest.raises(ValueError, match="run_id"):
        process(memory, fake)
    assert fake.calls == []
    assert LedgerStore(memory).load("ART-0001")["status"] == "accepted"


def test_process_needs_an_llm_when_a_call_is_planned(tmp_path):
    memory = tmp_path / "memory"
    ingest(memory, tmp_path, "a.md", b"Line one\n")
    with pytest.raises(ValueError, match="needs an LLM"):
        process(memory, None)
    assert LedgerStore(memory).load("ART-0001")["status"] == "accepted"


def test_a_configuration_error_leaves_the_status_unchanged(tmp_path):
    memory = tmp_path / "memory"
    ingest(memory, tmp_path, "a.md", b"Line one\n")
    llm = ObservedLLM(FakeLLM([LLMConfigError("No model")]), provider="fake", sink=MemorySink())
    with pytest.raises(LLMConfigError):
        process(memory, llm)
    assert LedgerStore(memory).load("ART-0001")["status"] == "accepted"
    assert not (memory / "work-orders").exists()
