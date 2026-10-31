# Handoff 007: the Governor (orchestrator)

- **From:** Claude (discovery, architecture, review)
- **To:** Copilot (implementation)
- **Owner and approver:** Miguel
- **Date:** 2026-10-31
- **Branch:** `feat/governor`
- **Scope:** the Governor (orchestrator), which reads an accepted artifact once and writes work orders, one per item, for the Registrars (specialist record keepers); the Decision Registrar's second prompt, which drafts the item a work order points to; a work orders file per artifact that makes a run resumable; a limit on items per artifact, with a new Ledger status `held`; and the `process` command, which replaces `record-decision`. Then new sample artifacts and one budgeted real run. No Risk Registrar, no folder command, no reprocessing of artifacts that produced records.
- **Inputs:** [007-governor-inputs.md](007-governor-inputs.md) holds the three new sample artifacts and the expected work orders and records.

**This handoff has three parts, 7A, 7B and 7C.** Each part ends with green tests, the docs for what it built, a `dev/STATUS.md` update and its own commits, so the work can stop after any part without leaving the branch half done. Miguel asks for one part at a time; plan and build only the part he names.

---

## 1. Context

Today `record-decision ART-0001` drafts the single most significant decision in an artifact, and a pipeline stand-in marks it `processed`. Real meetings hold several decisions, a risk or two and some open questions, so all but one decision is lost. The Governor removes that limit (ADR-0004, ADR-0006, `docs/architecture.md`, Data flow step 2).

Reuse, do not rebuild: `agents/registrar.py` (the drafting loop and `check_artifact`), `agents/comparator.py`, `core/write_rules.py`, `core/evidence.py` (`check_evidence`, `normalize_quote`, `normalize_text`), `core/prompts.py` (`retry_system_text`), `core/ledger.py`, `storage/json_files.py`, `storage/ledger_store.py` (its lost-update check is the model for the new store), and the body of `pipeline.record_decision`, which becomes the per-item step.

Read `AGENTS.md`, `dev/STATUS.md`, ADR-0006, ADR-0011, ADR-0014, ADR-0015, ADR-0017, ADR-0018 (Proposed, written for this handoff) and `docs/architecture.md` before planning.

**What Miguel and Claude decided (voice session and chat, 2026-10-31):**

1. **Item types:** the Governor finds decisions and risks, the two v0.1 registers. Only decisions are sent on; risk work orders are kept as *not routed* (no Risk Registrar yet) and the Ledger counts them. Proposals, open questions and action items are left out (ADR-0011).
2. **Register definitions:** each register brings a short definition of what belongs in it, as a versioned prompt file, and the Governor's prompt is built from them. Registers mapped to the PMBOK Guide keep its meaning; others, like the decision log, are extensions. This keeps the door open for a register configurator later (backlog).
3. **Work orders** carry the register and one to five evidence quotes, checked by code. The Decision Registrar gets a new prompt, `decision-registrar.v2`, that drafts the item the work order points to, and it **also carries the known prompt fixes** (`decided_by` from the attendee list, unsupported `impacts`, invented `rationale` and `alternatives`). Each fix is listed in the prompt, and v1 and v2 can be compared on the evaluation set later.
4. **Same artifact, several items:** orders run one after another, so a later item is compared with records an earlier one just wrote. The Governor's prompt asks it to return one item per thing; code and the Comparator are the safety nets: two items that share a quote fail the check and the retry asks for one item, and a split that shares no quote becomes a reaffirmation of the first item's record.
5. **Partial results:** the Governor's checked work orders are saved in a work orders file, and each order is marked when it finishes (checkpointing). A rerun after a provider error reuses the file, skips finished orders and makes no new Governor call.
6. **Nothing to record:** no work orders means `processed` with zero records. This settles the backlog question of how a Registrar reports "nothing to record": it never has to.
7. **The command:** `process ARTIFACT_ID` replaces `record-decision`. The folder command waits for a later step.
8. **Ledger:** transitions are made by `governor`; the entry records the Governor's model, prompt version, definition versions, attempts and the work orders found per register.
9. **Cost and safety:** one Governor call per artifact, with thinking enabled like the other agents. A setting, `KA_GOVERNOR_MAX_ITEMS` (default 10), limits the work orders per artifact. Above it, code drafts nothing and marks the artifact **`held`** for review; nothing is cut silently. The Operator (human in the loop) approves with `release`, and the saved work orders then run, all of them. This is a security control against runaway cost and memory poisoning, not only a trial-key guard.
10. **Placeholder labels:** a work order's label is built by code from its first quote, so everything in the work orders file is verified artifact text. The record's real title comes from the Registrar's draft.
11. **Schema versions:** a change that keeps every existing file valid (a new optional field, a new allowed value) is a minor version. ADR-0011 is amended to say so, so the Ledger entry schema becomes 1.2, not 2.0.

