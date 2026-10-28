# Status

## Last updated

2026-10-26

## Current phase

Handoffs 001 to 004 merged (PR #1 to PR #5). The first slice works end to end: one artifact goes to one validated decision record on a real Command call. Next is the Sensor (intake and input guardrail) and the Artifact Ledger.

## Done

- Handoff 001 scaffold merged as PR #1: package skeleton, CI (ruff, pytest on Python 3.11 and 3.15, pip-audit), Dependabot, `AGENTS.md`, README, `SECURITY.md`, architecture draft, ADRs 0001 to 0010 and the dev process files.
- CI follow-ups merged as PR #2: aggregate `ci-ok` job, now the only required status check in the `main` ruleset; `dev/costs.md`.
- Handoff 002 merged as PR #3:
  - Five JSON Schema files in `schemas/` (record envelope, draft, reconciliation, decision, risk).
  - Validators for records, drafts and Comparator (reconciliation) results, and the evidence quote check.
  - `jsonschema` as the first runtime dependency, `uv.lock`, CI and Dependabot on uv, and a CI `package` job that loads every schema from the built wheel. Python 3.15 passed with the first compiled dependency.
  - ADR-0011 (record model and write rules); ADR-0007 amended to cite the PMBOK Guide, Eighth Edition.
- Planning updates after PR #3 (Miguel and Claude): the design principle "use the LLM only where judgement is needed" in `docs/architecture.md`, the thin vertical slice moved ahead of the Sensor, the Markdown view specification in the backlog, credits recorded as the last commit before merging, and "Cohere notes" at the end of every implementation report.
- Handoff 003 merged as PR #4 (`dev/handoffs/003-llm-service-layer.md`, ADR-0012), with tests:
  - `knowledge_automata.llm`: interfaces, errors, settings (`KA_*` variables, plus `KA_CHAT_THINKING`), the Cohere schema reduction, the Cohere adapter (`cohere` 7.3 SDK), `FakeLLM`, `ObservedLLM` with JSONL and in-memory sinks, the price table and `build_llm`.
  - Event log at `runtime/logs/llm-events.jsonl` (under the existing `/runtime/` ignore rule), validated against `schemas/core/llm-event.v1.json`.
  - `prices.toml` has no Cohere models yet: the pricing page lists no per-token prices for them, so events carry no `cost_usd`.
  - Tests never touch the network (autouse socket block); the adapter is tested against the real SDK through `httpx.MockTransport`.
  - ADR-0012, architecture, README, backlog and logs updated; `dev/handoffs` excluded from `ruff format`, which formats Python blocks inside Markdown.
  - Addendum A: every event carries `schema_version` and a `run_id` grouping the calls of one run, plus the provider's `request_id` and raw token counts when reported. The event log is append-only.
  - Smoke check (`uv run --env-file .env python scripts/cohere_smoke.py`), run twice with Miguel's approval on 2026-10-25, 0 failed checks both times. The second run (7 calls, after Addendum A) wrote 7 valid events sharing one `run_id`, each with `schema_version` 1.0 and a `request_id`; raw token counts appeared on the chat events only.
    - Structured output: the vermilion test was enforced under both `response_format` field names, `schema` and `json_schema`. SDK 7.3 logs an "experimental feature" warning for `schema` only, so the adapter now sends `json_schema`, the name in the API reference and the SDK.
    - Thinking on versus off for the same decision draft: about 6x billed output tokens (1,320 versus 223, then 1,256 versus 223) and the same `validate_draft` result (passed). Latency was 6.3x in the first run (10.1 s versus 1.6 s) but only 1.6x in the second (3.9 s versus 2.4 s), so latency varies. One artifact only: handoff 004 chooses the default and checks quality on the sample project.
    - Chat raw token counts differ from billed ones: raw input 117 versus 12 billed for the colour test and 728 versus 256 for the draft; raw output is billed output plus 3 to 4.
    - Embed (`embed-v5.0-fast`): 2,048 dimensions, 23 and 5 billed input tokens. Rerank (`rerank-v5.0-pro`): correct order (0.6867 for the matching document), billed as 39 input tokens, not search units.
    - The SDK raises a Pydantic `__fields__` deprecation warning (`PydanticDeprecatedSince20`, in `cohere/core/unchecked_base_model.py`) while parsing responses; harmless now, but it will break with Pydantic 3.
- Handoff 004 merged as PR #5 (`dev/handoffs/004-decision-slice.md`, ADR-0013, ADR-0014), with tests (415 passing, every LLM call mocked):
  - Prompt files packaged in the wheel and loaded by `core/prompts.py`; CI's `package` job loads every prompt from the installed wheel.
  - `core/records.py` (envelope builder) and `storage/record_store.py`: one JSON file per record in a memory folder, validated before it is written, written atomically, never overwritten, deterministic formatting (ADR-0013).
  - `agents/registrar.py`: one drafting loop for every Registrar (specialist record keeper), with one retry from the versioned retry prompt; the record history cites `decision-registrar.v1+registrar-retry.v1` when the retry was used (ADR-0014).
  - `views/markdown.py` and the decision log view: an index and one page per decision, checked against hand-written fixtures; CI runs `knowledge-automata views --memory examples/sample-project --check`.
  - `pipeline.py` (a temporary stand-in for the Artifact Ledger) and `cli.py`: `knowledge-automata record-decision` and `knowledge-automata views [--check]`, with exit codes 0, 1 (rejected or stale views), 2 (usage, configuration or file problem) and 3 (provider error). Thinking is disabled for the Decision Registrar unless `KA_CHAT_THINKING` is set.
  - ADR-0013 and ADR-0014, architecture "Storage and views", README "Try it", sample project README, backlog.
- The real run, with Miguel's approval on 2026-10-26 (run `98ebfd14-8f1a-4937-961f-242554938b23`, `command-a-plus-05-2026`, thinking disabled): `DEC-0001` recorded from `ART-0001` in 2 attempts and committed unedited with its views.
  - Attempt 1 (`decision-registrar.v1`): `LLMResponseError` (unusable response) after 10.3 s, billed 697 input and 2,390 output tokens. That is more output than thinking enabled used in the smoke check (about 1,300). The cause is unknown, because events record only the error type.
  - Attempt 2 (`decision-registrar.v1+registrar-retry.v1`): accepted after 2.1 s, billed 756 input and 322 output tokens.
  - Total: 1,453 input and 2,712 output billed tokens; about 15 s for the whole command.
  - Against handoff section 5: statement, rationale, alternatives, date and context match; the QR codes, the offline-sync risk and the actions were left out; the decision quote comes first, and quotes wrapped across lines passed the evidence check. Miguel accepted the record as is. Quality notes for a future `decision-registrar.v2`, to be judged on the evaluation set: `decided_by` listed everyone present instead of the group named in the decision ("the board"), and `impacts` is a generic summary not supported by the artifact, although the prompt says to omit unsupported fields. No evidence quote contains the artifact's typographic apostrophe, so that case was not exercised.
- README pass before the Cohere application (Miguel and Claude, 2026-10-26): a "See it working" link to `DEC-0001`, Status moved up with what works and what is next, a "Design principles" section, built versus planned roles in "How it works", and American spelling.

## In progress

None.

## Next

- The Sensor (intake and input guardrail) and the Artifact Ledger, replacing the stand-ins in `pipeline.py` (artifact ID and date by hand, artifacts found by name).
- Then the Comparator, the Governor (orchestrator), the Risk Registrar, the sample project as an evaluation set, and the v0.1.0 release (see `dev/backlog.md`).

## Blockers

None.

## Notes for the next session

- The sample record is evidence: never rerun the real call to get a nicer `DEC-0001`. Prompt changes are new version files (`decision-registrar.v2`) judged on the evaluation set.
- Line endings: `core.autocrlf` is on for this clone, so committed text may be CRLF in the working tree. The record store and views always write LF, `views --check` ignores CRLF versus LF, and `read_artifact` normalizes line endings before the evidence check. The Sensor's content hashes must do the same (backlog, *Open questions*).
- Local checks: `uv sync --all-extras` (a plain `uv sync` removes ruff and pytest), then `uv run ruff check`, `uv run ruff format --check`, `uv run pytest`, and `uv run knowledge-automata views --memory examples/sample-project --check`.
- Python 3.15: the Cohere SDK pulls in PyYAML, which has no 3.15 wheel yet and builds from source. If a dependency fails to install on 3.15 in CI, stop and report it; do not drop 3.15 without Miguel's approval.
- Trial keys are rate limited and capped at 1,000 calls a month, so real calls (smoke checks, evaluation runs) are budgeted. The key lives only in `.env` as `CO_API_KEY` (never committed).
- If a default model stops working (not available to trial keys, no structured-output support, or errors), log why in `dev/tool-feedback.md`, fall back to the previous version (`command-a-03-2025`, `embed-v4.0`, `rerank-v4.0-pro` or `rerank-v3.5`) and record it here. Only if no Cohere model works for a role, ask Miguel (handoff 003 Addendum A).
- Record each pull request's Copilot credits in `dev/costs.md` as the last commit on its branch, before merging. The rows for PR #4 and PR #5 were added after their merges.
- When squash merging, copy the `Co-authored-by:` trailers from the code block in `AGENTS.md` (Commit conventions). In PR #4 they were indented, and in PR #5 the Claude address became a Markdown link and the Copilot line was missing, so GitHub may not credit the co-authors on those two commits.
- Local setup: `uv sync --all-extras`, then `uv run pytest`. Keep the clone outside cloud-synced folders (see README).
