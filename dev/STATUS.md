# Status

## Last updated

2026-10-25

## Current phase

Handoffs 001 and 002 merged (PR #1 to PR #3). Handoff 003 (LLM service layer and Cohere adapter) is ready for Copilot on `feat/llm-service-layer`.

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

- Handoff 003: LLM service layer, Cohere adapter, fake adapter, event log and price table (`dev/handoffs/003-llm-service-layer.md`).

## Next

- Handoff 004, the thin vertical slice: one sample artifact through the Decision Registrar (specialist record keeper) to one validated, stored decision record on a real Command call. It comes before the Sensor (intake and input guardrail) so the Cohere path is proven end to end early.
- Then the Sensor and Artifact Ledger, the Comparator, the Governor (orchestrator), the Risk Registrar, the sample project and CLI, and the v0.1.0 release (see `dev/backlog.md`).

## Blockers

None.

## Notes for the next session

- Before Copilot runs the smoke check in handoff 003, Miguel creates a Cohere trial API key and puts it in `.env` as `CO_API_KEY` (never committed). Trial keys are rate limited and reportedly capped at about 1,000 calls a month, so real calls are budgeted.
- Record each pull request's Copilot credits in `dev/costs.md` as the last commit on its branch, before merging.
- Local setup: `uv sync --all-extras`, then `uv run pytest`. Keep the clone outside cloud-synced folders (see README).
