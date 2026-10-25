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
