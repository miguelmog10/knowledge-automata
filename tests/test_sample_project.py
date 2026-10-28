from pathlib import Path

from knowledge_automata.agents.sensor import content_hash
from knowledge_automata.domains.project_management.registers import DECISION_LOG
from knowledge_automata.storage.ledger_store import LedgerStore
from knowledge_automata.storage.record_store import RecordStore

SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sample-project"


def test_the_backfilled_ledger_entry_matches_the_sample_project():
    entry = LedgerStore(SAMPLE).load("ART-0001")
    copy = SAMPLE / entry["stored_path"]
    # The hash ignores line endings, so it holds on any checkout. size_bytes is not compared
    # with the file: autocrlf may change the bytes on disk (backlog, Open questions).
    assert content_hash(copy.read_bytes()) == entry["content_hash"]
    assert entry["source"]["name"] == copy.name
    assert entry["status"] == "processed"

    records = {record["id"]: record for record in RecordStore(SAMPLE).load_all(DECISION_LOG)}
    for produced in entry["produced"]:
        record = records[produced["record_id"]]
        assert {source["artifact_id"] for source in record["sources"]} == {entry["id"]}
        assert produced["model"] == record["history"][0]["model"]
        assert produced["prompt_version"] == record["history"][0]["prompt_version"]
        assert produced["schema_version"] == record["schema_version"]
    cited = {
        record_id
        for record_id, record in records.items()
        if any(source["artifact_id"] == entry["id"] for source in record["sources"])
    }
    assert {item["record_id"] for item in entry["produced"]} == cited
