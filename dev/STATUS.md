# Status

## Last updated

2026-10-25

## Current phase

Handoffs 001 and 002 merged (PR #1 to PR #3). Handoff 003 (LLM service layer and Cohere adapter) is implemented on `feat/llm-service-layer`; the smoke check against the real API is pending Miguel's go-ahead.

## Done

- Handoff 001 scaffold merged as PR #1: package skeleton, CI (ruff, pytest on Python 3.11 and 3.15, pip-audit), Dependabot, `AGENTS.md`, README, `SECURITY.md`, architecture draft, ADRs 0001 to 0010 and the dev process files.
- CI follow-ups merged as PR #2: aggregate `ci-ok` job, now the only required status check in the `main` ruleset; `dev/costs.md`.
- Handoff 002 merged as PR #3:
  - Five JSON Schema files in `schemas/` (record envelope, draft, reconciliation, decision, risk).
  - Validators for records, drafts and Comparator (reconciliation) results, and the evidence quote check.
  - `jsonschema` as the first runtime dependency, `uv.lock`, CI and Dependabot on uv, and a CI `package` job that loads every schema from the built wheel. Python 3.15 passed with the first compiled dependency.
  - ADR-0011 (record model and write rules); ADR-0007 amended to cite the PMBOK Guide, Eighth Edition.
- Planning updates after PR #3 (Miguel and Claude): the design principle "use the LLM only where judgement is needed" in `docs/architecture.md`, the thin vertical slice moved ahead of the Sensor, the Markdown view specification in the backlog, credits recorded as the last commit before merging, and "Cohere notes" at the end of every implementation report.

## In progress

- Handoff 003 on `feat/llm-service-layer` (`dev/handoffs/003-llm-service-layer.md`), implemented with tests:
  - `knowledge_automata.llm`: interfaces, errors, settings (`KA_*` variables, plus `KA_CHAT_THINKING`), the Cohere schema reduction, the Cohere adapter (`cohere` 7.3 SDK), `FakeLLM`, `ObservedLLM` with JSONL and in-memory sinks, the price table and `build_llm`.
  - Event log at `runtime/logs/llm-events.jsonl` (under the existing `/runtime/` ignore rule), validated against `schemas/core/llm-event.v1.json`.
  - `prices.toml` has no Cohere models yet: the pricing page lists no per-token prices for them, so events carry no `cost_usd`.
  - Tests never touch the network (autouse socket block); the adapter is tested against the real SDK through `httpx.MockTransport`.
  - ADR-0012, architecture, README, backlog and logs updated; `dev/handoffs` excluded from `ruff format`, which formats Python blocks inside Markdown.
  - Remaining: the smoke check (`uv run --env-file .env python scripts/cohere_smoke.py`), run only with Miguel's approval, with thinking enabled and disabled so handoff 004 can choose the default.

## Next

- Handoff 004, the thin vertical slice: one sample artifact through the Decision Registrar (specialist record keeper) to one validated, stored decision record on a real Command call. It comes before the Sensor (intake and input guardrail) so the Cohere path is proven end to end early.
- Then the Sensor and Artifact Ledger, the Comparator, the Governor (orchestrator), the Risk Registrar, the sample project and CLI, and the v0.1.0 release (see `dev/backlog.md`).

## Blockers

None.

## Notes for the next session

- Python 3.15: the Cohere SDK pulls in PyYAML, which has no 3.15 wheel yet and builds from source. If a dependency fails to install on 3.15 in CI, stop and report it; do not drop 3.15 without Miguel's approval.
- Trial keys are rate limited and capped at 1,000 calls a month, so real calls (smoke checks, evaluation runs) are budgeted. The key lives only in `.env` as `CO_API_KEY` (never committed).
- If a default model stops working (not available to trial keys, no structured-output support, or errors), log why in `dev/tool-feedback.md`, fall back to the previous version (`command-a-03-2025`, `embed-v4.0`, `rerank-v4.0-pro` or `rerank-v3.5`) and record it here. Only if no Cohere model works for a role, ask Miguel (handoff 003 Addendum A).
- Record each pull request's Copilot credits in `dev/costs.md` as the last commit on its branch, before merging.
- Local setup: `uv sync --all-extras`, then `uv run pytest`. Keep the clone outside cloud-synced folders (see README).
