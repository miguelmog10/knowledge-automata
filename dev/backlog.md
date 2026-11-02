# Backlog

## Now (v0.1, first working slice)

- Markdown view generator: the decision log view is done (handoff 004); the risk register view comes with the Risk Registrar. JSON records stay the source of truth; code generates the views and nobody edits them by hand.
  - Risk register: one table sorted by the computed score (probability times impact).
  - Decision log (done): an index table and one page per decision.
  - Each page starts with a short front matter block (ID, status, dates).
  - Standard relative Markdown links only, no double-bracket wiki links: supersession linked both ways, each record linked to its source artifacts, and the index linked to each record, so the registers browse like a wiki.
  - A test renders fixture records against expected output, and a CI check fails if committed views differ from the generator's output (done for the decision log).
- Governor (orchestrator and router): work orders, resumable runs, the `held` status and the `process` command (handoff 007: parts 7A and 7B built and tested offline, part 7C the real run on ART-0006 to ART-0008 of the sample project; ADR-0018 accepted).
- Risk Registrar. The Governor already finds risks (handoff 007) and keeps their work orders as not routed; whether the Risk Registrar drafts from those saved work orders or through reprocessing is decided in its handoff.
- Fictional sample project in `examples/`, doubling as a small evaluation set with expected records.
  - Evaluation harness, grown from the handoff 007 spike (`runtime/diagnostics/spike_governor.py`, git-ignored): a committed script with a call budget, the expected results as a data file (from `dev/handoffs/007-governor-inputs.md` and the handoff 006 table), and a short saved report per run (counts matched, quotes passed, records as expected, calls and tokens used), so runs can be compared, for example `decision-registrar.v1` against v2, or two wordings of a Governor prompt. Run by hand before a real run or after a prompt change, never in pull request CI: it costs calls and needs the key, and the model's answers vary between runs, so results are rates, not pass or fail. This is an evaluation of the model with our prompts; the offline tests check our code, and `scripts/cohere_smoke.py` is the integration check that the API works with our requests. One run per artifact is only a sample: in the 007 spike, a one-line prompt change fixed one artifact and broke another (Miguel and Claude, 2026-10-31). A small step of its own after handoff 007.
- CLI entry point to run the pipeline over a folder (after handoff 007: `process` runs one artifact).
- Release workflow that generates a CycloneDX SBOM and attaches it to the v0.1.0 tag.

## Stretch (v0.1)

- Oracle (query interface): question answering over the registers with citations.

## Later

