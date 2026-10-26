# Backlog

## Now (v0.1, first working slice)

- Markdown view generator: the decision log view is done (handoff 004); the risk register view comes with the Risk Registrar. JSON records stay the source of truth; code generates the views and nobody edits them by hand.
  - Risk register: one table sorted by the computed score (probability times impact).
  - Decision log (done): an index table and one page per decision.
  - Each page starts with a short front matter block (ID, status, dates).
  - Standard relative Markdown links only, no double-bracket wiki links: supersession linked both ways, each record linked to its source artifacts, and the index linked to each record, so the registers browse like a wiki.
  - A test renders fixture records against expected output, and a CI check fails if committed views differ from the generator's output (done for the decision log).
- Sensor (intake and input guardrail) with deterministic checks (empty, unsupported format, oversized, encoding, duplicate hash), Artifact Ledger and quarantine path.
- Governor (orchestrator and router): classification and work orders.
- Comparator (reconciliation) using Embed and Rerank.
- Risk Registrar, and the Decision Registrar's remaining write rules (update, reaffirmation, supersession).
- Fictional sample project in `examples/`, doubling as a small evaluation set with expected records.
- CLI entry point to run the pipeline over a folder.
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
- Issue log Registrar, including proposals and open questions found in artifacts (dropped in v0.1, ADR-0011) and risks that occurred.
- Operator (human in the loop) review of evidence-check rejections.
- Remaining PMBOK risk fields: urgency, proximity, contingency and fallback plans, residual and secondary risks, reserves.
- Typed Python models for records, only with a test that keeps them in sync with the schema files.
- Store the envelope version in each record before the first envelope change.
- Probability-impact heat map in the risk register view.
- Links across registers, for example a risk mitigated by a decision (a minor schema change).
- Opt-in debug capture of prompts and responses to a git-ignored folder, for prompt tuning (never in the event log).
- Plain-text `chat` in the service layer, when an agent needs it (for example the Oracle).
- Budget guard: stop a run before it exceeds a call or cost limit (trial keys are capped).
- Event log rotation or archiving, if the file grows large.
- A small report that sums calls, units and cost per run, per agent and per artifact from the event log.
- Thinking on versus off for the Registrars, measured on the evaluation set.

### When collaborators join

- Raise required approvals to 1.
- Add CODEOWNERS with code-owner review for `schemas/`, `docs/decisions/` and `AGENTS.md`.
- Dismiss stale approvals and require conversation resolution.
- Add CONTRIBUTING.md, a code of conduct and issue templates.
- Keep approval required for workflow runs from first-time contributors.
- Decide between a CLA and a DCO before the first external pull request.

## Open questions

- Storage for records: decided, one JSON file per record ([ADR-0013](../docs/decisions/0013-record-storage-json-files.md)). The Artifact Ledger's storage is decided with the Sensor.
- Artifact Ledger status when some of an artifact's records are rejected (for example a `processed` status with a list of rejections).
- How a Registrar reports that an artifact has nothing to record. The draft schema always requires content; this is probably the Governor's job (it only sends work orders for items it found).
- Persisting rejected drafts and their errors: with the Artifact Ledger's `failed` status (ADR-0006).
- Sensor content hashes must ignore line endings (CRLF versus LF), so the same artifact hashes the same on Windows and in CI.
- Cohere's trial monthly cap: the docs give no exact wording for the 429 it returns, so the adapter marks a 429 as the monthly cap only when the message mentions "month" (`llm/cohere_adapter.py`). Confirm the wording the first time it happens.
- Chat thinking default for the Registrars: decided for the Decision Registrar, thinking disabled unless `KA_CHAT_THINKING` is set ([ADR-0014](../docs/decisions/0014-registrar-drafting-loop.md)); revisited with the evaluation set (see *Later*).
- Prices: Cohere's pricing page lists no per-token or per-search-unit prices for the configured models, so `prices.toml` has no model entries and events carry no `cost_usd`. Fill the table when prices are published, or record an official source.
- Python 3.15: PyYAML (pulled in by the Cohere SDK through `tokenizers` and `huggingface-hub`) has no 3.15 wheel yet and builds from source. CI shows whether that works on Ubuntu; on Windows it needs a C compiler.

## Technical debt

- (empty)
