# Backlog

## Now (v0.1, first working slice)

- Decision and Risk register schemas, PMI-mapped (design with Claude first).
- LLM service layer with a Cohere adapter and a fake adapter for tests.
- Structured event logging for every LLM call, plus a dated price table and token-to-cost function.
- Sensor (intake and input guardrail) with deterministic checks (empty, unsupported format, oversized, encoding, duplicate hash), Artifact Ledger and quarantine path.
- Governor (orchestrator and router): classification and work orders.
- Comparator (reconciliation) using Embed and Rerank.
- Decision Registrar and Risk Registrar (specialist record keepers).
- Fictional sample project in `examples/`, doubling as a small evaluation set with expected records.
- CLI entry point to run the pipeline over a folder.
- Lock file, added with the first runtime dependency (the Cohere SDK).
- Release workflow that generates a CycloneDX SBOM and attaches it to the v0.1.0 tag.

## Stretch (v0.1)

- Oracle (query interface): question answering over the registers with citations.

## Later

- Observer (quality control): periodic health and cross-register consistency checks.
- Remaining registrars: issue log, assumption log, change log, lessons learned, stakeholder register; glossary as a minor register.
- Additional domains beyond project management (for example associations or research groups), each as its own set of Registrars and schemas.
- Operator (human in the loop) approval workflow for sensitive changes; quarantine review and release.
- Sensor relevance check and prompt-injection detection.
- Oracle insight feedback loop: Operator-confirmed conclusions from Oracle conversations are saved as new raw artifacts ("insight notes") and re-enter through the Sensor, so there is still one write path.
- Enterprise connectors (Jira, Confluence, Microsoft Teams) as Sensor sources.
- Alternative LLM providers behind the service layer.
- OpenTelemetry-compatible observability; analytics over the event log.
- Threat model and security review; cybersecurity compliance considerations (for example the EU Cyber Resilience Act).
- Role contracts documented so other platforms can implement roles (reference implementation vision).
- CodeQL code scanning (free for public repos).
- OpenSSF Scorecard.
- Build provenance and signed releases (GitHub artifact attestations, SLSA).
- mypy type checking.
- Coverage report.
- Evaluation job against real Cohere models that runs manually or on `main` only, never on pull requests from forks.
- Cost tracking automation: test whether the VS Code chat export includes per-request credits; if so, script it into `dev/costs.md`.
- Cohere token costs in `dev/costs.md` once the pipeline makes real calls.
- Write the Knowledge Automata case study in the principles repo at v0.1.0.

### When collaborators join

- Raise required approvals to 1.
- Add CODEOWNERS with code-owner review for `schemas/`, `docs/decisions/` and `AGENTS.md`.
- Dismiss stale approvals and require conversation resolution.
- Add CONTRIBUTING.md, a code of conduct and issue templates.
- Keep approval required for workflow runs from first-time contributors.
- Decide between a CLA and a DCO before the first external pull request.

## Open questions

- Which PMBOK edition should the schemas cite? This includes whether that edition names the decision log as an artifact (see ADR-0007).
- Storage details for records and the ledger (JSON files per record, one file per register, or SQLite).

## Technical debt

- (empty)