**Claude's proposals inside that frame (Miguel confirms them when he approves each part's plan):**

- Code sorts work orders by where their earliest quote appears in the artifact, so the run order follows the meeting and does not depend on the model or on which quote it lists first.
- Two work orders in the same register may not share a quote (one contains the other after normalization): that is one item returned twice, and it fails the check, with one retry.
- A draft must have at least one quote that matches a work order quote (one contains the other after normalization), so the Registrar cannot draft a different decision.
- The limit counts routed work orders only: not-routed orders cost no calls.
- A choice about how to respond to a risk belongs with the risk (the decision-log definition says so), as in the PMBOK Guide's risk register.
- The work orders file is the single place where per-order results live. The Ledger's `produced` and `rejected` lists are rebuilt from it at the end of every run, so a Ledger left behind by an interruption is corrected by the next run.
- A rerun (from `failed`, or from `processed` with nothing produced) runs every routed order that is not recorded: pending ones, and rejected ones, as reruns do today. Continuing an interrupted run (the Ledger still says `accepted`) runs only pending orders, so a crash never changes what a finished order decided.
- Not-routed orders keep their quotes in the work orders file. Whether the Risk Registrar drafts from them later is that handoff's decision.

**Already committed on this branch (Claude wrote them, Miguel committed them):** this handoff and its inputs file; `prompts/core/governor.v1.md`, `prompts/core/governor-retry.v1.md`, `prompts/project-management/decision-registrar.v2.md` and the two definitions in `prompts/project-management/definitions/`; ADR-0018 (Proposed); the ADR-0011 amendment; backlog and status updates. Do not modify them. If you find a problem, raise it in your plan.

## 2. How to work on each part

1. **Plan first.** Read this whole document, then reply with a short plan for the part Miguel names: files to create or change, anything that does not fit the existing code, and the commits. **Wait for Miguel's approval.**
2. Small commits, tests in the same commit as the code. `ruff check`, `ruff format --check` and `pytest` before each commit. Trailers copied from the code block in `AGENTS.md`.
3. **No test may call the network.** The real run (7C) happens only after Claude's review and Miguel's go.
4. Ask instead of guessing; add open points to `dev/backlog.md` under *Open questions*.
5. End each part by updating `dev/STATUS.md` and reporting, with a **Cohere notes** section. Then stop.

## 3. Agreed design

### 3.1 The flow

```
process ART-0006
  1. Checks, no call: Ledger status, supersession links, records citing the artifact,
     and whether a work orders file exists
  2. No work orders file: the Governor reads the artifact      1 or 2 chat calls
       rejected ──► processed, rejected item (stage "governor"), no file
       accepted ──► write work-orders/ART-0006.json (all orders, sorted)
       more routed orders than KA_GOVERNOR_MAX_ITEMS ──► held, nothing drafted, stop
     A work orders file exists: use it, no Governor call
  3. For each routed order that is not recorded, in order:
       Decision Registrar drafts (v2, with the work order)    1 or 2 chat calls
       Comparator compares, code applies the write rule        as in handoff 006
       write: records, then views, then the order's result in the work orders file
  4. Ledger: processed (or failed on a provider error), produced and rejected rebuilt
     from the work orders file, the Governor block, by "governor"
```

