# Handoff 002: Decision log and Risk register schemas

- **From:** Claude (discovery, architecture, review)
- **To:** Copilot (implementation)
- **Owner and approver:** Miguel
- **Date:** 2026-10-25
- **Branch:** `feat/register-schemas`
- **Revised:** 2026-10-25, after Copilot's plan review: `"type": "string"` added to every `enum` field, and `"x-version": "1.0"` added to the record envelope. Versions stay 1.0, because nothing has been released. No other changes.
- **Scope:** the record schemas for the decision log and the risk register, the core record envelope, the Registrar draft and Comparator result formats, and the code that validates them. No LLM calls, no storage, no agents.

---

## 1. Context

Handoff 001 delivered the scaffold (PR #1) and PR #2 the CI follow-ups. This handoff delivers the contract every role must honour: the JSON Schema files that define what a record is. Miguel and Claude designed them together before implementation (P1, P2), because the schemas are an architecture deliverable, not something to generate while coding.

Read `AGENTS.md`, `dev/STATUS.md`, ADR-0005, ADR-0006, ADR-0007 and ADR-0009 before planning.

**Already committed by Miguel on this branch:** this handoff, the five schema files in `schemas/` (section 5) and the housekeeping updates to `dev/STATUS.md`, `dev/costs.md` and `dev/tool-feedback.md`. Do not modify this handoff. The schema files are the agreed design: if you find a problem in them, raise it in your plan instead of changing them silently.

## 2. How to work on this task

1. **Plan first.** Read this whole document, then reply with a short plan: files you will create or change, the lock file tool you propose (6.1), how schemas are packaged (6.2) and the commit sequence. **Wait for Miguel's approval** before writing files.
2. **Check Cohere compatibility against Cohere's docs** (6.7). Anything surprising goes in `dev/tool-feedback.md`.
3. Implement in small commits (section 9), with tests in the same commit as the code they cover.
4. If anything here is ambiguous or seems wrong, ask instead of guessing, and add it to `dev/backlog.md` under *Open questions*.
5. Finish by updating `dev/STATUS.md` and reporting what you did and anything you were unsure about.

## 3. Agreed design

### 3.1 Code owns the envelope, the LLM drafts only `content`

Every stored record has two parts:

- **Envelope** (`schemas/core/record.v1.json`), owned by code: ID, register, schema version, record status, revision, timestamps, sources, relations and history (including the model and prompt version per revision).
- **Content** (`schemas/project-management/decision.v1.json` or `risk.v1.json`), drafted by a Registrar (specialist record keeper) and validated against its register's content schema.

LLM output only ever lands in `content`. This extends "code assigns record IDs, never the LLM" to the whole envelope, enforced by the shape of the record rather than by discipline. An LLM that tries to set an ID is rejected by `additionalProperties: false`.

### 3.2 Evidence quotes, checked by code

A Registrar returns a draft (`schemas/core/draft.v1.json`): the content plus `evidence`, a list of quotes copied word for word from the artifact. Code checks that every quote really appears in the artifact before the record can be stored. This is cheap, deterministic and catches the most dangerous failure: a record invented from nothing (P10, with evidence for P11 built in). Verified quotes become the record's `sources`, which later double as citations for the Oracle (query interface).

- Normalize both the quote and the artifact text before comparing (6.6), so a valid quote does not fail over formatting.
- Any failed quote rejects **that record only**, not the whole artifact. The rejection is logged.

### 3.3 Links between records are proposed by the LLM and checked by code

When the Comparator (reconciliation) says "this supersedes DEC-0004", that is an LLM judgement, so code does not trust it blindly. The Comparator returns a result (`schemas/core/reconciliation.v1.json`) with a classification and a target ID. Code checks that the target is one of the candidates it was shown, belongs to the same register, and that the transition is allowed for that register (6.5). Only then does code write `relations` and `history`.

### 3.4 One source of truth, two validation passes

- The JSON Schema files in `schemas/` (draft 2020-12) are the contract. Code validates against them directly with the `jsonschema` library. No Pydantic models in this handoff; if typed models are added later, a test must keep them in sync with the schema files.
- The draft and reconciliation schemas are sent to the LLM provider as the structured-output format. They use only a small keyword subset (6.7). Validation-only keywords (`maxLength`, `minItems`, `maxItems`) and annotations (`$schema`, `$id`, `x-version`, `x-pmi-mapping`) will be removed by the provider adapter in a later handoff, and code validates the full schema after the response arrives.
- The record envelope is never sent to a provider, so it may use any 2020-12 keyword.

### 3.5 Nothing made up

- Optional content fields are omitted when the artifact does not state or clearly imply them. No nulls, no "unknown".
- Derived values are computed by code and not stored: for example the risk score (probability times impact on a 1 to 5 scale) is computed when a view or sort needs it.

### 3.6 Decision log scope

- Only decisions the group actually made. Rejecting an option is a decision ("Do not use supplier B for the pilot").
- Proposals and open questions without an outcome are dropped in v0.1. In PMI terms they belong in the issue log, a later Registrar (backlog item in 8.5).
- Decisions have no status in `content`. Lifecycle (`active`, `superseded`) is set by code in the envelope.

### 3.7 IDs and versions

- IDs are a register prefix plus a sequence: `DEC-0001`, `RSK-0001`, and `ART-0001` for artifacts. Assigned by code.
- The major version is in the schema file name (`decision.v1.json`). The full version (`MAJOR.MINOR`) is in the schema's `x-version` and is copied into each record's `schema_version`. Adding an optional field is a minor change; anything else is a major change and needs a new file and a migration.

### 3.8 Write rules (documented now, implemented with the Registrars)

| Classification | Decision log | Risk register |
|---|---|---|
| new | Create the record. | Create the record. |
| update | Fills only fields that are empty in the existing record. Values for fields that are already filled are ignored and the differences logged as warnings (a real change of substance is a supersession). | Fields present in the draft overwrite existing values; fields absent from the draft are kept (the LLM cannot remove a field in v0.1). |
| reaffirmation | Adds the verified quotes as new sources and a history entry. Draft content is ignored. | Same as decision log. |
| supersession | Creates a new record with `relations.supersedes`; the old record becomes `superseded` with `relations.superseded_by` and a `superseded` history entry. A reversal is a new decision that supersedes the old one. | Not allowed in v0.1 (the Comparator should return update). |

Every change increments `revision` and appends a history entry. Only `active` records can be the target of update, reaffirmation or supersession. A risk whose status becomes `occurred` stays in the register; linking it to an issue-log record comes later.

This handoff implements the checks in 6.5, not the write rules themselves; those come with the Registrars and storage.

## 4. Target structure

New and changed files (existing files not shown):

```
schemas/                                   # already committed by Miguel (section 5)
├── core/
│   ├── record.v1.json
│   ├── draft.v1.json
│   └── reconciliation.v1.json
└── project-management/
    ├── decision.v1.json
    └── risk.v1.json
src/knowledge_automata/
├── core/
│   ├── __init__.py
│   ├── registers.py                       # RegisterSpec (domain-neutral)
│   ├── schemas.py                         # loading schema files, building draft schemas
│   ├── validation.py                      # record, draft and reconciliation validators
│   └── evidence.py                        # quote normalization and check
└── domains/
    ├── __init__.py
    └── project_management/
        ├── __init__.py
        └── registers.py                   # DECISION_LOG and RISK_REGISTER specs, risk semantic check
tests/
├── fixtures/                              # fictional records, drafts and one artifact text
├── test_schemas.py
├── test_record_validation.py
├── test_draft_validation.py
├── test_evidence.py
└── test_reconciliation.py
docs/decisions/0011-record-model-and-write-rules.md
```

Remove `schemas/.gitkeep`. Module names are a suggestion; propose alternatives in your plan if they fit better.

## 5. Schema files

These are committed by Miguel. They are reproduced here so the handoff is a complete record of the design.

### 5.1 `schemas/core/record.v1.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:knowledge-automata:schema:core:record:v1",
  "x-version": "1.0",
  "title": "Record envelope",
  "description": "Every stored record. Code owns every field here. Only 'content' holds LLM-drafted data, and it is validated separately against the content schema of the record's register. Never sent to an LLM provider.",
  "type": "object",
  "properties": {
    "id": { "$ref": "#/$defs/record_id" },
    "register": {
      "type": "string",
      "pattern": "^[a-z][a-z0-9-]*$",
      "description": "Register name, for example decision-log or risk-register."
    },
    "schema_version": {
      "type": "string",
      "pattern": "^[0-9]+\\.[0-9]+$",
      "description": "Version (MAJOR.MINOR) of the content schema the content was validated against."
    },
    "record_status": {
      "type": "string",
      "enum": ["active", "superseded"],
      "description": "Record lifecycle, set by code. Domain states (for example a risk being open or closed) live in content."
    },
    "revision": { "type": "integer", "minimum": 1 },
    "created_at": { "type": "string", "format": "date-time" },
    "updated_at": { "type": "string", "format": "date-time" },
    "content": {
      "type": "object",
      "description": "Register-specific content drafted by a Registrar (specialist record keeper)."
    },
    "sources": {
      "type": "array",
      "minItems": 1,
      "items": { "$ref": "#/$defs/source" }
    },
    "relations": { "$ref": "#/$defs/relations" },
    "history": {
      "type": "array",
      "minItems": 1,
      "items": { "$ref": "#/$defs/history_entry" }
    }
  },
  "required": [
    "id",
    "register",
    "schema_version",
    "record_status",
    "revision",
    "created_at",
    "updated_at",
    "content",
    "sources",
    "history"
  ],
  "additionalProperties": false,
  "if": {
    "properties": { "record_status": { "const": "superseded" } },
    "required": ["record_status"]
  },
  "then": {
    "required": ["relations"],
    "properties": { "relations": { "required": ["superseded_by"] } }
  },
  "$defs": {
    "record_id": {
      "type": "string",
      "pattern": "^[A-Z]{3}-[0-9]{4,}$",
      "description": "Register prefix and sequence number, for example DEC-0001. Assigned by code."
    },
    "artifact_id": {
      "type": "string",
      "pattern": "^ART-[0-9]{4,}$",
      "description": "Artifact Ledger ID, for example ART-0001. Assigned by code."
    },
    "source": {
      "type": "object",
      "description": "One verified quote from one artifact. A record has one source entry per verified quote.",
      "properties": {
        "artifact_id": { "$ref": "#/$defs/artifact_id" },
        "artifact_date": {
          "type": "string",
          "format": "date",
          "description": "Artifact date copied from the Artifact Ledger, when known."
        },
        "excerpt": {
          "type": "string",
          "minLength": 1,
          "maxLength": 500,
          "description": "The quote as drafted, after it passed the evidence check."
        },
        "added_at": { "type": "string", "format": "date-time" }
      },
      "required": ["artifact_id", "excerpt", "added_at"],
      "additionalProperties": false
    },
    "relations": {
      "type": "object",
      "description": "Links between records. Proposed by the Comparator (reconciliation), checked and written by code.",
      "properties": {
        "supersedes": {
          "type": "array",
          "minItems": 1,
          "items": { "$ref": "#/$defs/record_id" }
        },
        "superseded_by": { "$ref": "#/$defs/record_id" }
      },
      "additionalProperties": false
    },
    "history_entry": {
      "type": "object",
      "description": "One change to the record. Append-only.",
      "properties": {
        "revision": { "type": "integer", "minimum": 1 },
        "at": { "type": "string", "format": "date-time" },
        "change": {
          "type": "string",
          "enum": ["new", "update", "reaffirmation", "supersession", "superseded"],
          "description": "'supersession' is written on the new record; 'superseded' on the record it replaces."
        },
        "artifact_id": { "$ref": "#/$defs/artifact_id" },
        "fields": {
          "type": "array",
          "items": { "type": "string" },
          "description": "Content fields set or changed in this revision."
        },
        "related_id": {
          "$ref": "#/$defs/record_id",
          "description": "The other record in a supersession."
        },
        "model": {
          "type": "string",
          "description": "Model that drafted this revision, if an LLM was involved."
        },
        "prompt_version": {
          "type": "string",
          "description": "Version of the Registrar prompt used, if an LLM was involved."
        }
      },
      "required": ["revision", "at", "change", "artifact_id"],
      "additionalProperties": false
    }
  }
}
```

### 5.2 `schemas/core/draft.v1.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:knowledge-automata:schema:core:draft:v1",
  "x-version": "1.0",
  "title": "Registrar draft",
  "description": "What a Registrar (specialist record keeper) returns for one work order. At runtime, code replaces the 'content' placeholder with the content schema of the target register.",
  "type": "object",
  "properties": {
    "content": {
      "type": "object",
      "description": "Placeholder for the register's content schema."
    },
    "evidence": {
      "type": "array",
      "minItems": 1,
      "maxItems": 5,
      "items": { "type": "string", "maxLength": 500 },
      "description": "Quotes copied word for word from the artifact that support the content. Copy the exact words; do not paraphrase, translate or join separate sentences. Prefer one short sentence per quote."
    }
  },
  "required": ["content", "evidence"],
  "additionalProperties": false
}
```

### 5.3 `schemas/core/reconciliation.v1.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:knowledge-automata:schema:core:reconciliation:v1",
  "x-version": "1.0",
  "title": "Reconciliation result",
  "description": "What the Comparator (reconciliation) returns for one work order: how the new input relates to existing records. This is an LLM judgement; code checks it before acting on it.",
  "type": "object",
  "properties": {
    "classification": {
      "type": "string",
      "enum": ["new", "update", "reaffirmation", "supersession"],
      "description": "new: no existing record covers this. update: adds to or changes an existing record without replacing it. reaffirmation: restates an existing record with nothing new. supersession: replaces an existing record with a different one."
    },
    "target_id": {
      "type": "string",
      "description": "ID of the existing record this input relates to. Must be one of the candidate IDs provided. Omit when classification is new."
    },
    "reason": {
      "type": "string",
      "maxLength": 300,
      "description": "One or two sentences explaining the classification."
    }
  },
  "required": ["classification", "reason"],
  "additionalProperties": false
}
```

### 5.4 `schemas/project-management/decision.v1.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:knowledge-automata:schema:project-management:decision:v1",
  "x-version": "1.0",
  "x-pmi-mapping": "Decision log: a widely used project-management practice, not an artifact named in the PMBOK Guide, Eighth Edition (see ADR-0007).",
  "title": "Decision log entry",
  "description": "One decision the group actually made, including a decision to reject an option. Proposals and open questions without an outcome are not decisions. Use only information stated or clearly implied in the artifact; omit any optional field that is not.",
  "type": "object",
  "properties": {
    "title": {
      "type": "string",
      "maxLength": 120,
      "description": "Short label for the decision, about ten words or fewer."
    },
    "statement": {
      "type": "string",
      "maxLength": 500,
      "description": "What was decided, as one plain sentence. A decision not to do something is valid, for example: Do not use supplier B for the pilot."
    },
    "context": {
      "type": "string",
      "maxLength": 1000,
      "description": "The question or problem the decision answers."
    },
    "rationale": {
      "type": "string",
      "maxLength": 1000,
      "description": "Why this option was chosen, as stated in the artifact."
    },
    "alternatives": {
      "type": "array",
      "maxItems": 10,
      "items": { "type": "string", "maxLength": 200 },
      "description": "Options that were considered and not chosen."
    },
    "decided_by": {
      "type": "array",
      "maxItems": 20,
      "items": { "type": "string", "maxLength": 100 },
      "description": "People, roles or groups who made the decision, as named in the artifact."
    },
    "decided_on": {
      "type": "string",
      "format": "date",
      "description": "Date the decision was made, only if the artifact states it. Never use today's date."
    },
    "impacts": {
      "type": "string",
      "maxLength": 1000,
      "description": "What changes as a result, for example work, scope, cost, schedule or other decisions affected."
    }
  },
  "required": ["title", "statement"],
  "additionalProperties": false
}
```

### 5.5 `schemas/project-management/risk.v1.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:knowledge-automata:schema:project-management:risk:v1",
  "x-version": "1.0",
  "x-pmi-mapping": "Risk register, PMBOK Guide, Eighth Edition (see ADR-0007). v0.1 covers identification, qualitative assessment and response planning; urgency, proximity, contingency and fallback plans, residual and secondary risks and reserves are deferred.",
  "title": "Risk register entry",
  "description": "One uncertain event that could affect the group's objectives, negatively (threat) or positively (opportunity). An event that has already happened and was never uncertain is an issue, not a risk. Use only information stated or clearly implied in the artifact; omit any optional field that is not.",
  "type": "object",
  "properties": {
    "title": {
      "type": "string",
      "maxLength": 120,
      "description": "Short label for the risk, about ten words or fewer."
    },
    "event": {
      "type": "string",
      "maxLength": 500,
      "description": "The uncertain event itself, without its cause or effect. Example: The supplier may deliver the sensors late."
    },
    "kind": {
      "type": "string",
      "enum": ["threat", "opportunity"],
      "description": "threat: would harm objectives if it happens. opportunity: would benefit them."
    },
    "status": {
      "type": "string",
      "enum": ["open", "occurred", "closed"],
      "description": "open: could still happen. occurred: it has happened. closed: no longer relevant, or the response is complete. Use open for a newly identified risk."
    },
    "cause": {
      "type": "string",
      "maxLength": 500,
      "description": "The condition or fact that makes the event possible."
    },
    "effect": {
      "type": "string",
      "maxLength": 500,
      "description": "What would happen to objectives if the event occurs."
    },
    "probability": {
      "type": "string",
      "enum": ["very_low", "low", "medium", "high", "very_high"],
      "description": "Likelihood of the event, only if the artifact gives or clearly implies one."
    },
    "impact": {
      "type": "string",
      "enum": ["very_low", "low", "medium", "high", "very_high"],
      "description": "Size of the effect if the event occurs, only if the artifact gives or clearly implies one."
    },
    "owner": {
      "type": "string",
      "maxLength": 100,
      "description": "Person or role responsible for monitoring and responding, as named in the artifact."
    },
    "category": {
      "type": "string",
      "maxLength": 60,
      "description": "Short category if one is stated or obvious, for example technical, schedule, cost, supplier, people or external."
    },
    "response_strategy": {
      "type": "string",
      "enum": ["escalate", "avoid", "transfer", "mitigate", "exploit", "share", "enhance", "accept"],
      "description": "Agreed response. For threats: escalate, avoid, transfer, mitigate or accept. For opportunities: escalate, exploit, share, enhance or accept."
    },
    "response_actions": {
      "type": "array",
      "maxItems": 10,
      "items": { "type": "string", "maxLength": 300 },
      "description": "Specific actions agreed to carry out the response."
    },
    "triggers": {
      "type": "array",
      "maxItems": 10,
      "items": { "type": "string", "maxLength": 300 },
      "description": "Warning signs that the event is about to happen or has happened."
    }
  },
  "required": ["title", "event", "kind", "status"],
  "additionalProperties": false
}
```

## 6. Code requirements

### 6.1 Runtime dependency and lock file

- Add `jsonschema` as the first runtime dependency in `pyproject.toml`.
- This triggers the backlog item "Lock file, added with the first runtime dependency" earlier than planned (it was written with the Cohere SDK in mind). Propose the tool in your plan (for example `uv lock`, or `pip-tools` with hashes), keep CI and Dependabot working with it, and remove the item from the backlog.
- `jsonschema` depends on `rpds-py`, a compiled package. This is the first real test of Python 3.15 in CI. If it fails there, follow the note in `dev/STATUS.md`.

### 6.2 Packaging the schema files

`schemas/` stays at the repository root, because it is the visible, language-neutral contract (and will get code-owner review later). Code must still find the files when the package is installed, not only in an editable install. Propose an approach in your plan (for example hatchling `force-include` into the wheel plus `importlib.resources`) and check it once with a non-editable install.

### 6.3 Registers

- `core/registers.py` defines a frozen dataclass `RegisterSpec`: `name` (for example `decision-log`), `id_prefix` (`DEC`), `content_schema` (path relative to `schemas/`), `allowed_classifications` (a frozenset) and `semantic_checks` (a tuple of functions that take content and return a list of error messages).
- `domains/project_management/registers.py` defines `DECISION_LOG` and `RISK_REGISTER`, plus the risk semantic check: `response_strategy` must fit `kind`. `avoid`, `transfer` and `mitigate` are for threats only; `exploit`, `share` and `enhance` for opportunities only; `escalate` and `accept` fit both.
- Core modules must not import from `domains/` (ADR-0009). Callers pass a `RegisterSpec`.

### 6.4 Schema loading

- Load schema files by relative path, cached.
- `draft_schema(spec)` returns a deep copy of `core/draft.v1.json` with the `content` placeholder replaced by the register's content schema, inlined (no `$ref`, because providers may not resolve references).
- `schema_version(spec)` returns the content schema's `x-version`.

### 6.5 Validators

All validators return a small result object (`ok`, plus a list of error messages that include the JSON path). They never raise for invalid data; they raise only for programming errors such as a missing schema file.

**Format checking.** Enable `format` assertion. `jsonschema` checks `date` out of the box but silently skips `date-time` unless `rfc3339-validator` is installed. Register a custom `date-time` checker based on `datetime.fromisoformat` that also requires a timezone, instead of adding another dependency.

**`validate_record(record, spec)`:**

1. Envelope valid against `core/record.v1.json`.
2. `register` equals `spec.name`, and `id` starts with `spec.id_prefix` followed by `-`.
3. The major part of `schema_version` matches the content schema's major version.
4. `content` valid against the register's content schema, and passes `spec.semantic_checks`.
5. History revisions increase by one from 1, and the last one equals `revision`. `relations` never point at the record's own ID.

**`validate_draft(draft, spec, artifact_text)`:**

1. Valid against `draft_schema(spec)`.
2. `content` passes `spec.semantic_checks`.
3. Every quote in `evidence` passes the evidence check (6.6). One failed quote rejects the draft, and the result names the failed quotes.

**`validate_reconciliation(result, spec, candidates)`**, where `candidates` maps each candidate ID shown to the Comparator to its current record:

1. Valid against `core/reconciliation.v1.json`.
2. `classification` is in `spec.allowed_classifications` (the decision log allows all four; the risk register does not allow `supersession`).
3. For `new`, `target_id` must be absent. For anything else, `target_id` is required, must be a key of `candidates`, must start with `spec.id_prefix`, and the target's `record_status` must be `active`.

### 6.6 Evidence check

`check_evidence(quotes, artifact_text, min_chars=12)` returns a per-quote result (passed or failed, with a reason).

Normalize the artifact text and each quote the same way:

1. Unicode NFKC.
2. Curly single and double quotes to straight quotes; en dash, em dash and minus sign to a hyphen; the ellipsis character to three dots; non-breaking spaces to spaces.
3. Case-fold.
4. Collapse every run of whitespace, including line breaks, to one space, and strip the ends.

For quotes only, also strip surrounding quote marks and a leading or trailing `...`. A quote passes if, after normalization, it is at least `min_chars` long and is a substring of the normalized artifact text. Short quotes fail, because a quote like "yes" proves nothing.

The check runs over the text the Sensor (intake and input guardrail) will store for the artifact. Until the Sensor exists, tests pass the text directly.

### 6.7 Provider compatibility

Add a test that walks `draft_schema(spec)` for each register, and `core/reconciliation.v1.json`, and fails if they use any keyword outside these two sets:

- **Sent to the provider:** `type`, `properties`, `required`, `items`, `enum`, `const`, `description`, `title`, `format` (only `date`, `date-time`, `time`, `uuid`), `additionalProperties`.
- **Removed by the adapter later:** `$schema`, `$id`, `x-version`, `x-pmi-mapping`, `maxLength`, `minItems`, `maxItems`.

Check this list against Cohere's structured outputs documentation, in particular whether `additionalProperties: false` and optional properties are supported, and whether unknown `x-` keywords are tolerated. Report what you find in your plan and log anything surprising in `dev/tool-feedback.md`. Claude's reading so far: Cohere does not support `minLength`/`maxLength`, `minimum`/`maximum`, `minItems`/`maxItems`, `allOf`/`oneOf`/`not` or `uniqueItems`, and every object needs at least one required field.

## 7. Tests

All fixtures are fictional and live in `tests/fixtures/`. No LLM calls.

- **Schemas:** every file in `schemas/` passes the draft 2020-12 meta-schema check; the provider compatibility test in 6.7.
- **Records:** a valid decision record and a valid risk record pass. Each of these fails: a missing required envelope field; a bad `record_status`; `superseded` without `superseded_by`; a malformed ID; a `DEC-` ID in the risk register; an invalid `date-time` (for example `"yesterday"`); content missing a required field; a `schema_version` with the wrong major version; `revision` not matching the last history entry.
- **Drafts:** a valid decision draft and a valid risk draft pass. Each of these fails: the LLM sets an ID inside `content`; the LLM sets an ID at the top level; a missing required content field; a bad enum (for example `"probability": "likely"`); empty `evidence`; a threat with `"response_strategy": "exploit"`.
- **Evidence:** an exact quote passes. Quotes that differ only in curly versus straight quotes, line breaks and double spaces, dashes, non-breaking spaces, case, surrounding quote marks or a trailing ellipsis pass. A paraphrase fails. A quote shorter than 12 characters fails. One bad quote among good ones rejects the draft and is named in the result.
- **Reconciliation:** `new` without a target passes. Each of these fails: `new` with a target; `update` without a target; a target that was not among the candidates; a target with another register's prefix; `supersession` in the risk register; `update`, `reaffirmation` or `supersession` of a superseded target.

## 8. Documentation changes

### 8.1 New ADR: `docs/decisions/0011-record-model-and-write-rules.md`

Use this text, and add the ADR to the index in `docs/decisions/README.md`:

```markdown
# 0011. Record model and write rules

