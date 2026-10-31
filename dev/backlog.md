# Backlog

## Now (v0.1, first working slice)

- Markdown view generator: the decision log view is done (handoff 004); the risk register view comes with the Risk Registrar. JSON records stay the source of truth; code generates the views and nobody edits them by hand.
  - Risk register: one table sorted by the computed score (probability times impact).
  - Decision log (done): an index table and one page per decision.
  - Each page starts with a short front matter block (ID, status, dates).
  - Standard relative Markdown links only, no double-bracket wiki links: supersession linked both ways, each record linked to its source artifacts, and the index linked to each record, so the registers browse like a wiki.
  - A test renders fixture records against expected output, and a CI check fails if committed views differ from the generator's output (done for the decision log).
- Governor (orchestrator and router): classification and work orders.
- Risk Registrar.
- Fictional sample project in `examples/`, doubling as a small evaluation set with expected records.
- CLI entry point to run the pipeline over a folder.
- Release workflow that generates a CycloneDX SBOM and attaches it to the v0.1.0 tag.

## Stretch (v0.1)

- Oracle (query interface): question answering over the registers with citations.

## Later

- Observer (quality control): periodic health and cross-register consistency checks.
- Remaining registrars: issue log, assumption log, change log, lessons learned, stakeholder register; glossary as a minor register.
- Additional domains beyond project management (for example associations or research groups), each as its own set of Registrars and schemas.
- Operator (human in the loop) approval workflow for sensitive changes.
- Operator release workflow beyond the `release` command (review queue, reasons, notifications).
- Chunking long artifacts after Operator approval: evidence quotes must still match the original text, and a decision can span two chunks.
- Document versions: treat an artifact as a new version of an earlier one and process only what changed.
- Format converters (PDF, Word) as a step before the Sensor; the Ledger hashes the original file and stores the extracted text that evidence is checked against.
- Artifact Ledger Markdown view.
- Reprocessing an artifact that produced records, after a prompt change: needs a `correction` change that replaces content and keeps history (update, reaffirmation and supersession all misdescribe it), a way out of `processed`, and reruns in artifact date order.
- Rerunning an artifact whose draft was rejected: done for artifacts that recorded nothing (handoff 006). `record-decision` runs them again from `processed` or `failed`, keeping the earlier rejected drafts.
- Tune `KA_COMPARATOR_TOP_K` and `KA_COMPARATOR_TOP_N` on the evaluation set, and consider a minimum Rerank score below which candidates are dropped and the draft is classified as new without a Command call (saves calls, but a wrong threshold lets duplicates in).
- Skip Embed when the register has no more active records than K (Rerank can read them all).
- A cheap pre-check that skips drafting for obvious repeats, if reaffirmation drafts become a visible cost in the event log.
- A git-ignored embedding cache next to the records, if the register grows large.
- Automatic repair of an interrupted supersession.
- Supersession of more than one record at once (`relations.supersedes` already allows a list).
- Repair for a Ledger left behind its records by an interrupted run (today the pipeline detects it and stops).
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
- Diagram copy check: a small script that copies each Mermaid block in `docs/diagrams/` into `README.md` and `docs/architecture.md` between their `diagram` markers, with a `--check` mode that CI runs (like `views --check`). Until then the copies are kept by hand.
- Guide on the mise-en-place screen theme: load its pinned `tokens.css` and Mermaid themes instead of the values in `docs/guide/index.html`, once mise-en-place v0.2 is tagged.
- Issue log Registrar, including proposals and open questions found in artifacts (dropped in v0.1, ADR-0011) and risks that occurred.
- Operator (human in the loop) review of evidence-check rejections.
- Remaining PMBOK risk fields: urgency, proximity, contingency and fallback plans, residual and secondary risks, reserves.
- Typed Python models for records, only with a test that keeps them in sync with the schema files.
- Store the envelope version in each record before the first envelope change.
- Probability-impact heat map in the risk register view.
- Links across registers, for example a risk mitigated by a decision (a minor schema change).
- Opt-in debug capture of prompts and responses to a git-ignored folder, for prompt tuning (never in the event log). A throwaway version (`runtime/diagnostics/inspect_chat_reply.py`, handoff 006 Addendum A) found the thinking problem with four calls.
- Plain-text `chat` in the service layer, when an agent needs it (for example the Oracle).
- Budget guard: stop a run before it exceeds a call or cost limit (trial keys are capped).
- Event log rotation or archiving, if the file grows large.
- A small report that sums calls, units and cost per run, per agent and per artifact from the event log.
- Thinking token budget (`token_budget`) for the Registrars and the Comparator, measured on the evaluation set.
- Prompt v2 candidates for the Decision Registrar, judged on the evaluation set, not on one artifact:
  - `decided_by` listed everyone present instead of the group named in the decision ("the board").
  - `impacts` was a generic summary not supported by the artifact, although the prompt says to omit unsupported fields.