A provider error (other than a configuration error) at any step gives `failed` with the results so far, and the error is raised again (exit 3). Not-routed orders are skipped in step 3.

### 3.2 Register definitions

`RegisterSpec` gains `definition: str | None = None`: the name of a prompt file, for example `project-management/definitions/decision-log.v1`. `DECISION_LOG` and `RISK_REGISTER` name the committed files. Definitions are prompts: immutable once cited (ADR-0014), loaded with `load_prompt`, version = file stem.

The Governor's system prompt is `governor.v1.md` with `{registers}` replaced by one block per register, in `REGISTERS` order, joined by a blank line:

```
### decision-log

<the definition text, stripped>
```

The Governor refuses at construction a prompt without `{registers}` and a register without a definition.

### 3.3 Work orders

**The Governor's reply** (`schemas/core/governor-reply.v1.json`, `x-version` 1.0, only keywords the Cohere reduction keeps or removes):

```json
{
  "type": "object",
  "properties": {
    "items": {
      "type": "array",
      "maxItems": 100,
      "description": "One item per distinct thing that fits a register, in the order they first appear. Empty when nothing fits.",
      "items": {
        "type": "object",
        "properties": {
          "register": { "type": "string", "description": "The register this item belongs to." },
          "evidence": {
            "type": "array", "minItems": 1, "maxItems": 5,
            "items": { "type": "string", "maxLength": 500 },
            "description": "Quotes copied word for word from the artifact that point to this item; the passage that states it first."
          }
        },
        "required": ["register", "evidence"],
        "additionalProperties": false
      }
    }
  },
  "required": ["items"],
  "additionalProperties": false
}
```

`governor_schema(specs)` in `core/schemas.py` returns it with `"enum"` set on `register` to the register names, like `draft_schema` inlines content. The 100 is a sanity bound, not the limit: the limit is a setting (3.8), so the model is never cut off silently by the schema.

**`validate_work_orders(reply, specs, artifact_text) -> ValidationResult`** in `core/validation.py`:

- schema errors;
- every quote passes `check_evidence`, path `$.items[i].evidence[j]`;
- two items in the same register share a quote (after `normalize_quote`, one contains the other; quotes within one item may overlap, for example a summary line that repeats part of a sentence): `$.items[j].evidence[k]: also quoted by item i in the same register; return one item for one thing`.

The count is **not** a validation error.