- Observer (quality control): periodic health and cross-register consistency checks.
- Remaining registrars: issue log, assumption log, change log, lessons learned, stakeholder register; glossary as a minor register.
- Project status summary: a generated Markdown view built from the registers (recent decisions, open risks, open issues, what changed since a given date), like the decision log views. No new register is needed; it is most useful once the risk register and the issue log exist (Miguel and Claude, 2026-10-31).
- Project charter as a register maintained from artifacts: objectives, scope, key stakeholders, success criteria and constraints as records drafted from kickoff meetings and early documents, then updated or superseded as later meetings change them, each change traced to its meeting, so a project manager can ask when the scope changed and why. Agile teams revise the charter more often than waterfall teams, especially in software, so it is not written once and frozen (Miguel, 2026-10-31). Check it against the PMBOK Guide's project charter before designing.
- Register configurator: let a group add a register, or extend one, without writing code, by giving its schema, its definition and its prompt as configuration. Registers mapped to the PMBOK Guide stay faithful to it; the others are labeled as extensions, as the decision log is. Handoff 007 prepares for it (each register's definition is a prompt file named by its spec, and the Governor's prompt is built from them); what is still code per register needs generic defaults: no semantic checks, a plain table view and a standard write rule (Miguel and Claude, 2026-10-31).
- Semantic guardrails with escalation: the Governor (orchestrator) is the first step that reads meaning, so it raises a suspicion (an artifact unrelated to the group's work, for example notes from another team's meeting; an injection attempt; an unusual number of items) and hands the artifact to a separate checker with deterministic and semantic checks, which can hold it for review. The Governor stays simple and the checker grows on its own: a cheap first check that escalates to an expensive one only when needed. Builds on the `held` status (handoff 007); the Sensor's relevance and prompt-injection checks stay deterministic (Miguel and Claude, 2026-10-31).
- Operator actions on held and quarantined artifacts beyond `release`: reject one, or ask the Governor to split a held artifact again. There is no way to split again yet: deleting the work orders file by hand is refused on purpose, since a new Governor run would mix its results with those of the first one (handoff 007).
- Additional domains beyond project management (for example associations or research groups), each as its own set of Registrars and schemas.
- Operator (human in the loop) approval workflow for sensitive changes.
- Operator release workflow beyond the `release` command (review queue, reasons, notifications).
- Chunking long artifacts after Operator approval: evidence quotes must still match the original text, and a decision can span two chunks.
- Document versions: treat an artifact as a new version of an earlier one and process only what changed.
- Format converters (PDF, Word) as a step before the Sensor; the Ledger hashes the original file and stores the extracted text that evidence is checked against.
- Artifact Ledger Markdown view.
- Reprocessing an artifact that produced records, after a prompt change: needs a `correction` change that replaces content and keeps history (update, reaffirmation and supersession all misdescribe it), a way out of `processed`, and reruns in artifact date order.
- Rerunning an artifact whose draft was rejected: done for artifacts that recorded nothing (handoff 006), and since handoff 007 for any run that stopped: `process` runs the work orders that are not recorded yet from `processed` or `failed`, keeping the earlier rejected drafts and records.
- Tune `KA_COMPARATOR_TOP_K` and `KA_COMPARATOR_TOP_N` on the evaluation set, and consider a minimum Rerank score below which candidates are dropped and the draft is classified as new without a Command call (saves calls, but a wrong threshold lets duplicates in).
- Skip Embed when the register has no more active records than K (Rerank can read them all).
- A cheap pre-check that skips drafting for obvious repeats, if reaffirmation drafts become a visible cost in the event log.
- A git-ignored embedding cache next to the records, if the register grows large.
- Automatic repair of an interrupted supersession.
- Supersession of more than one record at once (`relations.supersedes` already allows a list).
- Repair for records left ahead of the work orders file by an interrupted run (today `process` detects it before any call and stops). A Ledger left behind the work orders file is already rebuilt with no call (handoff 007).
- Sensor relevance check and prompt-injection detection.
  - An artifact could contain fake `<work-order>` text inside the artifact block, to steer a Registrar towards another item. Today the safety net is in code: the draft must quote something that matches the real work order (handoff 007).
