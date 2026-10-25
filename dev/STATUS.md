# Status

## Last updated

2026-10-25

## Current phase

Handoff 002 (Decision log and Risk register schemas) implemented on `feat/register-schemas`, ready for Miguel to open the pull request.

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
- Handoff 002 on `feat/register-schemas` (not merged yet):
  - Five JSON Schema files in `schemas/` (record envelope, draft, reconciliation, decision, risk), revised after Copilot's plan review.
  - `jsonschema` as the first runtime dependency, `uv.lock`, CI and Dependabot switched to uv, README setup uses `uv sync`.
  - Schema files packaged into the wheel; new CI `package` job builds the wheel and loads every schema from it; `ci-ok` now also needs `package`.
  - Core: register specs, schema loading, evidence quote check, record, draft and reconciliation validators (RFC 3339 `date-time` with a timezone). Project-management domain: decision log and risk register specs.
  - ADR-0011 (record model and write rules); ADR-0007 amended to cite the PMBOK Guide, Eighth Edition.

## In progress

- Pull request for handoff 002 (Miguel opens, reviews and merges).

## Next

- LLM service layer with a Cohere adapter and a fake adapter for tests. The adapter removes validation-only keywords and annotations before sending a schema (ADR-0011).
- Check the Cohere `response_format` field name (`schema` in the guide, `json_schema` in the API reference) with a real call when the adapter is built.

## Blockers

None.

## Notes for the next session

- Add `ci-ok` as the only required status check in the `main` ruleset, if not done yet (it has now run on PR #2).
- Check the first CI run of the handoff 002 PR: the new `package` job, the uv-based `audit` job, and the first compiled runtime dependency (`rpds-py`, via `jsonschema`) on Python 3.15. If 3.15 fails, fall back to the newest version that works and log it in `backlog.md` and `tool-feedback.md`.
- Local setup is now `uv sync --all-extras`; after changing dependencies in `pyproject.toml`, run `uv lock` and commit `uv.lock`.
