# Status

## Last updated

2026-10-25

## Current phase

Scaffolding, handoff 001.

## Done

- Package skeleton (`src/knowledge_automata`), `pyproject.toml` (hatchling, ruff, pytest, pip-audit) and a smoke test.
- CI: `test` job (ruff check, ruff format --check, pytest on Python 3.11 and 3.15) and `audit` job (pip-audit). Read-only token, actions pinned to commit SHAs.
- Dependabot for pip and GitHub Actions.
- `AGENTS.md`, pull request template, `README.md`, `SECURITY.md`.
- `docs/architecture.md` (draft v0.1) and ADRs 0001 to 0010.
- Dev process files: this file, `backlog.md`, `principles-in-practice.md`, `tool-feedback.md`.
- Verified locally on Python 3.12: `pip install -e ".[dev]"`, `ruff check`, `ruff format --check`, `pytest` and `pip-audit --skip-editable` all pass.

## In progress

- Pull request from `chore/scaffolding`: Miguel pushes, opens it and checks that CI is green.

## Next

- Handoff 002: Decision and Risk register schemas, PMI-mapped, designed with Claude.

## Blockers

None.

## Notes for the next session

- After the first CI run on the pull request, add the CI jobs as required status checks in the `main` ruleset (they appear as `test (3.11)`, `test (3.15)` and `audit`).
- GitHub settings from handoff 001 Addenda B.1 and C.1 are done by Miguel by hand.
- Python 3.15 is new in CI. If a dev dependency fails to install there, fall back to the newest version that works and log it in `backlog.md` and `tool-feedback.md`.