- Oracle insight feedback loop: Operator-confirmed conclusions from Oracle conversations are saved as new raw artifacts ("insight notes") and re-enter through the Sensor, so there is still one write path.
- Enterprise connectors (Jira, Confluence, Microsoft Teams) as Sensor sources.
- Alternative LLM providers behind the service layer, for example OpenAI as a temporary fallback if the trial key's monthly cap is reached (Miguel, 2026-10-31). Cohere stays the default, and another provider's adapter needs its own schema reduction, like the Cohere one.
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
- Printed validation errors quote model output and artifact text; consider printing paths and checks only, keeping the full messages for the retry prompt.
- Record why an attempt failed when the retry succeeded: today only rejected drafts keep their error paths, so the failed first attempt of DEC-0007's draft (ART-0007) left no trace. Keep its error paths, never the messages, as rejected items do.
- Budget guard: stop a run before it exceeds a call or cost limit (trial keys are capped).
- Governor calls with thinking on dense artifacts take about a minute; consider a higher default KA_LLM_TIMEOUT_SECONDS or a per-agent timeout, decided from the latencies in the event log. Measured in the handoff 007 real run (2026-11-01): two Governor calls on ART-0006 returned nothing within 60 s and 180 s, about 12 minutes apart, then the same request took 18.3 s in a diagnostic and 17.4 s in the run. Governor calls took 17.4 s on ART-0006 (3,383 output tokens), 14.5 s on ART-0007 (4,696) and 2.8 s on ART-0008 (300). The Decision Registrar was slower than the Governor: 8.8 to 27.0 s per draft (1,912 to 2,879 output tokens), the slowest on ART-0007. The Comparator took 0.9 to 3.2 s, Embed and Rerank under 0.21 s each.
- Event log rotation or archiving, if the file grows large.
- A small report that sums calls, units and cost per run, per agent and per artifact from the event log.
- Record reasoning tokens in LLM events: Cohere reports them in `usage.tokens.reasoning_tokens` (seen in the handoff 006 Addendum A diagnostic), but the adapter and the event log do not keep them yet. Needed to measure a thinking token budget.
- Thinking token budget (`token_budget`) for the Registrars and the Comparator, measured on the evaluation set. A smaller budget lowers cost (in the handoff 006 diagnostic, about 1,100 of 1,300 output tokens were reasoning), but if the model runs out of budget mid-reasoning the output may change: the reasoning could spill into the answer again and break the JSON, or the decisions could get worse. Test several budgets over several artifacts, checking that the JSON stays clean and the records stay correct, before lowering the default. This tests how reliable the answers are under different conditions, not only what they cost.
- Retest thinking disabled after each model or SDK upgrade, with several artifacts and the real prompts (a spike, not one call). If the schema is enforced from the first token with thinking disabled, an accepted call could cost about a quarter of today's output tokens; `KA_CHAT_THINKING` switches it without a code change (ADR-0014).
- Prompt v2 candidates for the Decision Registrar, judged on the evaluation set, not on one artifact. All three are addressed in `decision-registrar.v2` (handoff 007); compare v1 and v2 on the same artifacts once the evaluation set exists:
  - `decided_by` listed everyone present instead of the group named in the decision ("the board").
  - `impacts` was a generic summary not supported by the artifact, although the prompt says to omit unsupported fields.
  - Unsupported fields also block updates (handoff 006 real run): the `DEC-0002` draft from ART-0002 filled `rationale` and `alternatives` with content the meeting notes do not state, so when ART-0004 gave the real rationale and the alternative that was set aside, the update had no empty field to fill and kept the invented ones. ART-0004's quotes are in the sources, not in the content.
  - One data point to test, not a conclusion: `DEC-0002` was drafted with thinking disabled and invented both fields; `DEC-0003`, drafted with thinking enabled, left out the alternatives the artifact does not give and named "the board" as `decided_by`. Compare invented fields with thinking on and off on the evaluation set.
- ART-0006 (handoff 007 real run): the Comparator classified a confirmation as an update that filled no field (DEC-0003, fields []). Consider a code rule that records an update filling nothing as a reaffirmation, or a Comparator prompt v2 line; judge on the evaluation set.
- ART-0007 (handoff 007 real run): an update filled DEC-0004's empty decided_on with the date of the tech sync that restated the decision (2026-06-09), not the board meeting that made it (2026-05-26). Candidates, judged on the evaluation set: a Registrar prompt v3 line (decided_on is when the decision was made; a later meeting that restates it gives no date), and a code rule (an update never fills decided_on with the date of a later artifact than the record's first source).

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
- How a Registrar reports that an artifact has nothing to record: decided, it never has to. The Governor sends work orders only for items it found, and an artifact with none is `processed` with zero records (handoff 007, [ADR-0018](../docs/decisions/0018-governor-work-orders.md)).
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

- If writing the views or the work order's result fails after a record is saved, a rerun of `process` is refused because the work orders file is behind the records. The fix is by hand today (`knowledge-automata views`, then the order's state and results in the work orders file); the error could say so step by step.
- `release` does not check the stored copy's hash: a quarantined copy edited in place is released, then refused by `process`. Checking the hash at release would fail sooner, with the same message.
- A crash between writing an artifact copy and its Ledger entry leaves an orphan copy, and the next `ingest` stops on "file exists" for the same ID until the copy is deleted. It fails loudly; the error could say which file to remove.
- The Comparator keeps its own call, check and retry loop; the Registrars and the Governor share `agents/checked_chat.py` (handoff 007, part 7A). Moving the Comparator onto it would remove the duplicate, as long as its tests stay unchanged.