**After acceptance, code builds the work orders** (`core/work_orders.py`, pure): sort the items by the position of their earliest quote (the smallest position of any of its quotes, found with `normalize_quote` in `normalize_text(artifact)`; ties keep the model's order), number them from 1, and build each label with `placeholder_label(quote)`: whitespace collapsed, at most 60 characters, cut at a word boundary with `...` added when cut.

### 3.4 The Decision Registrar with a work order

- `registrar.user_message(artifact_text, work_order=None)`: unchanged without a work order. With one: the artifact block, a blank line, then `<work-order>`, the JSON `{"register": ..., "evidence": [...]}` (`ensure_ascii=False`, `indent=2`, every `<` escaped as `\u003c`, as in the Comparator), and `</work-order>`.
- `draft_record(..., work_order=None)` passes the order's quotes to `validate_draft(draft, spec, artifact_text, work_order_quotes=None)`. When given, a draft with no quote matching a work order quote gets `$.evidence: no quote matches the work order; draft the item the work order points to`, which the loop retries like any error.
- The retry prompt stays `registrar-retry.v1`, so the retry version is `decision-registrar.v2+registrar-retry.v1`.
- `decision-registrar.v1` stays in the repository: records cite it.

### 3.5 The work orders file (checkpoint)

One file per artifact, `<memory>/work-orders/ART-0006.json`, schema `schemas/core/work-orders.v1.json` (`x-version` 1.0), the same deterministic JSON writer as records, validated before every write and when read.

```json
{
  "schema_version": "1.0",
  "artifact_id": "ART-0006",
  "created_at": "2026-11-03T14:00:05Z",
  "updated_at": "2026-11-03T14:01:40Z",
  "run_id": "<the run that called the Governor>",
  "governor": {
    "model": "command-a-plus-05-2026",
    "prompt_version": "governor.v1",
    "attempts": 1,
    "definitions": ["decision-log.v1", "risk-register.v1"]
  },
  "max_items": 10,
  "orders": [
    {
      "number": 1,
      "register": "decision-log",
      "label": "Julie confirmed that the status paths per crop type stay as...",
      "evidence": ["Julie confirmed that the status paths per crop type stay as the board decided in April."],
      "state": "recorded",
      "produced": { "register": "decision-log", "record_id": "DEC-0003", "change": "reaffirmation", "...": "as a Ledger produced item" },
      "rejected": []
    },
    { "number": 3, "register": "risk-register", "label": "...", "evidence": ["..."], "state": "not-routed", "rejected": [] }
  ]
}
```

- `state`: `pending`, `recorded`, `rejected` or `not-routed`. `produced` (one Ledger `produced_record`) is present only when `recorded`. `rejected` lists Ledger `rejected_draft` items, each with its `run_id`, append-only.
- Define `produced` and `rejected` once: reference the Ledger schema's definitions if the validator can resolve them, or copy them with a test that the copies equal the Ledger's.
- Allowed changes (`storage/work_order_store.py`, `save_progress(old, new)`, lost-update check like `LedgerStore.save_transition`): `pending` or `rejected` to `recorded` or `rejected`; `recorded` and `not-routed` never change. Nothing else in the file changes except `updated_at`. `save_new` never overwrites.
- **Write order:** the work orders file is written once the Governor's reply is accepted, before any draft. For each order: the records (write rule as today), the views, then the order's result in the file. The Ledger is written once, at the end.
- **Guard before any call:** every change a recorded order makes adds exactly one history entry naming the artifact to each record it touches (`record_id`, and `related_id` for a supersession); every record history entry already requires `artifact_id`. So for each record in the register, the number of its history entries whose `artifact_id` is this artifact must equal the number of recorded orders that touch it. Otherwise stop before any call: "the work orders file is behind the records", naming the records, with the fix by hand. This catches an interrupted update or reaffirmation of a record an earlier order already touched (a split duplicate), which a check on record IDs alone would miss. Without a work orders file, the existing "Ledger is behind the records" guard applies unchanged.

### 3.6 Ledger entry schema 1.2

All additions keep 1.0 and 1.1 entries valid (ADR-0011, amended):

- `status` gains `held`. It has a stored copy.
- Transitions: `accepted`, `failed` or `processed` to `held` by `governor`; `held` to `accepted` by `operator` (with a reason). Every transition `pipeline` makes today is made by `governor` from now on; `pipeline` stays valid in history.
- History: a `held` entry needs a `run_id` and a `reason`.
- Entry-level `governor` (optional): `{model, prompt_version, attempts, definitions: [...], run_id, work_orders: [{register, count, routed}]}`, present once the Governor's reply was accepted.
- `produced_record` gains `work_order` (integer, at least 1). `produced` may be non-empty only for `processed`, or for `failed` when the entry has a `governor` block (results before the error). A `held` entry never lists records (3.7), and neither does the `accepted` entry after its release.
- `rejected_draft`: `stage` gains `governor`; `register` becomes required unless the stage is `governor`; it gains `work_order`.
- **`rejected` is kept across every later transition** once a run has listed an item: on `failed`, `held`, and the `accepted` entry after a release (today's rule allows it only on `processed`, or `failed` after an earlier `processed`; replace that rule).
- The `governor` block may appear on `processed`, `failed`, `held` and `accepted` (after a release), and is kept once set.
- The check that a rejected item's `run_id` belongs to a `processed` history entry applies only to items without `work_order`. Items with `work_order` come from the work orders file, whose runs may have ended `failed` or been interrupted.
- `processed` stays final once it lists records.
- **Rebuilding the lists:** `produced` = each recorded order's `produced` plus its `work_order`, in order number. `rejected` = the entry's earlier items that have no `work_order` (from before the Governor, or Governor-stage rejections), then each order's rejected items with its `work_order`.

### 3.7 Which artifacts `process` accepts, which orders run, and release

**Statuses:**

- `accepted` and `failed`: yes.
- `processed` with nothing produced: yes if there is no work orders file (the Governor was rejected), if the file has a routed order that is `pending` or `rejected`, or if the Ledger is behind the file (below). Otherwise refuse, before any call, with the reason: "the Governor found nothing to record in ART-0008", or "ART-0010 has no work orders for a register with a Registrar (1 risk-register, not routed)"; either way, reprocessing needs its own design.
- `held`: refuse, naming `release`. `quarantined` and `rejected`: as today.

**Which orders run:** when the Ledger says `accepted` (a first run, or one interrupted before its Ledger write), only `pending` orders. When it says `failed` or `processed` (a rerun), `pending` and `rejected` orders. `recorded` and `not-routed` orders never run.

**Nothing left to draft still finishes:** if no order would run, but the work orders file has results the Ledger does not list (a run whose Ledger write was lost), `process` writes the Ledger from the file with no call: `processed` by `governor`, reason `Rebuilt from the work orders file`. That is how a Ledger left behind is corrected.

**Zero routed orders** (nothing found, or only not-routed orders): `processed` with zero records, exit 0. The output says what was found, for example `The Governor found 1 work order, none for a register with a Registrar (1 risk-register, not routed): nothing to record yet.`

**Release:** `release ART-0009 --reason TEXT` on a `held` artifact makes it `accepted` by `operator`, with no Sensor checks (its bytes were already accepted). A quarantined artifact is released as today.

**The hold, tied to its work orders file:** the `held` history entry carries the Governor's `run_id`, the same as the file's `run_id`. A file counts as released when the Ledger history has a `held` entry with that `run_id`, followed by an `accepted` entry by `operator`. Before any draft, a file with no `recorded` or `rejected` order yet, more routed orders than **its own** `max_items`, and no release is marked `held` (again) with no call, for example after a crash between writing the file and writing the Ledger. A file made by a later Governor run (say, after the old file was deleted by hand) has a new `run_id`, so an earlier release does not cover it. Changing the setting later never holds a file whose orders have started.

### 3.8 The limit (a security control)

`KA_GOVERNOR_MAX_ITEMS`: a whole number, at least 1, default 10, read before any call by `GovernorSettings.from_env()` (exit 2 on a bad value, naming the variable). Reuse the Comparator's whole-number reader; move it to a shared module if that is cleaner. Add it to `.env.example`, commented out with a one-line explanation. The work orders file records `max_items` as it was, and the hold check uses that value (3.7). The held reason is written by code, for example: `The Governor found 12 work orders for registers with a Registrar, more than KA_GOVERNOR_MAX_ITEMS (10); nothing was drafted. Review the artifact, then release it.`

### 3.9 What is stored where

| What | Where |
|---|---|
| Work orders (register, label, verified quotes), their state and per-order results | Work orders file |
| Governor model, prompt and definition versions, attempts, counts per register | Ledger `governor`, and the work orders file |
| Records produced and drafts rejected, with their work order | Ledger, rebuilt from the work orders file |
| Every call's units (agent `governor` for the Governor's calls) | Event log |
| The Comparator's reason | Terminal only, as today |

## 4. Part 7A: the Governor and the second Registrar prompt (offline)

No pipeline or CLI change. Agents never import storage or `knowledge_automata.llm.*` submodules (the existing test enforces it).

**Files:** `schemas/core/governor-reply.v1.json`; `core/registers.py` (`definition`); `domains/project_management/registers.py` (both definitions); `core/schemas.py` (`governor_schema`); `core/validation.py` (`validate_work_orders`, `validate_draft` with `work_order_quotes`); `core/work_orders.py` (`WorkOrder`, sorting, `placeholder_label`); `agents/governor.py`; `agents/registrar.py` (work order in the user message and the check).

**`agents/governor.py`:**

- `Governor(agent="governor", prompt, retry_prompt, registers: tuple[tuple[RegisterSpec, Prompt], ...], max_attempts=2)` with `system_text()` (3.2) and `retry_version` (`governor.v1+governor-retry.v1`).
- `find_work_orders(governor, llm, artifact_text, *, artifact_id) -> GovernorOutcome`: `check_artifact`, the user message from `registrar.user_message(artifact_text)`, `chat_json` with `governor_schema`, `CallContext("governor", artifact_id, version)`, `validate_work_orders`; one retry with the errors (the rendered system text, a blank line, the retry prompt); `LLMResponseError` counts as an attempt; every other `LLMError` propagates. A shared retry helper with `registrar.py` is welcome only if `registrar.py`'s behavior and tests stay unchanged.
- `GovernorOutcome`: work orders (sorted and numbered), errors, attempts, model, prompt version, definition versions, usage per call, error type, `accepted`.

**Tests (fakes only):** the rendered system text for both registers; refusal without `{registers}` or without a definition; the schema's register enum and that `to_cohere_schema` accepts it; each validation error (quote not found, quote too short, unknown register, a shared quote in the same register, including one quote contained in another; a shared quote in different registers passes); an empty list is accepted; sorting by earliest quote (an item whose first-listed quote is from a summary at the end still sorts by its earlier quote) and the tie rule; `placeholder_label` short, long, and with line breaks; one retry then rejection; an unusable response counts as an attempt; retry prompt version; `LLMRateLimitError` propagates; events carry agent `governor`. Registrar: the user message with a work order is the artifact block plus valid JSON inside the tags, with no raw `<`; without one it is byte-for-byte unchanged; the match check passes on containment either way and fails otherwise; the existing Registrar tests pass unchanged. `decision-registrar.v2`, `governor.v1`, `governor-retry.v1` and both definitions load from the wheel (`tests/test_prompts.py`).

**Docs:** `dev/STATUS.md`. **Commits:** `feat: add register definitions and the work order checks`, then `feat: add the Governor (orchestrator) agent`, then `feat: let the Decision Registrar draft from a work order`, then `docs: update status after part 7A`.

## 5. Part 7B: the `process` command

**Files:** `schemas/core/ledger-entry.v1.json` (1.2, 3.6); `schemas/core/work-orders.v1.json`; `core/ledger.py` and `core/validation.py` (statuses, transitions, history and list rules); `core/work_orders.py` (the file: new, order results, rebuilding the Ledger lists); `storage/work_order_store.py`; `pipeline.py`; `cli.py`; `.env.example`.

**`pipeline.py`:**

- `process_artifact(*, artifact_id, memory, llm, now, comparator_settings, governor_settings) -> ProcessOutcome`, following 3.1 and 3.5 to 3.7. The per-order step is today's `record_decision` body (draft with the work order, compare, write rule, views), run once per order. `REGISTRARS = {"decision-log": decision_registrar}`; orders for any other register are `not-routed`.
- `decision_registrar()` uses `decision-registrar.v2`. `record_decision` and its stand-in role go; `recordable_entry` becomes the check list in 3.7.
- One place still sets the thinking default for every agent (today `record_decision_settings`; rename it if the name no longer fits).
- `release_artifact` handles `held` (3.7).
- `ProcessOutcome`: the run ID, the Governor outcome (or that saved work orders were used), each order's outcome (draft, comparison, change, records, filled and ignored fields, or why it was skipped), the counts, and the Ledger entry.

**`cli.py`:**

- `process ARTIFACT_ID [--memory]` replaces `record-decision` (remove the old command and move its tests). Exit codes: 0 when every routed order that ran was recorded, or there was no routed order to run; 1 when the Governor or any order was rejected, or the artifact was held; 2 and 3 as today.
- Output, in order (wording is Copilot's choice where not shown):

```
Run ID: <uuid>
Found 4 work orders in ART-0006 in 1 attempt (model ..., prompt governor.v1, definitions decision-log.v1, risk-register.v1, thinking enabled): 3 decision-log, 1 risk-register (no Registrar yet, not routed)
Work order 1 of 4, decision-log: "Julie confirmed that the status paths per crop type stay as..."
  Drafted in 1 attempt (prompt decision-registrar.v2)
  Compared with 3 active decisions; candidates: DEC-0003 (0.71), DEC-0001 (0.02)
  Classified as reaffirmation of DEC-0003 in 1 attempt (prompt decision-comparator.v1): <reason>
  Reaffirmed DEC-0003 (revision 2): added 1 source
Work order 3 of 4, risk-register: not routed (no Registrar yet)
...
Recorded 3 of 3 routed work orders; 0 rejected; 1 not routed
Billed: governor ...; drafts ...; comparisons ...; embed ...; rerank ...
Index: .../decision-log.md
```

- With saved work orders: `Using 4 saved work orders from run <uuid>; the Governor was not called.` A rerun says so first, as today. Held: the reason, and `release` to continue. Nothing found: `The Governor found nothing to record in ART-0008.`
- `ledger` shows `held` and appends the changes as today, plus the not-routed count.
- The module docstring keeps the rule: output never holds settings, keys or prompts; it prints the Comparator's reason and the placeholder labels, which are verified artifact text.

**Tests (end to end in `tmp_path`, fakes only):** an artifact with two decisions and a risk records both decisions and lists the risk as not routed; nothing found; Governor rejected, then a rerun calls the Governor again; a provider error on the second order leaves `failed` with the first order's record listed, and the rerun makes no Governor call and drafts only the second; a crash after the records but before the order result is detected before any call; a Ledger left behind the work orders file is rebuilt by the next run; more orders than the limit: `held`, no draft, the file saved; `process` refuses `held`; `release` makes it `accepted` and `process` then runs every order with no Governor call; a file over the limit with no release is held again with no call, judged by the file's `max_items`, not the current setting; a release covers only the file whose `run_id` was held; Governor rejected, then a rerun that is held, then released: the earlier Governor-stage rejected item survives every transition; order 1 rejected and order 2 failing on a provider error gives a valid `failed` entry, and the rerun retries both; a run interrupted after order 1 was rejected continues with order 2 only; a run interrupted after every order was recorded, before its Ledger write, is finished by the next `process` with no call (also when the entry was `processed` with nothing produced before); an interrupted reaffirmation of a record an earlier order already updated is caught by the history count; only not-routed orders: `processed`, exit 0, and a rerun is refused with its reason; a split duplicate becomes a reaffirmation of the record from the same artifact; a rejected order and a recorded order in one run: `processed`, final; bad `KA_GOVERNOR_MAX_ITEMS` exits 2 with no call; Ledger 1.2 accepts the 1.0 and 1.1 sample entries; every new transition and list rule, allowed and refused; the store's refusals (stale file, changed evidence, `recorded` changed); no output contains artifact text other than the title, the labels and the Comparator's reason.

**Docs:** ADR-0006 (statuses: `held`; the Governor owns `processed`, `failed` and `held`) and ADR-0015 (transitions, `held`, `failed` with results, the work orders file), each marked amended in the index; `docs/architecture.md` text only (Roles: the Governor is built; Data flow steps 2 and 5 and the paragraph on what runs today; the memory folder layout gains `work-orders/`; Patterns: checkpointing for resumable runs); `README.md` outside the diagram block (Try it uses `process`; Status); `dev/backlog.md`; `dev/STATUS.md`. **Do not edit Mermaid blocks or their markers**; Claude refreshes the diagrams and the guide.

**Commits:** `feat: add Ledger entry schema 1.2 and the held status`, `feat: add the work orders file`, `feat: process artifacts through the Governor`, `feat: release held artifacts`, `docs: amend ADR-0006 and ADR-0015, update architecture, README and backlog`, `docs: update status after part 7B`.

## 6. Part 7C: evidence

**Before 7A, done on 2026-10-31:** Miguel ran Claude's throwaway spike (`runtime/diagnostics/spike_governor.py`, git-ignored) on ART-0001 to ART-0008 with the real prompts (11 calls, thinking enabled). Every reply was valid JSON and every quote passed the evidence check. The counts matched on 7 of 8 artifacts: on ART-0004 the Governor returned the rationale sentence ("the board chose a single ladder") as a second decision, so `governor.v1` gained one line on passages that only explain an item. Before 7A, Miguel runs the spike again on ART-0004, ART-0006 and ART-0007 (3 calls) to check the fix and that nothing else changed. ART-0007's split trap passed: each decision was one item, quoting its section and the summary. The three v2 drafts for ART-0006 invented no rationale or alternatives, and `decided_by` was "the board" or absent.

**7C, after Claude's review of 7B and Miguel's go:**

1. Save the three artifacts from the inputs file in `runtime/inbox/` (Claude may already have put them there; check their SHA-256 against the inputs file).
2. Run, one artifact at a time, reading each output before the next:

```powershell
uv run knowledge-automata ingest runtime/inbox/project-board-2026-05-26.md --artifact-date 2026-05-26 --memory examples/sample-project
uv run knowledge-automata ingest runtime/inbox/tech-sync-2026-06-09.md --artifact-date 2026-06-09 --memory examples/sample-project
uv run knowledge-automata ingest runtime/inbox/status-update-2026-06-16.md --artifact-date 2026-06-16 --memory examples/sample-project
uv run --env-file .env knowledge-automata process ART-0006 --memory examples/sample-project
uv run --env-file .env knowledge-automata process ART-0007 --memory examples/sample-project
uv run --env-file .env knowledge-automata process ART-0008 --memory examples/sample-project
uv run knowledge-automata views --memory examples/sample-project --check
```

3. **Budget:** ART-0006 and ART-0007 have three routed items each: 1 Governor call plus about 5 calls per item, so about 16 each; ART-0008 is 1 call. About 33 calls, more with retries or a split duplicate. **Stop at 50** and report.
4. **Rules (as in handoff 006):** stop on a rejection or a provider error and diagnose before any rerun; reruns only where the code allows them, each with Miguel's go; commit what comes out unedited (copies, Ledger entries, work orders files, records, views) in one commit; paste the full output into the pull request description; a result that differs from the expected table is a finding for the backlog, not something to fix by editing files.

**Docs:** the sample project README (the three artifacts, the expected and actual tables, the run IDs, and that the work orders files are part of the memory); ADR-0018 becomes Accepted, with any change the run calls for; `dev/STATUS.md`. **Commits:** `feat: process ART-0006 to ART-0008 in the sample project`, then `docs: record the Governor real run`. Claude refreshes the diagrams and the guide on the branch; Miguel adds the credits row to `dev/costs.md` as the last commit before merging. Suggested pull request title: `feat: add the Governor (orchestrator) (handoff 007)`.

## 7. Done when

- Each part's tests pass, with `ruff check`, `ruff format --check` and `pytest` green locally and in CI (`ci-ok`), including Python 3.15.
- No test touches the network; only `llm/cohere_adapter.py` imports `cohere`; agents import neither storage nor `knowledge_automata.llm.*` submodules.
- The docs listed in each part are updated, no Mermaid block was edited, and nothing was read from or copied from Chronicle. `.env` stays untracked.
- After 7C: the real run is committed unedited, with its output in the pull request description.

## 8. Out of scope

The Risk Registrar and drafting not-routed orders; the folder command; reprocessing artifacts that produced records (a `correction` change); Operator actions on held artifacts other than release (reject, split again); semantic guardrails and the escalation checker; a register configurator; a token budget; the diagrams, their copies and the guide (Claude).
