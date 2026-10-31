# 0018. Governor (orchestrator): work orders and resumable runs

- **Status:** Proposed
- **Date:** 2026-10-31

## Context

Until handoff 007, `record-decision` drafted the single most significant decision in an artifact, so a meeting with several decisions and a risk kept only one decision. ADR-0004 and ADR-0006 give that job to the Governor (orchestrator): read an accepted artifact, send work orders to the Registrars (specialist record keepers), and mark the artifact in the Artifact Ledger. Artifact text is untrusted, every model call is billed against a capped trial key, and a run that stops halfway already writes records today.

## Decision

- The Governor reads an accepted artifact once and returns work orders: for each item, the register it belongs to and one to five evidence quotes. It writes no free text. Code builds each work order's label from its first quote.
- Each register brings a short definition of what belongs in it, as a versioned prompt file named by its register spec, and the Governor's prompt is built from those definitions. Registers mapped to the PMBOK Guide keep its meaning; registers that are not in it, such as the decision log, are extensions with their own definition.
- Code checks the reply before anything else runs: the schema, every evidence quote, and no quote shared by two items in the same register. One retry with the errors, then the reply is rejected, as in the drafting loop (ADR-0014). Code sorts the work orders by where their earliest quote appears.
- The Decision Registrar drafts the item its work order points to (`decision-registrar.v2`, which also carries the known fixes for invented fields), and code checks that the draft quotes the work order. Work orders run one after another, so a later item is compared with the records an earlier one wrote (ADR-0017).
- The checked work orders are saved in a work orders file per artifact before any draft, and each one is marked recorded or rejected after its writes (checkpointing). A rerun reuses the file, skips recorded orders and does not call the Governor again. The Ledger's lists of records produced and drafts rejected are rebuilt from the file at the end of each run.
- Work orders for a register with no Registrar are kept as not routed, and the Ledger counts them. An artifact with no work orders is processed with zero records.
- A setting limits the work orders per artifact (`KA_GOVERNOR_MAX_ITEMS`, default 10). Above it, nothing is drafted and the artifact is held for review, a new Ledger status. The Operator (human in the loop) releases it, and the saved work orders then run. Nothing is cut silently.
- The Governor makes the Ledger transitions. The Ledger records its model, prompt and definition versions, attempts and the work orders found per register.
- The `process` command replaces `record-decision`.

## Consequences

- A meeting yields every decision in it, and each record still traces to verified quotes.
- A provider error halfway through costs only the unfinished items on the next run, and the split of the artifact into items cannot change between runs.
- One more call per artifact, plus about five calls per routed item. The limit bounds the cost of one odd or hostile artifact, and is one layer of defence against memory poisoning next to the evidence check and the Comparator (reconciliation).
- A new register needs a definition file; the Governor's prompt picks it up without a change, which a register configurator can build on later.
- Risks are found before the Risk Registrar exists, but are not drafted. Records already produced are not reprocessed, which still needs its own design.
- A split duplicate fails the shared-quote check when its two items quote the same words, and the retry asks for one item; otherwise it becomes a reaffirmation of the record written from the same artifact: harmless, but it costs a draft.
