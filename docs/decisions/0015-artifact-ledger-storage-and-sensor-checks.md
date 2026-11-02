# 0015. Artifact Ledger storage and Sensor checks

- **Status:** Accepted (amended 2026-10-30: reruns of artifacts that recorded nothing, entry schema 1.1, ADR-0017; amended 2026-11-01: the `held` status, `failed` with results, the work orders file, entry schema 1.2, ADR-0018)
- **Date:** 2026-10-27

## Context

ADR-0006 defines what the Artifact Ledger holds and who owns each status, and ADR-0013 left its storage to be decided with the Sensor (intake and input guardrail). Unlike records, Ledger entries change status over their life. The thin slice (handoff 004) ran with stand-ins: artifact IDs passed by hand, files found by name, and the input checks inside the pipeline. v0.1 accepts plain text and Markdown from files.

## Decision

- Each artifact has one Ledger entry, `ledger/<ID>.json` in the memory folder, validated against `schemas/core/ledger-entry.v1.json` before every write. The entry holds the current status and an append-only history of transitions (when, by whom, why). Only a valid transition may overwrite the file, and earlier history entries never change.
- Allowed transitions: `received` to `accepted`, `quarantined` or `rejected` (Sensor); `quarantined` to `accepted` (Operator release); `accepted` or `failed` to `processed`, `failed` or `held` (Governor); `processed` to `processed`, `failed` or `held` for an artifact whose run recorded nothing, a rerun that carries a reason (amended 2026-10-30, [ADR-0017](0017-comparator-reconciliation.md)); `held` to `accepted` (Operator release, with no Sensor check, since the bytes were already accepted). `rejected` is final, and `processed` is final once it lists records. Transitions written before the Governor existed by the pipeline stand-in (`pipeline`) stay valid in history. Each `processed`, `failed` or `held` step the Governor writes carries its run ID (amended 2026-11-01, [ADR-0018](0018-governor-work-orders.md)).
- A transition raises the entry's `schema_version` to the current minor version of the same major (1.0 entries become 1.1 when they change); an entry of another major version is refused (amended 2026-10-30).
- The content hash is SHA-256 over the bytes with a leading BOM removed and line endings normalized to LF. A file whose hash matches an entry that is not rejected is a duplicate: nothing is written and the existing entry is named.
- A file with the same name as earlier artifacts but different content is a new artifact; its entry lists those artifacts as a fact (`same_name_as`), not as a guessed revision.
- The Sensor's checks are deterministic. Unsupported formats and empty files are rejected. Files that are not UTF-8, larger than a configurable limit (100,000 bytes by default), or that contain the artifact delimiter are quarantined and kept for the Operator (human in the loop).
- `processed` means the pipeline ran to the end, even with zero records; the entry lists the records produced and the drafts rejected, by register, attempts, prompt version and error paths, plus the error type when the last response was unusable. Since entry schema 1.1, each produced item also names its change (new, update, reaffirmation or supersession) and, when a comparison ran, the Comparator's model, prompt version, attempts and candidate scores; each rejected item names its stage (draft or comparison) and run ID (amended 2026-10-30). `failed` is for errors such as a provider error.
- Since entry schema 1.2 (amended 2026-11-01, [ADR-0018](0018-governor-work-orders.md)): each produced and rejected item names its work order; a `governor` block holds the Governor's model, prompt and definition versions, attempts, run ID and the work orders found per register (routed or not). A `failed` entry may list the records an interrupted run produced before the error. Once a run has listed a rejected item, every later transition keeps it, and a later run appends to `produced` and `rejected` without changing what is already there. A `held` entry, and the `accepted` entry after its release, list no records.
- The checked work orders are saved per artifact in `work-orders/<ID>.json`, validated against `schemas/core/work-orders.v1.json` before every write, with each order's state (`pending`, `recorded`, `rejected` or `not-routed`) and its results. The Ledger's lists are rebuilt from that file, so a Ledger left behind it is corrected by the next run with no call.
- The Ledger never holds model output, and holds artifact text only as the title.

## Consequences

- Reruns are idempotent, and every artifact's path through the system can be read in one file.
- Artifacts and records link both ways: records through their sources, Ledger entries through `produced`.
- Writes go record, views, then Ledger, so an interruption leaves the Ledger behind the records, which the pipeline detects. Since ADR-0018 each work order goes records, views, then its result in the work orders file, and the Ledger is written at the end of the run: a Ledger left behind the file is rebuilt with no call, and records ahead of the file are caught before any call and left for a hand correction (amended 2026-11-01).
- Long documents must be released by hand until chunking exists, and other formats wait for converters that run before the Sensor.
- Exact-name matching flags common names such as `notes.md` often; the flag is informational only.
- The Sensor decides from bytes alone and never touches files, because agents do not import storage. The pipeline writes the artifact copies, the work orders files and the Ledger entries for the Sensor and the Governor.
