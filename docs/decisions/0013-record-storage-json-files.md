# 0013. Record storage: one JSON file per record

- **Status:** Accepted
- **Date:** 2026-10-26

## Context

Records need durable storage from the first slice (handoff 004). The backlog listed three options: one JSON file per record, one file per register, or SQLite. The repository is public, and the sample project's records are meant to be read and reviewed on GitHub. v0.1 has one writing process and small registers.

## Decision

- Each record is one JSON file, `registers/<register>/<ID>.json`, inside a memory folder that holds the institutional memory of one group. The memory folder is a parameter: the default, `runtime/memory`, is git-ignored, and the sample project uses `examples/sample-project`.
- Code validates every record (envelope and content) before writing it. An invalid record is never written.
- A new record is written to a temporary file and moved into place. A new record never overwrites an existing file; revisions arrive with the Comparator (reconciliation).
- The next ID is the highest existing sequence in the register plus one. Records are never deleted (a change of substance supersedes them), so IDs are not reused.
- Files are written deterministically (UTF-8, LF line endings, two-space indentation, fixed key order), so diffs show only real changes.
- Markdown views are generated from the files and never edited by hand.
- One writing process at a time is assumed.

## Consequences

- Records are plain files that can be read, diffed and reviewed one by one, with no database.
- Finding the next ID, or the records that cite an artifact, means reading the register folder. That is fine at v0.1 scale; an index can come later.
- There are no transactions across files. A supersession changes two files, so the Comparator handoff must order the writes so that an interruption leaves a state that can be detected and repaired.
- Concurrent writers could clash on IDs; a lock or SQLite is the path if that becomes real.
- The Artifact Ledger's storage is decided with the Sensor (intake and input guardrail).
