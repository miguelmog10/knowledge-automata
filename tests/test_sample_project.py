from pathlib import Path

from knowledge_automata.agents.sensor import content_hash, copy_name
from knowledge_automata.domains.project_management.registers import DECISION_LOG
from knowledge_automata.storage.ledger_store import LedgerStore
from knowledge_automata.storage.record_store import RecordStore

SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sample-project"


def test_every_ledger_entry_matches_the_sample_project():
    records = {record["id"]: record for record in RecordStore(SAMPLE).load_all(DECISION_LOG)}
    entries = LedgerStore(SAMPLE).load_all()
    assert entries
    for entry in entries:
        copy = SAMPLE / entry["stored_path"]
        # The hash ignores line endings, so it holds on any checkout. size_bytes is not
        # compared with the file: autocrlf may change the bytes on disk (backlog, Open
        # questions).
        assert content_hash(copy.read_bytes()) == entry["content_hash"], entry["id"]
        assert copy_name(entry["id"], entry["source"]["name"]) == copy.name, entry["id"]
        assert entry["status"] == "processed"

        for produced in entry["produced"]:
            record = records[produced["record_id"]]
            change = produced.get("change", "new")
            steps = [
                step
                for step in record["history"]
                if step["artifact_id"] == entry["id"] and step["change"] == change
            ]
            assert len(steps) == 1, (entry["id"], produced["record_id"])
            assert produced["model"] == steps[0]["model"]
            assert produced["prompt_version"] == steps[0]["prompt_version"]
            assert produced["schema_version"] == record["schema_version"]
            if "related_id" in produced:
                assert steps[0]["related_id"] == produced["related_id"]
        cited = {
            record_id
            for record_id, record in records.items()
            if any(source["artifact_id"] == entry["id"] for source in record["sources"])
        }
        assert {item["record_id"] for item in entry["produced"]} == cited, entry["id"]
