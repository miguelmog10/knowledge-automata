# 0017. Comparator (reconciliation): compare checked drafts before writing

- **Status:** Accepted
- **Date:** 2026-10-30

## Context

ADR-0011 sets the decision log's write rules and says the Comparator (reconciliation) proposes how new input relates to existing records, while code checks the proposal. Until now every record was new, so a decision restated in three meetings became three records. The architecture placed the Comparator before the Registrars (specialist record keepers), comparing a summary from the Governor (orchestrator), which does not exist yet. Records were never rewritten (ADR-0013), and a supersession changes two files with no transaction across them.

## Decision

- The Registrar drafts first, code validates the draft and its evidence quotes, and then the Comparator compares the checked draft with existing records. This is the intended order, also once the Governor exists: the Comparator only judges content that code has grounded in the artifact.
- Retrieval runs in two stages over the register's active records, recomputed on every run with no cache. Embed ranks them by cosine similarity of title, statement and context, Rerank reorders the top K (default 10), and Command classifies against the top N (default 3). K and N are settings and starting values, to be tuned on the evaluation set. When the register has no active record, code classifies the draft as new with no calls.
- The Comparator returns the reconciliation result from a versioned prompt. Code checks that the target was one of the candidates shown, is in the same register and is active. A failed check or an unusable response gets one retry with the errors; if the retry fails, the draft is rejected and nothing is written, as in the Registrar loop (ADR-0014). There is no fallback to new.
- An existing record changes only through a revision: the revision number plus one, one more history entry, earlier history and sources unchanged, and no lost update. An update fills only empty fields and adds the draft's quotes as sources; a reaffirmation adds the quotes only.
- A supersession writes the new record, pointing back to the old one, before it marks the old record superseded. An interruption between the two leaves a new record whose target is still active, which the pipeline detects before any call. Repair is by hand in v0.1.
- The Ledger lists the change each artifact made and, when a comparison ran, the Comparator's model, prompt version, attempts and the candidates' Rerank scores. The Comparator's reason is model output: it is printed, never stored.
- An artifact whose earlier run recorded nothing may be run again. Reprocessing an artifact that produced records needs its own design.

## Consequences

- Duplicates are prevented by design: a restated decision adds sources to the existing record instead of creating a new one.
- A reaffirmation pays for a full draft that is mostly discarded (its quotes are kept). The cost is visible per artifact in the event log and is accepted in exchange for comparing only verified content; a cheap pre-check could skip obvious repeats later.
- Each artifact costs up to five more calls when the register is not empty: two Embed calls, one Rerank call and one or two Command calls.
- Recomputing the vectors costs one Embed call over the whole register per run; a cache becomes worthwhile only at a much larger size.
- The right record can be cut by the K or N limit. The recorded scores and the evaluation set show whether that happens.
- A supersession misclassified as an update still goes unnoticed until the Observer (quality control) exists (ADR-0011).