### When collaborators join

- Raise required approvals to 1.
- Add CODEOWNERS with code-owner review for `schemas/`, `docs/decisions/` and `AGENTS.md`.
- Dismiss stale approvals and require conversation resolution.
- Add CONTRIBUTING.md, a code of conduct and issue templates.
- Keep approval required for workflow runs from first-time contributors.
- Decide between a CLA and a DCO before the first external pull request.

## Open questions

- Storage for records: decided, one JSON file per record ([ADR-0013](../docs/decisions/0013-record-storage-json-files.md)). The Artifact Ledger's storage: decided, one JSON file per artifact with an append-only history ([ADR-0015](../docs/decisions/0015-artifact-ledger-storage-and-sensor-checks.md)).
- Artifact Ledger status when some of an artifact's records are rejected: decided, `processed` with a list of rejected drafts ([ADR-0015](../docs/decisions/0015-artifact-ledger-storage-and-sensor-checks.md)).
- How a Registrar reports that an artifact has nothing to record. The draft schema always requires content; this is probably the Governor's job (it only sends work orders for items it found).
- Persisting rejected drafts and their errors: decided, the Ledger lists each rejected draft by register, attempts, prompt version and error paths, plus the error type when the last response was unusable, never the full error messages, because evidence errors quote model output ([ADR-0015](../docs/decisions/0015-artifact-ledger-storage-and-sensor-checks.md)).
- Sensor content hashes must ignore line endings (CRLF versus LF): decided, SHA-256 over the bytes without a leading BOM and with line endings as LF ([ADR-0015](../docs/decisions/0015-artifact-ledger-storage-and-sensor-checks.md)).
- Record finish_reason and the adapter's error message in LLM events: done, event schema 1.1 ([ADR-0012](../docs/decisions/0012-llm-service-layer-observation-and-cost.md), amended).
- Keep artifact copies byte-identical on every checkout, for example a .gitattributes rule marking examples/*/artifacts/** as -text, so stored_path holds the original bytes and size_bytes matches the file.
- Cohere's trial monthly cap: the docs give no exact wording for the 429 it returns, so the adapter marks a 429 as the monthly cap only when the message mentions "month" (`llm/cohere_adapter.py`). Confirm the wording the first time it happens.
- Chat thinking default for the Registrars and the Comparator: decided, thinking enabled unless `KA_CHAT_THINKING` is set (amended 2026-10-31 after the handoff 006 real run, [ADR-0014](../docs/decisions/0014-registrar-drafting-loop.md)); the token budget is measured with the evaluation set (see *Later*).
- Prices: Cohere's pricing page lists no per-token or per-search-unit prices for the configured models, so `prices.toml` has no model entries and events carry no `cost_usd`. Fill the table when prices are published, or record an official source.
- Python 3.15: PyYAML (pulled in by the Cohere SDK through `tokenizers` and `huggingface-hub`) has no 3.15 wheel yet and builds from source. CI shows whether that works on Ubuntu; on Windows it needs a C compiler.
- Embed input types for comparing records with records: the Comparator embeds records as documents and the draft as a query (the usual search setup); whether a symmetric input type compares decisions better is untested.

## Technical debt

- If writing the views or the Ledger entry fails after a record is saved, a rerun of `record-decision` is refused because the Ledger is behind the records. The fix is by hand today (`knowledge-automata views`, then the Ledger entry); the error could say so step by step.
- `release` does not check the stored copy's hash: a quarantined copy edited in place is released, then refused by `record-decision`. Checking the hash at release would fail sooner, with the same message.
- A crash between writing an artifact copy and its Ledger entry leaves an orphan copy, and the next `ingest` stops on "file exists" for the same ID until the copy is deleted. It fails loudly; the error could say which file to remove.
