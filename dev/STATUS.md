# Status

## Last updated

2026-10-25

## Current phase

Scaffolding and CI follow-ups merged (PR #1 and PR #2). Handoff 002 (Decision log and Risk register schemas) is in design with Claude.

## Done

- Handoff 001 scaffold merged to `main` as PR #1:
  - Package skeleton (`src/knowledge_automata`), `pyproject.toml` (hatchling, ruff, pytest, pip-audit) and a smoke test.
  - CI: `test` job (ruff check, ruff format --check, pytest on Python 3.11 and 3.15) and `audit` job (pip-audit). Read-only token, actions pinned to commit SHAs.
  - Dependabot for pip and GitHub Actions.
  - `AGENTS.md`, pull request template, `README.md`, `SECURITY.md`.
  - `docs/architecture.md` (draft v0.1) and ADRs 0001 to 0010.
  - Dev process files: this file, `backlog.md`, `principles-in-practice.md`, `tool-feedback.md`.
- CI and handoff 001 follow-ups merged to `main` as PR #2 (from `ci/required-check`):
  - Aggregate `ci-ok` job that fails unless `test` and `audit` both succeeded.
  - ADR-0002 names the fix for overlapping schemas.
  - README links to the principles on `main`.
  - Definition of done and PR checklist include README updates for user-visible changes.
  - `dev/costs.md` for Copilot credits per pull request.

## In progress

- Handoff 002: Decision log and Risk register schemas, PMI-mapped. Design agreed between Miguel and Claude; handoff written in `dev/handoffs/002-register-schemas.md`.

## Next

- Copilot plans and implements handoff 002 on `feat/register-schemas`.
- LLM service layer with a Cohere adapter and a fake adapter for tests.

## Blockers

None.

## Notes for the next session

- Add `ci-ok` as the only required status check in the `main` ruleset, if not done yet (it has now run on PR #2).
- Python 3.15 is new in CI. If a dependency fails to install there, fall back to the newest version that works and log it in `backlog.md` and `tool-feedback.md`. The first runtime dependency with compiled wheels (expected in handoff 002) is the first real test.