- **Status:** Accepted
- **Date:** 2026-10-25

## Context

ADR-0005 requires validated records with code-assigned IDs. Registrars (specialist record keepers) draft records with an LLM, and the Comparator (reconciliation) judges how new input relates to existing records. The system needs a clear line between what an LLM may write and what code owns, a defence against records invented from nothing, and write rules for the decision log and the risk register.

## Decision

- Every record has an envelope owned by code (`schemas/core/record.v1.json`) and a `content` part drafted by a Registrar and validated against its register's content schema. LLM output only ever lands in `content`.
- A Registrar returns its content with evidence: quotes copied word for word from the artifact. Code normalizes the text (Unicode, quote marks, dashes, whitespace, case) and checks that every quote appears in the artifact. A failed quote rejects that record only, and the rejection is logged.
- Links between records are LLM judgements. The Comparator proposes a classification and a target; code checks that the target was a candidate, belongs to the same register and is active, and that the transition is allowed, before it writes relations and history.
- The JSON Schema files in `schemas/` are the single source of truth, and code validates against them directly. The parts sent to an LLM provider use a small keyword subset; the provider adapter removes validation-only keywords, and code validates the full schema afterwards.
- Optional fields are omitted when not stated. Derived values, such as the risk score, are computed by code and not stored.
- Record IDs are a register prefix plus a sequence (`DEC-0001`, `RSK-0001`). Schema files carry their major version in the file name and `MAJOR.MINOR` in `x-version`; adding an optional field is a minor change, anything else is major.
- The decision log records only decisions that were made, including rejected options. It is append-only: an update only fills empty fields, a reaffirmation adds sources, and any change of substance is a new decision that supersedes the old one.
- The risk register is updated in place, with every revision recorded in the history. Risks are not superseded in v0.1.

