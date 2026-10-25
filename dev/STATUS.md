# Status

## Last updated

2026-10-25

## Current phase

Scaffolding complete (handoff 001, PR #1 merged). Small follow-up on `ci/required-check` before handoff 002.

## Done

- Handoff 001 scaffold merged to `main` as PR #1:
  - Package skeleton (`src/knowledge_automata`), `pyproject.toml` (hatchling, ruff, pytest, pip-audit) and a smoke test.
  - CI: `test` job (ruff check, ruff format --check, pytest on Python 3.11 and 3.15) and `audit` job (pip-audit). Read-only token, actions pinned to commit SHAs.
  - Dependabot for pip and GitHub Actions.
  - `AGENTS.md`, pull request template, `README.md`, `SECURITY.md`.
  - `docs/architecture.md` (draft v0.1) and ADRs 0001 to 0010.
  - Dev process files: this file, `backlog.md`, `principles-in-practice.md`, `tool-feedback.md`.
- On `ci/required-check`:
  - Aggregate `ci-ok` job that fails unless `test` and `audit` both succeeded.
  - ADR-0002 names the fix for overlapping schemas.
  - README links to the principles on `main`.
  - Definition of done and PR checklist include README updates for user-visible changes.
  - `dev/costs.md` for Copilot credits per pull request.

## In progress

- Pull request from `ci/required-check`: Miguel pushes, opens it and checks that CI is green.

## Next

- Handoff 002: Decision and Risk register schemas, PMI-mapped, designed with Claude.

## Blockers

None.

## Notes for the next session

- Add `ci-ok` as the only required status check in the `main` ruleset after the first CI run on the `ci/required-check` pull request.
- Fill in `dev/costs.md` for PR #1 and the `ci/required-check` pull request.
- Python 3.15 is new in CI. If a dev dependency fails to install there, fall back to the newest version that works and log it in `backlog.md` and `tool-feedback.md`.
