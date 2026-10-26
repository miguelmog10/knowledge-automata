# Handoff 004: thin vertical slice, from one artifact to the decision log

- **From:** Claude (discovery, architecture, review)
- **To:** Copilot (implementation)
- **Owner and approver:** Miguel
- **Date:** 2026-10-26
- **Branch:** `feat/decision-slice`
- **Scope:** one sample artifact through the Decision Registrar (specialist record keeper), on a real Command call, to one validated decision record stored as a JSON file, plus the decision log's Markdown views and a first CLI command. No Sensor, Artifact Ledger, Governor or Comparator.

---

## 1. Context

Handoff 003 (PR #4) delivered the LLM service layer. This handoff proves the Cohere path end to end before the Sensor (intake and input guardrail) is built: an artifact goes in, a validated record comes out, and the result can be browsed on GitHub.

What already exists and must be reused, not rebuilt:

- `knowledge_automata.llm`: `build_llm`, `chat_json`, `CallContext`, `FakeLLM`, the event log and the project exceptions (ADR-0012).
- `knowledge_automata.core`: `draft_schema`, `validate_draft` (schema, semantic checks and evidence quotes), `validate_record`, `schema_version`, `DECISION_LOG` (ADR-0011).
- `scripts/cohere_smoke.py` shows the call pattern that worked against the real API.

Read `AGENTS.md`, `dev/STATUS.md`, ADR-0005, ADR-0006, ADR-0011, ADR-0012 and `docs/architecture.md` before planning.

**What Miguel decided for this handoff (2026-10-26):**

1. The sample artifact, its record and the decision log views are **committed in `examples/sample-project/`**, the first piece of the fictional sample project. The folder that holds records and views is a parameter; for real use it defaults to the git-ignored `runtime/memory`.
2. With no Sensor or Ledger yet, **the caller passes the artifact ID and date** (`--artifact-id`, `--artifact-date`). This is temporary and documented as such.
3. The Decision Registrar runs with **thinking disabled by default** (`KA_CHAT_THINKING` still overrides it). The smoke check showed about 6x billed output tokens for the same validation result on one artifact. Revisit when the sample project's evaluation set exists.
4. The slice runs through **the first CLI command** (`knowledge-automata`), so the later pipeline CLI grows from it instead of replacing a script.
5. **Storage:** one JSON file per record (ADR-0013, section 8.1), confirming the backlog's leaning.

**Already committed by Miguel on this branch:** this handoff, the Registrar prompt (`prompts/project-management/decision-registrar.v1.md`), the retry prompt (`prompts/core/registrar-retry.v1.md`), the sample artifact (`examples/sample-project/artifacts/ART-0001-project-board-2026-02-03.md`), and the PR #4 housekeeping in `dev/costs.md` and `dev/STATUS.md`. Do not modify these files. If you find a problem in them, raise it in your plan.

## 2. How to work on this task

1. **Plan first.** Read this whole document, then reply with a short plan: files to create or change, anything here that does not fit the existing code, and the commit sequence. **Wait for Miguel's approval** before writing files.
2. Implement in small commits (section 9), with tests in the same commit as the code they cover.
3. **No test may call the network.** The one real run (section 7) happens only with Miguel's approval, with his key in `.env`, and costs one or two calls.
4. If anything here is ambiguous or seems wrong, ask instead of guessing, and add it to `dev/backlog.md` under *Open questions*.
5. Finish by updating `dev/STATUS.md` and reporting what you did, ending with the **Cohere notes** section required by `AGENTS.md`.

## 3. Agreed design

### 3.1 The flow

```
artifact file ──► Decision Registrar ──► validate_draft ──┬─► envelope (code) ──► validate_record ──► JSON file ──► Markdown views
  (read-only)     (Command, 1 call)     (schema, semantic, │
                                          evidence quotes)  └─► invalid: one retry with the errors, then reject (nothing written)
```

Steps 1 to 3 of the architecture's data flow (Sensor, Governor, Comparator) are skipped: every record in this slice is classified `new`. A small orchestration function stands in for the Governor (orchestrator) and is replaced when the Governor exists.

### 3.2 Model proposes, code checks (design principle)

The model drafts `content` and `evidence` only. Code assigns the ID, timestamps, sources, history and record status, validates the full record, and writes it. A record that fails any check is never written.

### 3.3 One Registrar loop for every register

Nothing in the drafting loop is specific to decisions: the register spec and the prompt file are the only inputs that differ. Build it once (`agents/registrar.py`) so the Risk Registrar later is configuration plus a prompt (P16). Do not add abstractions beyond that.

### 3.4 Prompts are versioned files

The system message is the content of a prompt file, sent as is. Prompt files are immutable once a record cites them: any change is a new version file (`decision-registrar.v2.md`), and the old file stays, because record history names the prompt version that produced each revision.

### 3.5 Instructions and artifact are kept apart

The system message holds only instructions. The user message holds only the artifact text, between `<artifact>` and `</artifact>` lines. An artifact that contains `</artifact` (any case) is refused before any call, because it could close the delimiter early; the Sensor's checks replace this later.

### 3.6 One retry, with the errors

If the response is unusable (`LLMResponseError`) or the draft fails `validate_draft`, the Registrar retries once. The retry's system message is the Registrar prompt, a blank line, then the retry prompt with `{errors}` replaced by the previous attempt's errors, one per line, each starting with `- ` (for an `LLMResponseError`, its message). Replace the placeholder with `str.replace`, not `str.format`, because error messages contain braces. If the retry fails too, the record is rejected. Configuration, authentication, request, rate-limit and availability errors are not retried here (the SDK already retries what can be retried).

The prompt version of a retry attempt is `decision-registrar.v1+registrar-retry.v1`. It goes into the call's `CallContext` and, when the retry produced the stored draft, into the record's history.

### 3.7 Storage and views

Records live in a **memory folder**: the stored institutional memory of one group. Layout:

```
<memory>/
  artifacts/                         raw artifacts (read-only; only the sample project keeps them here)
  registers/decision-log/DEC-0001.json
  views/decision-log.md              index (generated)
  views/decision-log/DEC-0001.md     one page per decision (generated)
```

JSON records are the source of truth. Views are generated from them, never edited by hand, and a check fails when committed views differ from the generator's output.

### 3.8 Idempotency until the Ledger exists

Without the Ledger's content hashes, rerunning on the same artifact would create a duplicate decision. Before any call, `record-decision` refuses if a record in the register already cites the artifact ID, and spends no call.

## 4. Target structure

New and changed files (existing files not shown):

```
src/knowledge_automata/
  cli.py                                   # knowledge-automata console script (argparse)
  pipeline.py                              # record_decision: stand-in for the Governor in this slice
  agents/__init__.py
  agents/registrar.py                      # shared Registrar drafting loop
  core/prompts.py                          # load versioned prompt files
  core/records.py                          # build a new record's envelope (code-owned fields)
  storage/__init__.py
  storage/record_store.py                  # one JSON file per record (ADR-0013)
  views/__init__.py
  views/markdown.py                        # escaping, relative links, write and check view files
  domains/project_management/decision_log_view.py   # decision log index and pages
prompts/                                   # committed by Miguel (section 1)
examples/sample-project/
  README.md                                # what the sample project is and how it was produced
  artifacts/ART-0001-project-board-2026-02-03.md     # committed by Miguel
  registers/decision-log/DEC-0001.json     # from the real run (section 7), unedited
  views/decision-log.md                    # generated
  views/decision-log/DEC-0001.md           # generated
tests/
  test_prompts.py, test_records.py, test_record_store.py, test_registrar.py,
  test_decision_log_view.py, test_cli.py
  fixtures/views/...                       # expected view output, written by hand (6.6)
docs/decisions/0013-record-storage-json-files.md
docs/decisions/0014-registrar-drafting-loop.md
pyproject.toml                             # console script, prompts in the wheel
.github/workflows/ci.yml                   # views check, prompts in the package job
```

Remove `prompts/.gitkeep` and `examples/.gitkeep`.

## 5. The sample artifact and the expected record

`examples/sample-project/artifacts/ART-0001-project-board-2026-02-03.md` is fictional meeting notes from the project board of Tallyleaf, a small team building a mobile app for plant inventory in commercial greenhouses. The team, the app and the meeting are invented; the sample project will follow this team's decisions over several meetings. It contains one decision with a rationale and a rejected option, plus distractors the Registrar must not record as decisions: a proposal with no outcome (QR codes on benches), a risk (conflicting offline counts) and action items. It also has a typographic apostrophe and sentences that wrap across lines, which the evidence check must handle.

A good record, for Miguel's review after the real run (wording will differ):

- **statement:** build one Flutter app for iOS and Android (separate native apps rejected for version 1).
- **rationale:** a single codebase lets the two developers ship the walkthrough count to both platforms at the same time.
- **alternatives:** separate native apps (Swift for iOS, Kotlin for Android).
- **decided_by:** the project board. **decided_on:** 2026-02-03.
- **context:** may mention that growers use both iPhones and Android phones.
- **Not in the record:** the QR codes (no decision yet), the offline sync risk, the actions.
- **evidence:** quotes copied from the artifact, the decision first.

## 6. Code requirements

### 6.1 Packaging (`pyproject.toml`)

- Console script: `[project.scripts] knowledge-automata = "knowledge_automata.cli:main"`.
- Ship the prompts in the wheel like the schemas: `"prompts" = "knowledge_automata/prompts"` under `force-include`.
- No new runtime dependency (`argparse`, `json`, `pathlib` and `os` are enough).

### 6.2 Prompts (`core/prompts.py`)

- `prompts_root()` mirrors `schemas_root()`: the packaged `knowledge_automata/prompts` first, then the repository's `prompts/` folder in a source checkout.
- `load_prompt(name)` takes a path relative to `prompts/` without the extension (`project-management/decision-registrar.v1`) and returns a `Prompt` with `version` (the file stem, `decision-registrar.v1`) and `text`. Read as UTF-8; reject absolute paths and `..` like `load_schema`; raise `FileNotFoundError` naming the prompt when it is missing.
- `list_prompts()` for the CI package job.

### 6.3 Registrar loop (`agents/registrar.py`)

Suggested shape (adjust in your plan if the code suggests better names):

```python
@dataclass(frozen=True)
class Registrar:
    agent: str              # "decision-registrar", used in CallContext and events
    spec: RegisterSpec      # DECISION_LOG
    prompt: Prompt          # decision-registrar.v1
    retry_prompt: Prompt    # registrar-retry.v1
    max_attempts: int = 2


@dataclass(frozen=True)
class DraftOutcome:
    draft: dict[str, Any] | None   # the accepted draft; None when rejected
    errors: tuple[str, ...]        # errors of the last attempt; empty when accepted
    attempts: int
    model: str | None              # model that produced the accepted draft
    prompt_version: str            # of the accepted attempt, or of the last attempt
    usage: tuple[Usage, ...]       # one per call that returned a result

    @property
    def accepted(self) -> bool: ...


def draft_record(
    registrar: Registrar, llm: ChatModel, artifact_text: str, *, artifact_id: str
) -> DraftOutcome: ...
```

- Each attempt calls `llm.chat_json(system=..., user=..., schema=draft_schema(spec), context=CallContext(agent, artifact_id, prompt_version))`.
- User message: `"<artifact>\n" + artifact_text + "\n</artifact>"`. Nothing else.
- Validation: `validate_draft(result.data, spec, artifact_text)`. Accept when `ok`.
- Retry and rejection as in 3.6. `LLMResponseError` counts as a failed attempt; other `LLMError`s propagate unchanged.
- Raise `ValueError` before any call if the artifact contains `</artifact` (any case) or is empty after stripping.
- The function never writes files and never builds the envelope.

### 6.4 Envelope (`core/records.py`)

`new_record(*, spec, record_id, content, quotes, artifact_id, artifact_date, model, prompt_version, now) -> dict` builds a `revision: 1`, `record_status: "active"` record:

- `register` = `spec.name`; `schema_version` = `schema_version(spec)`.
- `content`: keys reordered to the content schema's property order, so files diff cleanly.
- `sources`: one entry per quote, in order, each with `artifact_id`, `artifact_date` (only when given), `excerpt` (the quote as drafted) and `added_at`.
- `history`: one entry with `revision: 1`, `at`, `change: "new"`, `artifact_id`, `fields` (content keys in schema order), `model` and `prompt_version`.
- `created_at`, `updated_at`, every `added_at` and `at` are the same `now`, formatted `YYYY-MM-DDTHH:MM:SSZ` in UTC (no fractions). `now` is passed in, so tests are deterministic.
- Key order of the envelope follows `schemas/core/record.v1.json`.

### 6.5 Record store (`storage/record_store.py`)

`RecordStore(memory: Path)`, per ADR-0013:

- `next_id(spec)`: highest sequence among files named `<PREFIX>-<digits>.json` in `registers/<spec.name>/`, plus one, zero-padded to four digits (`DEC-0001` when empty; `DEC-0004` after `DEC-0001` and `DEC-0003`; `DEC-10000` after `DEC-9999`). IDs are never reused.
- `save_new(record, spec) -> Path`: run `validate_record`; if it fails, raise with every error and write nothing. Refuse if the file exists. Write to a temporary file in the same folder, then move it into place (`os.replace`); no temporary file may remain after success or failure. Create folders as needed.
- Formatting: `json.dumps(record, indent=2, ensure_ascii=False) + "\n"`, UTF-8, LF line endings (`newline="\n"`), keys in the order given.
- `load_all(spec) -> list[dict]`: every record, sorted by ID, each validated; an invalid file raises an error naming the file. A file in the register folder that does not match the ID pattern raises an error naming it (never silently ignored).
- `ids_citing(spec, artifact_id) -> list[str]`: IDs of records with a source from that artifact.
- One writing process at a time is assumed, as for the event log.

### 6.6 Decision log views (`views/markdown.py`, `domains/project_management/decision_log_view.py`)

`render_decision_log(records, artifact_links) -> dict[str, str]` maps paths relative to `<memory>/views/` to file contents. `artifact_links` maps an artifact ID to the artifact file's path relative to the memory folder; artifacts not in the map are shown as plain IDs. The CLI builds the map by scanning `<memory>/artifacts/` for files whose name starts with an artifact ID followed by `-` or `.` (two files for one ID is an error). The Ledger replaces this convention later.

**Index** (`decision-log.md`):

```markdown
# Decision log

Generated from the JSON records in `registers/decision-log/`. Do not edit this file by hand: run `knowledge-automata views` to regenerate it.

| ID | Decision | Decided on | Status |
|---|---|---|---|
| [DEC-0001](decision-log/DEC-0001.md) | Build one Flutter app for iOS and Android | 2026-02-03 | active |
```

Sorted by ID. "Decided on" is empty when absent. A superseded record shows `superseded by [DEC-0002](decision-log/DEC-0002.md)`. With no records, the table is replaced by "No decisions recorded yet."

**One page per decision** (`decision-log/DEC-0001.md`):

Lines with a note in parentheses describe a section; they are not literal output.

```markdown
---
id: DEC-0001
status: active
revision: 1
created: 2026-10-26T14:03:12Z
updated: 2026-10-26T14:03:12Z
---

# DEC-0001: Build one Flutter app for iOS and Android

Back to the [decision log](../decision-log.md).

## Decision

Build one Flutter app for iOS and Android.

## Context
## Rationale
## Alternatives considered      (bullet list)
## Decided by                   (comma-separated)
## Decided on
## Impacts
## Related decisions            (only when relations exist: "Supersedes [DEC-0001](DEC-0001.md)", "Superseded by ...")

## Sources

> the board chose to build one Flutter app for iOS and Android, because a single codebase lets two developers ship the walkthrough count to both platforms at the same time.

From [ART-0001](../../artifacts/ART-0001-project-board-2026-02-03.md), 2026-02-03.

## History

| Revision | Date | Change | Artifact | Model | Prompt |
|---|---|---|---|---|---|
| 1 | 2026-10-26T14:03:12Z | new | ART-0001 | command-a-plus-05-2026 | decision-registrar.v1 |
```

- Sections for absent optional fields are omitted. Field order follows the content schema.
- Supersession is linked both ways when relations exist (the slice writes none, but render them; a test covers it).
- All links are standard relative Markdown links, computed from file locations, with `/` separators on every platform.
- Escaping: content is LLM text, so escape ``\ ` * _ [ ] < > |`` in every rendered value, and in table cells also replace line breaks with spaces. Multi-line quotes become one `> ` line per line.
- No generation timestamp or anything else that changes between runs: the same records always produce the same bytes.
- `write_views(views_dir, files, owned)` writes changed files and deletes stale `.md` files the generator owns (`decision-log.md` and everything under `decision-log/`). `check_views(...)` returns the differences (missing, changed, extra), comparing with line endings normalized, so a Windows checkout with CRLF passes.

**Tests:** write the expected files in `tests/fixtures/views/` **by hand from this section**, not by copying the generator's output, and compare against them. Cover: one full record (the existing `decision-record.json` fixture), a record with only `title` and `statement`, a superseded pair, a value containing `|`, `*`, `<` and a line break, an empty register, and an artifact with and without a link.

### 6.7 Orchestration (`pipeline.py`)

`record_decision(*, artifact_path, artifact_id, artifact_date, memory, llm, now) -> RecordOutcome`, the stand-in for the Governor (orchestrator):

1. Validate `artifact_id` (`ART-` and four or more digits) and, when given, `artifact_date` (`YYYY-MM-DD`, a real date) before reading anything.
2. Read the artifact as UTF-8 (a BOM is tolerated). Refuse an empty file, a file that is not valid UTF-8, or one longer than 50,000 characters, with a clear message (the Sensor takes this over).
3. Refuse if `ids_citing` finds a record from this artifact (3.8). No call is made.
4. `draft_record` with the Decision Registrar.
5. If accepted: `next_id`, `new_record` with the model and prompt version from the outcome, `save_new`, then regenerate the decision log views.
6. Return the outcome (record ID and path, or the rejection errors), attempts, usage and the run ID.

The Decision Registrar's thinking default lives here: when `settings.chat_thinking` is `None`, use `"disabled"` (`DECISION_REGISTRAR_THINKING`).

### 6.8 CLI (`cli.py`)

```
knowledge-automata record-decision ARTIFACT --artifact-id ART-0001 [--artifact-date 2026-02-03] [--memory DIR]
knowledge-automata views [--memory DIR] [--check]
```

- `--memory` defaults to `runtime/memory` (under the existing `/runtime/` ignore rule).
- `record-decision` builds the LLM with `build_llm` and prints: the run ID; `Recorded DEC-0001 from ART-0001 in 1 attempt (model ..., prompt ..., thinking disabled)`; billed input and output tokens summed over the attempts; the record and index paths. On rejection it prints every error of the last attempt to stderr.
- `views` regenerates every view from the stored records; with `--check` it writes nothing and reports differences.
- Exit codes: 0 success; 1 record rejected, or views differ under `--check`; 2 usage or configuration error (bad arguments, missing API key with the setup hint, unreadable or refused artifact, artifact already recorded); 3 provider error (authentication, rate limit, unavailable, request rejected). Every failure prints one clear message, never a traceback.
- `main(argv=None, *, build=build_llm, clock=...)` so tests inject `FakeLLM` through `ObservedLLM` with a `MemorySink`, and a fixed clock.
- Never print the settings, the key, prompts or artifact text.

## 7. The real run

With Miguel's approval and his key in `.env`, run once:

```
uv run --env-file .env knowledge-automata record-decision examples/sample-project/artifacts/ART-0001-project-board-2026-02-03.md --artifact-id ART-0001 --artifact-date 2026-02-03 --memory examples/sample-project
```

- Expected cost: one call, two if the retry is needed. Do not rerun to get a "nicer" record: if the record is wrong, stop and report it, with the errors or the content, so Miguel and Claude can decide whether the prompt needs a v2.
- Commit the record and views exactly as produced. Never edit them by hand.
- Report the printed output (it contains only fictional data, model IDs, billed units and timings), the event log lines of the run (metadata only), and the record's content for Miguel's quality review against section 5.
- Record in `dev/STATUS.md`: attempts, billed tokens, latency, and whether the content matched section 5.

## 8. Documentation changes

### 8.1 New ADR: `docs/decisions/0013-record-storage-json-files.md`

Use this text and add it to the index in `docs/decisions/README.md`:

```markdown
# 0013. Record storage: one JSON file per record

- **Status:** Accepted
- **Date:** 2026-10-26

## Context

Records need durable storage from the first slice (handoff 004). The backlog listed three options: one JSON file per record, one file per register, or SQLite. The repository is public, and the sample project's records are meant to be read and reviewed on GitHub. v0.1 has one writing process and small registers.

## Decision

- Each record is one JSON file, `registers/<register>/<ID>.json`, inside a memory folder that holds the institutional memory of one group. The memory folder is a parameter: the default, `runtime/memory`, is git-ignored, and the sample project uses `examples/sample-project`.
- Code validates every record (envelope and content) before writing it. An invalid record is never written.
- A new record is written to a temporary file and moved into place. A new record never overwrites an existing file; revisions arrive with the Comparator (reconciliation).
- The next ID is the highest existing sequence in the register plus one. IDs are never reused.
- Files are written deterministically (UTF-8, LF line endings, two-space indentation, fixed key order), so diffs show only real changes.
- Markdown views are generated from the files and never edited by hand.
- One writing process at a time is assumed.

## Consequences

- Records are plain files that can be read, diffed and reviewed one by one, with no database.
- Finding the next ID, or the records that cite an artifact, means reading the register folder. That is fine at v0.1 scale; an index can come later.
- There are no transactions across files. A supersession changes two files, so the Comparator handoff must order the writes so that an interruption leaves a state that can be detected and repaired.
- Concurrent writers could clash on IDs; a lock or SQLite is the path if that becomes real.
- The Artifact Ledger's storage is decided with the Sensor (intake and input guardrail).
```

### 8.2 New ADR: `docs/decisions/0014-registrar-drafting-loop.md`

```markdown
# 0014. Registrar drafting loop

- **Status:** Accepted
- **Date:** 2026-10-26

## Context

ADR-0005 and ADR-0011 require every draft to be validated before it becomes a record, and AGENTS.md says invalid output is retried or rejected, never written. The first Registrar (specialist record keeper) needs a concrete loop: what goes to the model, when to retry, and what is recorded about the attempt. The handoff 003 smoke check measured Command A+ with thinking enabled at about 6x the billed output tokens of thinking disabled, with the same validation result, on one artifact.

## Decision

- A Registrar is a register spec plus a versioned prompt file in `prompts/`. One drafting loop serves every Registrar.
- The system message holds only instructions. The user message holds only the artifact, between `<artifact>` tags. An artifact containing the closing tag is refused until the Sensor (intake and input guardrail) checks input.
- Each draft is checked with `validate_draft`: schema, semantic checks and evidence quotes. An invalid draft or an unusable response gets one retry, with the errors added to the system message from a versioned retry prompt. If the retry fails, the record is rejected and nothing is written. Configuration, authentication, request, rate-limit and availability errors are not retried by the loop.
- The record history stores the prompt version of the attempt that produced the stored draft, including the retry prompt when one was used (for example `decision-registrar.v1+registrar-retry.v1`).
- Prompt files are immutable once a record cites them; a change is a new version file.
- The Decision Registrar runs with Command A+ thinking disabled by default; `KA_CHAT_THINKING` overrides it. This is revisited with the sample project's evaluation set.

## Consequences

- At most two calls per record, visible in the event log.
- The retry feedback includes quotes from the model's previous output; they go back to the same model for the same artifact.
- A single retry will not fix a systematic prompt problem; rejection rates in evaluation runs will show it.
- Thinking disabled may miss harder decisions; the evaluation set decides.
```

### 8.3 `docs/architecture.md`

- **New section "Storage and views"** after "Write rules": the memory folder layout (3.7), JSON records as the source of truth, generated views and the CI check. Link ADR-0013.
- **Data flow:** one sentence that the thin slice (handoff 004) runs step 4 for the decision log without steps 1 to 3, and every record is `new` until the Comparator exists.
- **Registrars:** one sentence on the shared drafting loop and the retry. Link ADR-0014.

### 8.4 `README.md`

- "Status": first slice working: one artifact to one validated decision record on a real Command call.
- After "Getting started", a short "Try it" section: the `record-decision` and `views` commands, and a link to `examples/sample-project/views/decision-log.md` ("a decision recorded from fictional meeting notes"). Keep model IDs and prices out of the README.

### 8.5 `examples/sample-project/README.md`

What the sample project is (the invented Tallyleaf team building a greenhouse plant inventory app, growing into the evaluation set; a short note that the team and app are fictional), the folder layout, that `ART-0001`'s record came from one real Command call and was not edited, how to regenerate the views, and that views are never edited by hand.

### 8.6 `dev/backlog.md`

- **Now:** remove the thin slice item; in the Markdown view item, mark the decision log view done and keep the risk register view.
- **Open questions:** mark storage as decided (ADR-0013). Add: "How a Registrar reports that an artifact has nothing to record. The draft schema always requires content; this is probably the Governor's job (it only sends work orders for items it found)." and "Persisting rejected drafts and their errors: with the Artifact Ledger's `failed` status (ADR-0006)."
- **Later:** "Thinking on versus off for the Registrars, measured on the evaluation set."

### 8.7 `dev/tool-feedback.md` and `dev/principles-in-practice.md`

Log anything surprising from the real run or the SDK. Add principles entries where a principle visibly shaped the work (for example P11 for committing the real record unedited, or P6 for the thin slice ahead of the Sensor).

### 8.8 `dev/STATUS.md`

Update at the end of the session, including the real run results (section 7).

## 9. Suggested commit sequence

1. `build: package prompt files and add the prompt loader`
2. `feat: add the record envelope builder and the JSON record store` (implements ADR-0013)
3. `feat: add the shared Registrar drafting loop` (implements ADR-0014)
4. `feat: add the decision log Markdown views`
5. `feat: add the knowledge-automata CLI with record-decision and views`
6. `ci: check that committed views match the generator and load prompts from the wheel`
7. `docs: add ADR-0013 and ADR-0014 and update architecture, README and backlog`
8. `feat: record the first sample decision from a real Command call` (the run's record and views, unedited, plus `examples/sample-project/README.md`)
9. `docs: record the real run results and update status`

Each commit includes its tests and ends with a `Co-authored-by:` trailer. Run `ruff check`, `ruff format --check` and `pytest` before each commit. Suggested pull request title: `feat: add the decision slice from artifact to decision log (handoff 004)`. Miguel adds the Copilot credits to `dev/costs.md` as the last commit before merging, and checks that the squash commit's `Co-authored-by:` trailers start at the beginning of their lines.

## 10. Tests

No network anywhere (the autouse fixture stays). Use `FakeLLM` wrapped in `ObservedLLM` with a `MemorySink` where events matter.

- **Prompts:** both prompt files load with the right `version`; a missing prompt and a path with `..` fail clearly.
- **Records:** a built record passes `validate_record`; one source per quote, `artifact_date` only when given; content and envelope key order; timestamp format; the history entry's fields, model and prompt version.
- **Store:** `next_id` on an empty register, with gaps, and past 9999; `save_new` refuses an existing ID and an invalid record (nothing written, no temporary file left); saved bytes match a hand-written expected file; `load_all` round-trips and names an invalid or unexpected file; `ids_citing` finds records by artifact.
- **Registrar:** valid draft on the first call (one call, accepted); invalid evidence then valid (two calls, the second system message contains the error and the retry prompt, the accepted prompt version is `decision-registrar.v1+registrar-retry.v1`); invalid twice (rejected, errors of the last attempt); `LLMResponseError` then valid (retried); `LLMRateLimitError` (not retried, propagates); the user message is exactly the delimited artifact and the first system message is exactly the prompt file; every call's context has the agent, artifact ID and prompt version, and its schema is `draft_schema(DECISION_LOG)`; an artifact containing `</ARTIFACT>` is refused with no call.
- **Views:** the cases in 6.6, plus: same records give identical bytes on a second render; `check_views` reports missing, changed and extra files and ignores CRLF versus LF.
- **CLI (end to end in `tmp_path`):** `record-decision` stores `DEC-0001`, writes the views and exits 0; a second run on the same artifact exits 2 with no call; a missing key exits 2 with the hint; a rejected draft exits 1 and writes nothing; bad `--artifact-id` or `--artifact-date` exits 2; `views --check` exits 0 on matching views and 1 after a view is edited; thinking defaults to `disabled` and `KA_CHAT_THINKING=enabled` overrides it; no output contains the artifact text or a sentinel placed in the prompt.
- **CI:** in the `test` job, after pytest: `uv run --no-sync knowledge-automata views --memory examples/sample-project --check`. In the `package` job, also load every prompt from the installed wheel.

## 11. Done when

- The modules in section 4 exist with the tests in section 10, and `ruff check`, `ruff format --check` and `pytest` pass locally and in CI (`ci-ok` green), including Python 3.15.
- No test touches the network; only `llm/cohere_adapter.py` imports `cohere`; agent logic, LLM calls and storage stay in separate modules.
- The real run has been done once with Miguel's approval, and `DEC-0001` and its views are committed unedited and pass the views check.
- ADR-0013 and ADR-0014 are added and the docs in section 8 are updated.
- No file was read from or copied from Chronicle. No secrets in the repo; `.env` stays untracked.
- `dev/STATUS.md` is updated and you have reported back, ending with **Cohere notes**.

## 12. Out of scope

The Sensor and Artifact Ledger, the Governor's classification and work orders, the Comparator and the update, reaffirmation and supersession writes, the Risk Registrar and the risk register view, more than one decision per artifact, persisting rejections, the evaluation set, budget guards, the Oracle, and any change to the schemas or the LLM service layer (raise it in the plan if one seems needed).