## Consequences

- Ownership is enforced by the shape of the record, not by discipline.
- Records invented from nothing are rejected by a cheap, deterministic check, and the verified quotes double as citations.
- History records the model and prompt version per revision, which supports targeted reprocessing (ADR-0006).
- A record supported only by paraphrase cannot be stored. False rejections are logged so they can be reviewed.
- A decision update ignores changes to fields that are already filled (they are logged), so a supersession misclassified as an update can go unnoticed until the Observer (quality control) exists.
```

### 8.2 Amend ADR-0007

Resolve the edition question. Change the status line to `Accepted (amended 2026-10-25: PMBOK edition resolved)` and replace the Decision and Consequences sections with:

```markdown
## Decision

- Record schemas are defined by this project and explicitly mapped to artifact descriptions in the PMBOK Guide, Eighth Edition (PMI, 2025): risk register, issue log, assumption log, change log, lessons learned register and stakeholder register.
- The decision log is included as a widely used project-management practice. It is not named as an artifact in the Eighth Edition (checked against summaries of its inputs and outputs on 2026-10-25), and its schema says so in its mapping note.
- v0.1 implements the decision log and the risk register.
- These registers are the first domain under ADR-0009.

## Consequences

- Credible, recognizable structure for project managers.
- Agile-compatible, because maintenance is automated rather than manual.
- Each schema documents its own mapping in `x-pmi-mapping`.
- When PMI publishes a new edition, the mappings are reviewed.
```

### 8.3 `docs/architecture.md`

- **Data flow, step 3:** the Comparator proposes a classification and a target; code checks it before anything is written.
- **Data flow, step 4:** code checks the evidence quotes, validates the draft against the schema, assigns the ID and stores the record; a rejected draft affects only that record.
- **Write rules:** replace the section with a short description of the envelope and `content` split, the evidence check and the table from 3.8, linking ADR-0011.
- **Patterns and terminology:** add a row: evidence quote check, established term "grounding check (attribution to source text)".

### 8.4 `README.md`

No change needed: nothing user-visible changes yet.

### 8.5 `dev/backlog.md`

- **Now:** remove the lock file item (done in this handoff). Remove the schemas item once this PR is ready.
- **Later**, add:
  - Issue log Registrar, including proposals and open questions found in artifacts (dropped in v0.1, ADR-0011) and risks that occurred.
  - Operator (human in the loop) review of evidence-check rejections.
  - Remaining PMBOK risk fields: urgency, proximity, contingency and fallback plans, residual and secondary risks, reserves.
  - Typed Python models for records, only with a test that keeps them in sync with the schema files.
- **Open questions:** remove the PMBOK edition question (resolved in ADR-0007). Add: "Artifact Ledger status when some of an artifact's records are rejected (for example a `processed` status with a list of rejections)."

### 8.6 `dev/principles-in-practice.md`

Add these entries (newest at the bottom), plus any of your own:

```markdown
### 2026-10-25: P2 Architecture is a first-class deliverable (product)

