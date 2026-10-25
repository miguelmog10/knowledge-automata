# 0002. Clean-room rebuild

- **Status:** Accepted
- **Date:** 2026-10-24

## Context

The author's earlier course project, Chronicle, explored similar ideas. Its review showed both useful lessons and structural gaps.

## Decision

Build Knowledge Automata from scratch. Port zero files from Chronicle. Carry forward only learnings, recorded as decisions.

Learnings carried forward:

- Keep planning separate from writing.
- Inject the LLM client so tests run without network calls.
- Combine deterministic and LLM-based quality checks.
- Maintain traceability to source artifacts.
- Keep prompts as files.
- Keep a status file for session handoff.

Gaps fixed by design:

- Specialists lacked context of existing records, causing duplicates (fixed by the Comparator, ADR-0004).
- Free-form Markdown was the source of truth (fixed by validated records, ADR-0005).
- The LLM generated IDs (code assigns them, ADR-0005).
- The provider was coupled to the code (fixed by the service layer, ADR-0003).
- Schemas overlapped.

## Consequences

- Clear ownership and a clean history.
- Applies the principle "reuse what compounds, delete what doesn't" (P16).
- No file from the Chronicle repository may be opened, read or copied while working on this repo.
