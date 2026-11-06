# Changelog

All notable changes to Knowledge Automata are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Versions 0.0.x are pre-releases: the pipeline works on real meetings, and anything can still change.

## [0.0.1] - YYYY-MM-DD

The first pre-release, after handoffs 001 to 008: a whole meeting goes in, and every decision in it becomes a checked record in an institutional memory that keeps its sources and history.

### Added

- An LLM service layer on Cohere's SDK (Command A+, Embed and Rerank) behind provider-neutral interfaces, with a metadata-only event log of billed units, latency and request IDs ([ADR-0003](docs/decisions/0003-provider-agnostic-llm-service-layer.md), [ADR-0012](docs/decisions/0012-llm-service-layer-observation-and-cost.md)).
- The Sensor (intake and input guardrail) and the Artifact Ledger: deterministic intake checks, duplicates found by content hash, suspicious files quarantined for the Operator (human in the loop), and one Ledger entry per artifact that lists the records it produced ([ADR-0015](docs/decisions/0015-artifact-ledger-storage-and-sensor-checks.md)).
- The Governor (orchestrator): reads an accepted artifact once and returns one work order per decision or risk, each tied to quotes that code checks. Runs resume from the saved work orders, and an artifact with more items than a set limit is held for the Operator ([ADR-0018](docs/decisions/0018-governor-work-orders.md)).
- The Decision Registrar (specialist record keeper): drafts each decision, code validates the draft, one retry, then reject ([ADR-0014](docs/decisions/0014-registrar-drafting-loop.md)).
- The Comparator (reconciliation): each new decision is compared with the existing ones (Embed, then Rerank, then Command) and recorded as new, a reaffirmation, an update or a supersession; code applies the write rule ([ADR-0017](docs/decisions/0017-comparator-reconciliation.md)).
- Records as JSON files with sources and history, and generated Markdown views, checked against the records in CI.
- The command line: `ingest`, `process`, `release`, `ledger` and `views`.
- Every JSON-mode prompt ends with an instruction to reply with one JSON object that matches the response schema, kept there by a conformance test (handoff 008).
- A fictional sample project: nine meetings processed by real runs, with eight decision records and their views committed unedited ([examples/sample-project](examples/sample-project/README.md)).
- 970 tests that run offline, CI on Python 3.11 and 3.15 with a dependency audit, and 18 architecture decision records.

### Not yet included

- The Risk Registrar: risks are found and kept as work orders, not recorded yet (handoff 009).
- A command that processes a whole folder.
- The evaluation set and its harness, which will measure prompt changes.
- A software bill of materials: every release attaches one from v0.1.0 ([ADR-0010](docs/decisions/0010-supply-chain-security-baseline.md)).

### Known issues

- Thinking must stay enabled (the default). With thinking disabled, the Decision Registrar on meetings with several decisions, and the Comparator, still write their reasoning before the JSON, and the reply is rejected ([handoff 008, section 9](dev/handoffs/008-json-instruction.md)).
- The Governor's call on one sample meeting (ART-0006) sometimes returns nothing within 180 s. The run stops with nothing written and can be rerun ([backlog](dev/backlog.md)).
- Real-run findings for the evaluation set: an update can take a later meeting's date as `decided_on`, an update can fill no field, and an impact can restate the decision ([backlog](dev/backlog.md)).

[0.0.1]: https://github.com/miguelmog10/knowledge-automata/releases/tag/v0.0.1