The record schemas were designed by Miguel and Claude before implementation, as language-neutral JSON Schema files, and handed to Copilot as a contract rather than generated while coding.
Evidence: `schemas/`, `dev/handoffs/002-register-schemas.md`.

### 2026-10-25: P5 AI generates. Humans own (teamwork)

Miguel's review of Claude's record design caught that links between records are also LLM judgements. The design changed so code checks the Comparator's proposed links instead of trusting them.
Evidence: ADR-0011.

### 2026-10-25: P10 Distrust the happy path (product)

Every record must carry quotes from its artifact, and code checks they really appear there, so a record invented from nothing is rejected by a cheap, deterministic check.
Evidence: ADR-0011, `src/knowledge_automata/core/evidence.py`.
```

### 8.7 `dev/STATUS.md`

Update at the end of the session.

## 9. Suggested commit sequence

1. `chore: add jsonschema runtime dependency and lock file`
2. `feat: add register specs and schema loading` (implements ADR-0011)
3. `feat: add record, draft and reconciliation validators`
4. `feat: add evidence quote check`
5. `docs: add ADR-0011 and resolve the PMBOK edition in ADR-0007`
6. `docs: update architecture, backlog, status and logs for handoff 002`

Each commit includes its tests and ends with a `Co-authored-by:` trailer. Run `ruff check`, `ruff format --check` and `pytest` before each commit. Suggested pull request title: `feat: add register schemas and validation (handoff 002)`.

## 10. Done when

- The validators in 6.5 and the evidence check in 6.6 exist, with the tests in section 7, and `ruff check`, `ruff format --check` and `pytest` pass locally and in CI (`ci-ok` green), including on Python 3.15.
- Schemas load from a non-editable install.
- Cohere compatibility was checked against its docs, and anything surprising is logged.
- ADR-0011 is added, ADR-0007 amended, and the docs in section 8 updated.
- No file was read from or copied from Chronicle. No secrets in the repo.
- `dev/STATUS.md` is updated and you have reported back.

## 11. Out of scope

LLM service layer and the provider adapter (including the keyword stripping), storage layout, the Registrars and the write rules themselves, the Comparator, the Sensor and the Artifact Ledger. These come in later handoffs.
