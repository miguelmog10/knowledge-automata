# Handoff 005: the Sensor and the Artifact Ledger

- **From:** Claude (discovery, architecture, review)
- **To:** Copilot (implementation)
- **Owner and approver:** Miguel
- **Date:** 2026-10-27
- **Branch:** `feat/sensor-ledger`
- **Scope:** the Sensor (intake and input guardrail) with deterministic checks, the Artifact Ledger stored as one JSON file per artifact, a manual quarantine release for the Operator (human in the loop), `record-decision` driven by the Ledger instead of hand-passed IDs, and two diagnostic fields in LLM events (`finish_reason` and the error message). No Governor, Comparator, chunking or format converters.

---

## 1. Context

Handoff 004 (PR #5) proved one artifact to one validated decision record on a real Command call. It did so with stand-ins in `pipeline.py`: the caller passes the artifact ID and date, artifact files are found by name in `<memory>/artifacts/`, rerunning is refused by scanning records, and `read_artifact` does the Sensor's checks inline. This handoff replaces those stand-ins with the Sensor and the Ledger described in ADR-0006 and `docs/architecture.md` (data flow, step 1).

It also closes a gap from the real run: attempt 1 failed with `LLMResponseError` after 2,390 output tokens, and the cause is unknown because events record only the error type. The adapter already builds a message that says why (for example `finish_reason MAX_TOKENS`, or the JSON error position); it is just never logged.

What already exists and must be reused, not rebuilt:

- `pipeline.read_artifact` and `validate_artifact_arguments`: UTF-8 with a tolerated BOM, line endings to LF, the date check. The Sensor takes this logic over.
- `agents/registrar.check_artifact`: the `</artifact` delimiter check. It stays in the Registrar as defense in depth, and the Sensor runs the same check at intake.
- `storage/record_store.py`: deterministic formatting (`format_record`) and the temporary-file-then-`os.replace` write. The Ledger store uses the same rules (6.5).
- `core/validation.py` and `core/schemas.py`: schema loading and validation patterns for the new Ledger entry schema.
- `llm/observed.py`, `llm/errors.py`, `llm/cohere_adapter.py`: the event pipeline that gains two optional fields.

Read `AGENTS.md`, `dev/STATUS.md`, ADR-0006, ADR-0011, ADR-0012, ADR-0013, ADR-0014 and `docs/architecture.md` before planning.

**What Miguel and Claude decided for this handoff (2026-10-27):**

1. **Ledger storage:** one JSON file per artifact, `<memory>/ledger/ART-0001.json`, consistent with records (ADR-0013) and readable on GitHub. Each file holds the current status plus an **append-only history** of every transition, with when, who and why. An artifact changes status three or four times in its life, so the history stays small, and it shows exactly what happened when an artifact is reprocessed after a prompt change.
2. **Duplicates:** exact content only. The content hash is SHA-256 over the bytes after line endings are normalized (6.2), so a Windows copy and a Linux copy of the same file are the same artifact. File names play no part in duplicate detection.
3. **Same file name, different content:** a new artifact. Its entry records the fact, `same_name_as: ["ART-0003"]`, and makes no guess about whether it is a revision: a name like `notes.md` may arrive a hundred times in a project's life. Exact name match only; "similar" names would need fuzzy matching, which is judgement.
4. **Formats:** plain text and Markdown only. PDF and Word converters come later, as a separate step before the Sensor, so the Sensor stays a simple gatekeeper (backlog).
5. **Encoding:** UTF-8 only. A byte order mark is removed if present. Anything that does not decode is quarantined.
6. **Oversized:** a configurable limit, 100,000 bytes by default (about 15,000 words, a very long meeting transcript). An oversized artifact is **quarantined, not rejected**, so nothing is lost: the Operator (human in the loop) reviews it and releases it by hand (6.7). Splitting long documents into chunks after approval is not trivial (a decision can span two chunks, and evidence quotes must still match the original text), so it goes to the backlog.
7. **Final status:** `processed` means the pipeline ran to the end, even with zero records, and the entry lists what was produced and what was rejected. `failed` is only for real errors, such as a provider error.
8. **Who sets `processed` and `failed`:** ADR-0006 gives this to the Governor (orchestrator), which is not built yet. Until it is, the pipeline stand-in sets them, and history entries say so (`by: "pipeline"`).
9. **Event diagnostics:** LLM events gain optional `finish_reason` and `error_message` fields, so the event schema moves to version 1.1. The error message is the project exception's message, never model output or artifact text, so the log stays metadata only.

**Claude's proposals inside that frame (Miguel confirms them when he approves the plan):**

- A duplicate is a no-op: no new ID and no new entry, and the command names the existing artifact. This is what makes reruns idempotent (ADR-0006). Only entries that are not `rejected` count, so a rejected file can be ingested again later (for example once converters exist).
- The Ledger lists a rejected draft by its register, attempts, prompt version and the JSON paths of its errors (for example `$.evidence[1]`), not the full error messages. Evidence errors quote the model's draft, which failed the check, so storing them would put unvalidated model text in the institutional memory. The full errors are still printed to the terminal, as today.
- Unsupported formats and empty files are `rejected` (nothing to review) and no copy is kept. Encoding failures, oversized files and the delimiter check are `quarantined`, and a copy is kept for the Operator.

**Already committed by Miguel on this branch:** this handoff and the 2026-10-27 entries in `dev/principles-in-practice.md`. Do not modify them. If you find a problem in this handoff, raise it in your plan.

## 2. How to work on this task

1. **Plan first.** Read this whole document, then reply with a short plan: files to create or change, anything here that does not fit the existing code, and the commit sequence. **Wait for Miguel's approval** before writing files.
2. Implement in small commits (section 9), with tests in the same commit as the code they cover.
3. **No test may call the network.** This handoff needs no real Command call (7).
4. If anything here is ambiguous or seems wrong, ask instead of guessing, and add it to `dev/backlog.md` under *Open questions*.
5. Finish by updating `dev/STATUS.md` and reporting what you did, ending with the **Cohere notes** section required by `AGENTS.md`.

## 3. Agreed design

### 3.1 The flow

```
file ──► Sensor ──┬─► duplicate of a live entry: no-op, names ART-0003
 (any    (code)   ├─► rejected   (unsupported format, empty)           ledger entry, no copy
  path)           ├─► quarantined (encoding, oversized, delimiter)     ledger entry + copy ──► Operator release ──► accepted
                  └─► accepted                                         ledger entry + copy
                                                                              │
record-decision ART-0002 ◄────────────────────────────────────────────────────┘
   └─► Decision Registrar (unchanged) ──► processed (records produced, drafts rejected) or failed (provider error)
```

Two commands, two steps: `ingest` runs the Sensor, `record-decision` processes one accepted artifact. A command that runs the whole pipeline over a folder comes with the Governor.

### 3.2 Status transitions

ADR-0006 defines the statuses. The allowed transitions, each with one owner:

| From | To | By | When |
|---|---|---|---|
| (none) | `received` | `sensor` | The file arrives. Written together with the next transition. |
| `received` | `accepted`, `quarantined` or `rejected` | `sensor` | After the checks (6.3). |
| `quarantined` | `accepted` | `operator` | `knowledge-automata release` (6.7). |
| `accepted` | `processed` or `failed` | `pipeline` (later `governor`) | After `record-decision`. |
| `failed` | `processed` or `failed` | `pipeline` (later `governor`) | A rerun after a provider error. |

`rejected` and `processed` are final in v0.1. Reprocessing a `processed` artifact (after a prompt change) comes with the Comparator, which is what makes it safe.

### 3.3 Deterministic, like the rest

Following the design principle, everything in this handoff is code: hashing, checks, IDs, transitions and file writes. No LLM call is added. Relevance and prompt-injection checks stay in the backlog.

### 3.4 The Ledger links both ways

Records already link back to artifacts through `sources`. The Ledger entry links forward through `produced` (ADR-0006, P4). The views now find artifact files through the Ledger (`stored_path`) instead of the file-name convention, and `scan_artifacts` is removed.

### 3.5 Memory folder layout

```
<memory>/
  artifacts/ART-0001-project-board-2026-02-03.md   copies of accepted and quarantined artifacts (read-only)
  ledger/ART-0001.json                             one Ledger entry per artifact (new)
  registers/decision-log/DEC-0001.json
  views/decision-log.md
  views/decision-log/DEC-0001.md
```

## 4. Target structure

New and changed files (existing files not shown):

```
schemas/core/ledger-entry.v1.json          # new: Ledger entry schema (6.1)
schemas/core/llm-event.v1.json             # x-version 1.1: finish_reason, error_message (6.9)
src/knowledge_automata/
  agents/sensor.py                         # new: intake checks, hashing, copy, first transitions
  core/ledger.py                           # new: entry builder and transition rules (pure functions)
  core/schemas.py                          # LEDGER_ENTRY_SCHEMA constant
  core/validation.py                       # validate_ledger_entry
  storage/json_files.py                    # new: shared deterministic JSON format and atomic write
  storage/record_store.py                  # uses json_files (record bytes unchanged)
  storage/ledger_store.py                  # new: one JSON file per Ledger entry
  pipeline.py                              # record_decision by artifact ID; stand-ins removed
  cli.py                                   # ingest, release, ledger; record-decision takes an ID
  llm/errors.py                            # LLMResponseError.finish_reason
  llm/cohere_adapter.py                    # passes finish_reason into LLMResponseError
  llm/observed.py                          # writes finish_reason and error_message
examples/sample-project/ledger/ART-0001.json   # backfilled entry for the existing artifact (8)
tests/
  test_sensor.py, test_ledger.py, test_ledger_store.py, test_json_files.py
  test_pipeline.py, test_cli.py, llm/test_observed_llm.py, llm/test_cohere_adapter.py   # extended
docs/decisions/0015-artifact-ledger-storage-and-sensor-checks.md
.env.example                               # KA_SENSOR_MAX_BYTES
```

## 5. Examples

An accepted artifact, after processing (field order follows the schema):

```json
{
  "schema_version": "1.0",
  "id": "ART-0002",
  "title": "Tallyleaf greenhouse inventory app: pilot review",
  "source": { "type": "file", "name": "pilot-review.md" },
  "artifact_date": "2026-03-02",
  "media_type": "text/markdown",
  "size_bytes": 2048,
  "content_hash": "sha256:9f2c...",
  "stored_path": "artifacts/ART-0002-pilot-review.md",
  "status": "processed",
  "created_at": "2026-10-28T14:00:00Z",
  "updated_at": "2026-10-28T14:00:20Z",
  "produced": [
    {
      "register": "decision-log",
      "record_id": "DEC-0002",
      "model": "command-a-plus-05-2026",
      "prompt_version": "decision-registrar.v1",
      "schema_version": "1.0"
    }
  ],
  "rejected": [],
  "history": [
    { "at": "2026-10-28T14:00:00Z", "status": "received", "by": "sensor" },
    { "at": "2026-10-28T14:00:00Z", "status": "accepted", "by": "sensor" },
    { "at": "2026-10-28T14:00:20Z", "status": "processed", "by": "pipeline", "run_id": "1b9e..." }
  ]
}
```

A quarantined artifact with the same file name as an earlier one:

```json
{
  "schema_version": "1.0",
  "id": "ART-0005",
  "title": "notes",
  "source": { "type": "file", "name": "notes.md" },
  "media_type": "text/markdown",
  "size_bytes": 182340,
  "content_hash": "sha256:41ab...",
  "stored_path": "artifacts/ART-0005-notes.md",
  "same_name_as": ["ART-0003"],
  "status": "quarantined",
  "created_at": "2026-10-28T15:10:00Z",
  "updated_at": "2026-10-28T15:10:00Z",
  "produced": [],
  "rejected": [],
  "history": [
    { "at": "2026-10-28T15:10:00Z", "status": "received", "by": "sensor" },
    {
      "at": "2026-10-28T15:10:00Z",
      "status": "quarantined",
      "by": "sensor",
      "check": "oversized",
      "reason": "182,340 bytes; the limit is 100,000 (KA_SENSOR_MAX_BYTES)"
    }
  ]
}
```

## 6. Code requirements

### 6.1 Ledger entry schema (`schemas/core/ledger-entry.v1.json`)

JSON Schema 2020-12, `x-version` `1.0`, `additionalProperties: false` at every level, following the style of `record.v1.json`. Every property is required except `artifact_date`, `media_type`, `stored_path` and `same_name_as`, so `produced` and `rejected` are always present, empty until processing. Properties, in this order:

- `schema_version` (`MAJOR.MINOR` pattern), `id` (`^ART-[0-9]{4,}$`).
- `title`: string, 1 to 200 characters.
- `source`: object with `type` (enum `["file"]` in v0.1; connectors add values later) and `name` (the original file name only, never a full path, because paths can reveal the owner's folders and the sample project is public).
- `artifact_date`: optional, `format: date`.
- `media_type`: enum `["text/markdown", "text/plain"]`; optional, absent when the format is unsupported.
- `size_bytes`: integer, minimum 0, of the file as received.
- `content_hash`: `^sha256:[0-9a-f]{64}$`.
- `stored_path`: optional, relative POSIX path inside the memory folder, starting with `artifacts/`. Present for `accepted`, `quarantined`, `processed` and `failed`; absent for `rejected`.
- `same_name_as`: optional, non-empty array of unique artifact IDs, in ascending order.
- `status`: enum of the six ADR-0006 statuses.
- `created_at`, `updated_at`: `format: date-time`, `YYYY-MM-DDTHH:MM:SSZ` as in records.
- `produced`: array of `{register, record_id, model, prompt_version, schema_version}`.
- `rejected`: array of `{register, attempts, prompt_version, error_paths}`, where `error_paths` is a non-empty array of unique JSON paths (`^\$`).
- `history`: non-empty array of `{at, status, by, check?, reason?, run_id?, error_type?}`. `by` is an enum: `sensor`, `operator`, `pipeline`, `governor` (reserved). `check` is an enum: `unsupported-format`, `empty`, `encoding`, `oversized`, `delimiter`. `reason` is text written by code (1 to 500 characters), never artifact text or model output.

Semantic checks in `validate_ledger_entry` (beyond the schema), returning errors like the record validators:

- `status` equals the last history entry's status, and `updated_at` equals its `at`.
- The history is a valid path through 3.2: it starts with `received` by `sensor`, and each step is an allowed transition with the right owner.
- `stored_path` presence matches the status rule above.
- `produced` and `rejected` are empty unless the status is `processed`; a `failed` history entry has an `error_type`; a `processed` or `failed` entry has a `run_id`.

### 6.2 Content hash and line endings

`content_hash(raw: bytes) -> str`, in `agents/sensor.py`:

1. Remove a leading UTF-8 BOM (`b"\xef\xbb\xbf"`).
2. Replace `b"\r\n"` with `b"\n"`, then any remaining `b"\r"` with `b"\n"`.
3. Return `"sha256:" + hashlib.sha256(result).hexdigest()`.

It works on bytes, so it hashes undecodable files too. Tests: the same text with LF, CRLF, lone CR and a BOM gives one hash; one changed character gives another.

### 6.3 Sensor checks (`agents/sensor.py`)

`ingest(*, path, memory, artifact_date, max_bytes, now) -> IngestOutcome`. Checks run in this order; the first one that fails decides the outcome:

1. **Read** the file as bytes. An unreadable path is an input error (CLI exit 2), not a Ledger entry.
2. **Hash** (6.2), then **duplicate:** if an entry whose status is not `rejected` has the same hash, return a duplicate outcome naming that entry and its status. Nothing is written.
3. **Format:** the extension, lowercased, must be `.md` or `.markdown` (`text/markdown`) or `.txt` (`text/plain`). Otherwise `rejected`, check `unsupported-format`. No content sniffing.
4. **Empty:** zero bytes: `rejected`, check `empty`.
5. **Encoding:** decode with `utf-8-sig`. On failure: `quarantined`, check `encoding`.
6. **Empty after decoding:** only whitespace: `rejected`, check `empty`.
7. **Oversized:** `size_bytes > max_bytes`: `quarantined`, check `oversized`. The reason states the size, the limit and the variable name.
8. **Delimiter:** the decoded text contains `</artifact` in any case (reuse `check_artifact`'s pattern): `quarantined`, check `delimiter`.
9. Otherwise `accepted`.

Then, for every outcome except duplicate:

- **ID:** the next `ART-` sequence from the Ledger, the same rule as records (highest plus one, at least four digits, never reused). Rejected entries also get an ID: they are in the Ledger.
- **Title:** for Markdown, the text of the first line that starts with `# `, stripped; otherwise, or when there is none or the file does not decode, the file name stem. Truncated to 200 characters.
- **Same name:** `same_name_as` lists the IDs of earlier entries with exactly the same `source.name` (case-sensitive), any status. Omitted when there are none.
- **Copy:** for `accepted` and `quarantined`, copy the original bytes unchanged to `artifacts/<ID>-<slug><ext>`, where `<slug>` is the stem lowercased, every run of characters outside `a-z0-9` replaced by `-`, trimmed of `-`, cut to 60 characters, and a leading `art-<digits>-` removed (so a file already named `ART-0001-...` does not repeat the prefix). An empty slug becomes `artifact`. Never overwrite an existing file. Write the copy before the Ledger entry, so an entry never points at a missing file.
- **Entry:** history `received` then the outcome, both by `sensor`, both at `now`.

`max_bytes` comes from `KA_SENSOR_MAX_BYTES` (positive integer, default `100000`), read by a small settings function next to the Sensor, not inside `LLMSettings`. Add it to `.env.example` with a one-line comment. An invalid value is a configuration error (exit 2).

Remove `MAX_ARTIFACT_CHARACTERS` and the checks in `read_artifact` that the Sensor now owns. `record-decision` still decodes the stored copy with `utf-8-sig` and normalizes line endings to LF before drafting, because evidence quotes are checked against that text.

### 6.4 Entry builder and transitions (`core/ledger.py`)

Pure functions, no file access:

- `new_entry(...) -> dict` builds a valid entry in schema key order.
- `transition(entry, *, to, by, at, reason=None, check=None, run_id=None, error_type=None) -> dict` returns a new entry with the history entry appended and `status` and `updated_at` set. It raises `LedgerError` for a transition not in 3.2 or the wrong owner. It never changes earlier history entries.
- `with_results(entry, produced, rejected)` sets `produced` and `rejected`, used together with the `processed` transition.
- `error_paths(errors) -> list[str]`: the part of each error message before the first `": "`, unique, in first-seen order. All validator messages already start with a JSON path (`$.evidence[1]: ...`).

### 6.5 Shared JSON files (`storage/json_files.py`) and the Ledger store (`storage/ledger_store.py`)

Move `format_record` and the temporary-file-then-`os.replace` write out of `record_store.py` into `json_files.py` (`format_json(data) -> str`, `write_json_atomic(path, data, *, overwrite: bool)`), and use them from both stores. Record files must keep exactly the same bytes: the existing store tests and the sample project's views check prove it.

`LedgerStore(memory)`:

- `next_id()`, `load(artifact_id)`, `load_all()`: one file per entry in `ledger/`, each validated on read; an invalid file or an unexpected name raises an error naming the file, as in `RecordStore`.
- `save_new(entry)`: validate, refuse if the file exists, write atomically.
- `save_transition(old, new)`: validate `new`; refuse unless the stored file still equals `old` (no lost update) and `new["history"]` starts with `old["history"]` unchanged; then overwrite atomically. This is the only way an existing entry changes.
- `find_by_hash(content_hash)` (excluding `rejected`) and `ids_with_name(name)`.
- Same format as records: UTF-8, LF, two-space indent, keys in schema order, trailing newline. One writing process at a time is assumed.

### 6.6 Pipeline (`pipeline.py`)

`record_decision(*, artifact_id, memory, llm, now) -> RecordOutcome`:

1. Validate the ID format, then load the entry. Refuse (`InputError`, no call) unless the status is `accepted` or `failed`. The message names the status, and for `quarantined` points to `knowledge-automata release`.
2. Keep the `ids_citing` guard as a consistency check: if records already cite the artifact while the Ledger says `accepted` or `failed`, refuse and say the Ledger is behind the records (for example after an interrupted run). No automatic repair in v0.1.
3. Read the stored copy (6.3, last paragraph) and draft with the Decision Registrar, unchanged.
4. On an accepted draft: save the record and the views as today, then the `processed` transition with `produced` set (model, prompt version and schema version from the outcome and the record).
5. On a rejected draft: the `processed` transition with `rejected` set (`error_paths` from the last attempt's errors). Nothing is written to the register. The CLI still exits 1 and prints the full errors.
6. On an `LLMError` other than `LLMConfigError`: the `failed` transition with `error_type`, then re-raise so the CLI exits 3 as today. A configuration error happens before any status change.
7. The `run_id` of the LLM goes into the `processed` or `failed` history entry.

Write order: record, then views, then Ledger. An interruption therefore leaves the Ledger behind, never ahead, and step 2 detects it.

`artifact_date` for the record's sources comes from the Ledger entry. Views map artifact IDs to `stored_path` from the Ledger; `scan_artifacts`, `_ARTIFACT_FILE` and the `--artifact-id` and `--artifact-date` arguments of `record-decision` are removed.

### 6.7 CLI (`cli.py`)

```
knowledge-automata ingest FILE [--artifact-date YYYY-MM-DD] [--memory DIR]
knowledge-automata record-decision ART-0002 [--memory DIR]
knowledge-automata release ART-0005 --reason TEXT [--memory DIR]
knowledge-automata ledger [--memory DIR]
knowledge-automata views [--memory DIR] [--check]
```

- **`ingest`** prints one line: `Accepted ART-0002 (pilot-review.md, 2,048 bytes)`, `Quarantined ART-0005 (oversized: ...)`, `Rejected ART-0006 (unsupported-format: ...)` or `Already in the Ledger as ART-0002 (processed); nothing was written`. When `same_name_as` is set, a second line: `Same file name as ART-0003`. Exit codes: 0 accepted or duplicate; 1 quarantined or rejected; 2 usage, configuration or file problem.
- **`release`** is the Operator's manual release: it reruns the Sensor's checks 3 to 8 on the stored copy, skipping the size limit (7), and if they pass, makes the `quarantined` to `accepted` transition by `operator` with the given reason (required, 1 to 500 characters). In v0.1 only an oversized artifact can be released; for the other checks the Operator fixes the file and ingests it again. Exit 0 on release, 1 if a check still fails, 2 for usage problems (unknown ID, not quarantined).
- **`ledger`** prints one line per entry, sorted by ID: ID, status, title, and the last history entry's check and reason when set. Read-only, exit 0.
- **`record-decision`** takes the artifact ID. Output and exit codes as today.
- Never print artifact text (the title excepted), prompts, settings or keys.

### 6.8 Views

`render_views` builds the artifact links from Ledger entries that have a `stored_path`. The committed sample views must not change (the CI views check proves it), because `ART-0001`'s backfilled entry points at the same file.

### 6.9 Event diagnostics (`llm-event.v1.json` version 1.1)

- Schema: `x-version` becomes `1.1`. Add two optional properties: `finish_reason` (string, 1 to 64 characters, "The provider's reason the model stopped, when it reports one, for example COMPLETE or MAX_TOKENS") and `error_message` (string, 1 to 500 characters, "The project exception's message. Present only when status is error; never prompts, artifact text or model output"). Extend the existing `if status error` rule so `error_message` is not allowed when the status is `ok`. Version 1.0 lines already in a log stay valid against 1.1.
- `LLMResponseError` gains an optional `finish_reason` keyword, like `usage` and `request_id`. The Cohere adapter passes the response's `finish_reason` whenever it raises `LLMResponseError` for a chat response (truncated, incomplete, no text, not JSON, not an object).
- `ObservedLLM` writes `finish_reason` from `ChatResult` on success and from the exception on failure, when present. It writes `error_message` only for subclasses of `LLMError`, as `str(exc)` cut to 500 characters, because `llm/errors.py` already guarantees those messages hold no keys, prompts or artifact text. For any other exception, it writes no message.
- Add a test that no event contains a sentinel string placed in the system message, the user message or the fake model's output, on success and on each error path.

## 7. No real run needed

Nothing here changes how the Registrar talks to Command, so no new decision is recorded and no trial calls are spent. Optional, with Miguel's approval only: rerun `scripts/cohere_smoke.py` once (7 calls) to confirm real chat events now carry `finish_reason` (`COMPLETE` expected) and still validate. Record the result in `dev/STATUS.md` if it is done.

## 8. The sample project's backfilled entry

`ART-0001` and `DEC-0001` predate the Ledger. Create `examples/sample-project/ledger/ART-0001.json` once, **through `core/ledger.py` and `LedgerStore`, not typed by hand**, and paste the exact command you used into the PR description:

- `source.name` is the stored file name, `ART-0001-project-board-2026-02-03.md` (the original name was never recorded); `stored_path` is `artifacts/` plus that name; the hash, size, title and media type are computed by the Sensor's functions; `artifact_date` is `2026-02-03`.
- History: `received` and `accepted` by `sensor`, then `processed` by `pipeline` with run ID `98ebfd14-8f1a-4937-961f-242554938b23` (the handoff 004 run). Every `at` is the backfill time, and each entry's reason is `Backfilled: recorded by handoff 004 before the Artifact Ledger existed`.
- `produced`: `DEC-0001`, with the model, prompt version (`decision-registrar.v1+registrar-retry.v1`) and schema version from its record.

The artifact file, `DEC-0001.json` and the views are not touched.

## 9. Documentation changes

### 9.1 New ADR: `docs/decisions/0015-artifact-ledger-storage-and-sensor-checks.md`

Use this text and add it to the index in `docs/decisions/README.md`:

```markdown
# 0015. Artifact Ledger storage and Sensor checks

- **Status:** Accepted
- **Date:** 2026-10-27

## Context

ADR-0006 defines what the Artifact Ledger holds and who owns each status, and ADR-0013 left its storage to be decided with the Sensor (intake and input guardrail). Unlike records, Ledger entries change status over their life. The thin slice (handoff 004) ran with stand-ins: artifact IDs passed by hand, files found by name, and the input checks inside the pipeline. v0.1 accepts plain text and Markdown from files.

## Decision

- Each artifact has one Ledger entry, `ledger/<ID>.json` in the memory folder, validated against `schemas/core/ledger-entry.v1.json` before every write. The entry holds the current status and an append-only history of transitions (when, by whom, why). Only a valid transition may overwrite the file, and earlier history entries never change.
- Allowed transitions: `received` to `accepted`, `quarantined` or `rejected` (Sensor); `quarantined` to `accepted` (Operator release); `accepted` or `failed` to `processed` or `failed` (Governor, and the pipeline stand-in until the Governor exists). `rejected` and `processed` are final in v0.1.
- The content hash is SHA-256 over the bytes with a leading BOM removed and line endings normalized to LF. A file whose hash matches an entry that is not rejected is a duplicate: nothing is written and the existing entry is named.
- A file with the same name as earlier artifacts but different content is a new artifact; its entry lists those artifacts as a fact (`same_name_as`), not as a guessed revision.
- The Sensor's checks are deterministic. Unsupported formats and empty files are rejected. Files that are not UTF-8, larger than a configurable limit (100,000 bytes by default), or that contain the artifact delimiter are quarantined and kept for the Operator (human in the loop).
- `processed` means the pipeline ran to the end, even with zero records; the entry lists the records produced and the drafts rejected, by register, attempts, prompt version and error paths. `failed` is for errors such as a provider error.
- The Ledger never holds model output, and holds artifact text only as the title.

## Consequences

- Reruns are idempotent, and every artifact's path through the system can be read in one file.
- Artifacts and records link both ways: records through their sources, Ledger entries through `produced`.
- Writes go record, views, then Ledger, so an interruption leaves the Ledger behind the records, which the pipeline detects. There is no automatic repair yet.
- Long documents must be released by hand until chunking exists, and other formats wait for converters that run before the Sensor.
- Exact-name matching flags common names such as `notes.md` often; the flag is informational only.
```

### 9.2 Amendments

- **ADR-0006:** under the status list, add: "Storage, the allowed transitions and the Operator release are set out in [ADR-0015](0015-artifact-ledger-storage-and-sensor-checks.md)." Mark it `Accepted (amended 2026-10-27)` in the ADR index.
- **ADR-0012:** in the event bullet, add that events may also carry the provider's `finish_reason` and, for failed calls, the project exception's message (event schema 1.1). Mark it amended in the index.

### 9.3 `docs/architecture.md`

- **Data flow, step 1:** one sentence that the Sensor runs deterministic checks and writes the Ledger entry, linking ADR-0015.
- Replace the thin-slice sentence: the Sensor and Ledger now run (handoff 005); the Governor and Comparator steps are still skipped, and the pipeline stand-in sets `processed` and `failed`.
- **Storage and views:** add `ledger/` to the layout and one sentence on Ledger entries.
- **Observability:** mention `finish_reason` and the error message.

### 9.4 `README.md`

"Try it": `ingest` then `record-decision ART-0002`, and one line that the Ledger tracks every artifact. "Status": the Sensor and the Artifact Ledger move to what works today. Keep model IDs out of the README.

### 9.5 `examples/sample-project/README.md`

Add `ledger/ART-0001.json` to the layout, and one sentence that the entry was backfilled after handoff 004.

### 9.6 `dev/backlog.md`

- **Now:** remove the Sensor and Ledger item.
- **Later:** "Chunking long artifacts after Operator approval: evidence quotes must still match the original text, and a decision can span two chunks." "Document versions: treat an artifact as a new version of an earlier one and process only what changed." "Format converters (PDF, Word) as a step before the Sensor; the Ledger hashes the original file and stores the extracted text that evidence is checked against." "Artifact Ledger Markdown view." "Operator release workflow beyond the `release` command (review queue, reasons, notifications)." "Reprocessing `processed` artifacts after a prompt change, with the Comparator."
- **Open questions:** mark as decided, linking ADR-0015: the Ledger storage, the `processed` status with rejections, persisting rejected drafts (error paths only), and the line-ending rule for hashes. Mark the `finish_reason` item done (event schema 1.1).

### 9.7 `dev/tool-feedback.md` and `dev/principles-in-practice.md`

Log anything surprising. Add principles entries where a principle visibly shaped the work (for example P4 for the two-way links, P10 for quarantine instead of silent loss, P16 for the shared JSON writer).

### 9.8 `dev/STATUS.md`

Update at the end of the session. Also fix "Current phase", which still says "PR #1 to PR #5" (PR #6 and the README pass have merged since).

## 10. Suggested commit sequence

1. `feat: add finish_reason and error messages to LLM events` (event schema 1.1)
2. `refactor: share the deterministic JSON writer between stores`
3. `feat: add the Artifact Ledger schema, entry builder and store` (implements ADR-0015)
4. `feat: add the Sensor with deterministic intake checks`
5. `feat: drive record-decision from the Ledger and add ingest, release and ledger commands`
6. `feat: backfill the sample project's Ledger entry for ART-0001`
7. `docs: add ADR-0015, amend ADR-0006 and ADR-0012, update architecture, README and backlog`
8. `docs: update status`

Each commit includes its tests and ends with the `Co-authored-by:` trailers copied from the code block in `AGENTS.md`. Run `ruff check`, `ruff format --check` and `pytest` before each commit. Suggested pull request title: `feat: add the Sensor and the Artifact Ledger (handoff 005)`. Miguel adds the Copilot credits to `dev/costs.md` before merging.

## 11. Tests

No network anywhere (the autouse fixture stays).

- **Hash:** 6.2 cases.
- **Sensor:** one test per check in 6.3, each asserting the status, `check`, whether a copy exists and the exit code through the CLI; the order (a `.pdf` that is also empty is `unsupported-format`; an oversized file that is not UTF-8 is `encoding`); a duplicate of an accepted, a quarantined and a processed entry is a no-op with nothing written; a duplicate of a rejected entry gets a new entry; `same_name_as` with zero, one and two earlier entries; ID sequence with a rejected entry in between; title from a heading, from the stem, and truncated; slug rules, including a name that already starts with `ART-0001-` and one with no usable characters; the copy's bytes equal the original's; `KA_SENSOR_MAX_BYTES` default, override and invalid value.
- **Ledger:** every allowed transition and every refused one (wrong status, wrong owner); history never rewritten; `validate_ledger_entry` catches a status that differs from the last history entry, a missing `stored_path`, `produced` on an accepted entry, and a `failed` entry without `error_type`; `error_paths` on evidence, schema and semantic errors.
- **Ledger store:** `save_new` refuses an existing file and an invalid entry, with no temporary file left; `save_transition` refuses a stale `old` and a rewritten history; saved bytes match a hand-written expected file; `load_all` names an invalid or unexpected file.
- **Shared writer:** record files written before and after the refactor are byte-identical.
- **Pipeline and CLI (end to end in `tmp_path` with `FakeLLM`):** `ingest` then `record-decision` produces `DEC-0001`, the views, and a `processed` entry listing it; a rejected draft gives `processed` with `rejected` and no record; a provider error gives `failed`, and a rerun can then succeed; `record-decision` on a quarantined, rejected or processed artifact exits 2 with no call; the "Ledger behind records" guard; `release` on an oversized artifact, and refused on an encoding quarantine; `ledger` output; views link artifacts through the Ledger; no output contains artifact text other than the title.
- **Events:** `finish_reason` on a successful chat; `finish_reason` and `error_message` on an `LLMResponseError` with `MAX_TOKENS`; `error_message` on `LLMRateLimitError`; no `error_message` for a non-project exception; a 1.0 event still validates; the sentinel test in 6.9.
- **Sample project:** CI's views check still passes, and the backfilled entry loads and validates.

## 12. Done when

- The modules in section 4 exist with the tests in section 11, and `ruff check`, `ruff format --check` and `pytest` pass locally and in CI (`ci-ok` green), including Python 3.15.
- No test touches the network; only `llm/cohere_adapter.py` imports `cohere`; the Sensor, the Ledger, storage and agent logic stay in separate modules.
- The sample project's committed record and views are unchanged, and its backfilled Ledger entry was written through the code (8).
- ADR-0015 is added, ADR-0006 and ADR-0012 are amended, and the docs in section 9 are updated.
- No file was read from or copied from Chronicle. No secrets in the repo; `.env` stays untracked.
- `dev/STATUS.md` is updated and you have reported back, ending with **Cohere notes**.

## 13. Out of scope

The Governor's classification and work orders, the Comparator and reprocessing of `processed` artifacts, chunking, format converters, document versioning, fuzzy name matching, relevance and prompt-injection checks, an Operator workflow beyond `release`, a Ledger Markdown view, a command that runs the pipeline over a folder, the Risk Registrar, prompt changes, and the evaluation set.
