# 0005. Validated structured records as the source of truth

- **Status:** Accepted (storage backend details to be refined when the first register is built)
- **Date:** 2026-10-24

## Context

LLM output can be malformed or inconsistent. Free-form text as the source of truth makes records hard to validate, audit and query.

## Decision

- Records are stored as structured data (JSON) validated against versioned schemas.
- Markdown views are generated from the records, never edited as the source.
- LLM output must pass schema validation before storage; invalid output is retried or rejected.
- Code assigns record IDs, never the LLM.

## Consequences

- Malformed output cannot enter the institutional memory.
- Most structural audits become unnecessary.
- Storage is git-friendly.
- The storage layout (JSON files per record, one file per register, or SQLite) is still open; see `dev/backlog.md`.
