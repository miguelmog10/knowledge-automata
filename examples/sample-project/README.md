# Sample project: Tallyleaf

Tallyleaf is a small team building a mobile app for plant inventory in commercial greenhouses. Its project board meets regularly, and this folder is the team's institutional memory as Knowledge Automata keeps it. It follows the team's decisions over nine meetings and status updates so far and will grow into a small evaluation set with expected records.

The team, the app and the meetings are fictional.

## Layout

This folder is a memory folder (see [ADR-0013](../../docs/decisions/0013-record-storage-json-files.md)):

```
artifacts/                            raw artifacts (meeting notes); read-only
ledger/ART-0001.json                  Artifact Ledger entry for each artifact
work-orders/ART-0006.json             the Governor's work orders for each processed artifact
registers/decision-log/DEC-0001.json  decision records: the source of truth
views/decision-log.md                 decision log index (generated)
views/decision-log/DEC-0001.md        one page per decision (generated)
```

Start with the [decision log](views/decision-log.md).

## How the records were made

`DEC-0001` was recorded from [ART-0001](artifacts/ART-0001-project-board-2026-02-03.md) by one real run of `knowledge-automata record-decision` against Cohere Command (handoff 004). The first response was unusable, so the Decision Registrar (specialist record keeper) retried once, and the retry's draft passed validation. The record and its views were committed exactly as written and have not been edited. The record's history names the model and prompt version that produced it.

The Artifact Ledger came later (handoff 005), so [ART-0001's entry](ledger/ART-0001.json) was backfilled once through the Ledger code: its history says so, and it lists `DEC-0001` as the record produced.

### Reconciliation: ART-0002 to ART-0005 (handoff 006)

Four more meetings were written for handoff 006, one for each way a new decision can relate to the memory. They were ingested through the Sensor (intake and input guardrail) and recorded one at a time, in date order, by real runs of `record-decision` on 2026-10-31. Each run drafts a decision, then the Comparator (reconciliation) compares it with the active decisions (Embed, then Rerank, then Command) and applies the matching write rule. Everything below was committed as written, without edits.

| Artifact | Meeting | Expected | Actual | Run ID |
|---|---|---|---|---|
| [ART-0002](artifacts/ART-0002-project-board-2026-03-03.md) | project board, 3 March | new: `DEC-0002`, one status ladder for every batch | new: `DEC-0002` | `620095ee-ccda-41af-964e-4efdd5640040` |
| [ART-0003](artifacts/ART-0003-tech-sync-2026-03-17.md) | tech sync, 17 March | reaffirmation of `DEC-0001` (revision 2, sources from ART-0003) | reaffirmation of `DEC-0001`: revision 2, three sources added | `bab2ba3b-fe45-4495-b631-8577f9cc51f1` (rejected), then `312c8736-68a7-46ef-ba81-4014a469f5c8` |
| [ART-0004](artifacts/ART-0004-design-review-2026-03-31.md) | design review, 31 March | update of `DEC-0002` (revision 2, rationale and alternatives filled if they were empty) | update of `DEC-0002`: revision 2, no field filled, because the ART-0002 draft had already filled both with content the meeting notes do not state (see below) | `e9a931d1-56c7-4aba-b3bc-bb27400a538a` |
| [ART-0005](artifacts/ART-0005-project-board-2026-04-28.md) | project board, 28 April | supersession: `DEC-0003` (one status path per crop type) supersedes `DEC-0002` | supersession: `DEC-0003` supersedes `DEC-0002`, now superseded (revision 3) | `8bd8beb3-0e9c-421f-b8fc-2a9ad7c841d3` |

`DEC-0001` revision 2 came from the reaffirmation by ART-0003, not from a hand edit: the record's history and the [ART-0003 Ledger entry](ledger/ART-0003.json) both say so. The first revision, as the handoff 004 run wrote it, is kept as a test fixture.

**Thinking disabled, then enabled.** The runs started with Command A+ thinking disabled, the default at the time. ART-0002 went through, but its draft and its comparison each needed the retry, and both draft attempts for ART-0003 were rejected as invalid JSON. A diagnostic showed what happened: with thinking disabled, the model wrote its reasoning as prose before the JSON. A later reproduction (2026-11-02) found the cause on our side: our prompts never asked for a JSON reply, which Cohere's structured outputs docs require, and with that line added, thinking disabled returned clean JSON. Thinking was then enabled by default ([ADR-0014](../../docs/decisions/0014-registrar-drafting-loop.md), amended), and ART-0003 was run again, which the Ledger allows because its first run recorded nothing. So `DEC-0002` revision 1 was drafted with thinking disabled, and every later draft and comparison with thinking enabled; each passed on the first attempt. The rejected draft stays in ART-0003's Ledger entry as evidence.

**What the run shows.** All four classifications and targets matched the expected table. Rerank separated the right record clearly: the record each meeting relates to scored 0.29 to 0.61, and every other candidate 0.022 or less. The content is weaker in one place. ART-0002 states no rationale and no alternatives, but its draft (thinking disabled) filled both with invented content, so the ART-0004 update had no empty field to fill and kept them; ART-0004's real rationale and the alternative that was set aside are in `DEC-0002`'s sources, not in its content. `DEC-0003`, drafted with thinking enabled, left out the alternatives ART-0005 does not give. These are candidates for the next Decision Registrar prompt, to be judged on the evaluation set ([backlog](../../dev/backlog.md)).

The command line crashed while printing the ART-0004 result (a character the Windows pipe could not encode, since fixed), after the record and the Ledger entry were written. That run is complete, but its printed Comparator reason was lost: reasons are shown, not stored.

### The Governor: ART-0006 to ART-0008 (handoff 007)

Three more artifacts were written for handoff 007: a busy board meeting, a tech sync whose decisions appear twice (in their section and in a summary at the end), and a status update with nothing to record. They were ingested through the Sensor and processed one at a time on 2026-11-01 with `knowledge-automata process`, which replaced `record-decision` ([ADR-0018](../../docs/decisions/0018-governor-work-orders.md)). The Governor (orchestrator) reads each artifact once and returns work orders: the register each item belongs to and its evidence quotes. Each decision work order is then drafted by the Decision Registrar (`decision-registrar.v2`), compared and written as before; risk work orders are kept as not routed until the Risk Registrar exists. The work orders files in `work-orders/` are part of the memory: they record what the Governor found and what became of each item. Everything was committed as written, without edits.

| Artifact | Meeting | Run ID | Work orders (decision, risk) | Calls |
|---|---|---|---|---|
| [ART-0006](artifacts/ART-0006-project-board-2026-05-26.md) | project board, 26 May | `23feff57-1c1d-4cb7-83b7-107f174fd8c3` | 3, 1 (expected 3, 1) | 16 |
| [ART-0007](artifacts/ART-0007-tech-sync-2026-06-09.md) | tech sync, 9 June | `98b81324-173e-4c44-9e4c-43919265e5c0` | 3, 1 (expected 3, 1) | 17 |
| [ART-0008](artifacts/ART-0008-status-update-2026-06-16.md) | status update, 16 June | `9e94307b-9b47-4a44-a7e1-8138cd6565c0` | 0, 0 (expected 0, 0) | 1 |

Every work order pointed to the expected item, and the items meant to be left out were left out: the open question about French and the actions in ART-0006, the dark mode suggestion in ART-0007, everything in ART-0008. The Governor's reply passed on the first attempt each time.

| Artifact | Work order | Expected | Actual |
|---|---|---|---|
| ART-0006 | 1 | reaffirmation of `DEC-0003`, revision 2 | **update** of `DEC-0003`, revision 2, no field filled; two ART-0006 sources added |
| | 2 | new `DEC-0004`, QR code labels, no rationale or alternatives, `decided_by` "the board" or absent | new `DEC-0004`, no rationale or alternatives, `decided_by` "the board" |
| | 3 | not routed (risk) | not routed: the label printer may arrive late |
| | 4 | new `DEC-0005`, add conflicting counts, with the stated rationale | new `DEC-0005` with the rationale (benches split between two people) and the alternative the meeting set aside (keep only the last count) |
| ART-0007 | 1 | update of `DEC-0004`, rationale and alternatives filled | update of `DEC-0004`, revision 2: rationale (half the phones cannot read NFC, labels cost a few cents) and alternatives (NFC tags) filled, **and `decided_on` 2026-06-09** |
| | 2 | supersession: `DEC-0006` supersedes `DEC-0005` | supersession: `DEC-0006` (keep the most recent count, the grower confirms), `decided_by` Marc and Sofia; `DEC-0005` superseded |
| | 3 | new `DEC-0007`, English and French for two screens | new `DEC-0007`; its draft needed the retry |
| | 4 | not routed (risk) | not routed: translating the other screens could delay the July release |
| ART-0008 | | `processed`, zero records, an empty work orders file | as expected |

**What the run shows.** The split trap in ART-0007 did not catch the Governor: it returned one work order per decision, each quoting both the section sentence and its summary line. Rerank separated the right record clearly again: 0.66 to 0.74 for the record each item relates to, 0.11 or less for every other candidate. The `decision-registrar.v2` fix for invented fields held: `DEC-0004` was drafted with no rationale and no alternatives, so the ART-0007 update could fill them, the case that failed for `DEC-0002` in handoff 006. Three findings, each a backlog item to judge on the evaluation set:

- ART-0006 work order 1, a known borderline: the Comparator read the pilot numbers in Julie's confirmation as a new detail and classified an update that then filled no field. Either way `DEC-0003` stays one record.
- ART-0007 work order 1 filled `DEC-0004`'s empty `decided_on` with 2026-06-09, the date of the tech sync that restated the decision. The board made it on 2026-05-26 (ART-0006), and ART-0007 itself says "the board picked QR codes in May". The write rule fills only empty fields, so the wrong date got in because the first draft had left the field empty.
- The `DEC-0007` draft passed on its second attempt, but why the first failed is not stored anywhere: only rejected drafts keep their error paths.

**Timeouts before the run.** The first two runs of ART-0006 (`19abb35e-b01e-4322-87ec-eef4d057be8b` with the default 60 s timeout, then `e8083665-5a93-415f-b341-3da571628b92` with `KA_LLM_TIMEOUT_SECONDS=180`) stopped at the Governor call, which returned nothing in time; both are in ART-0006's Ledger history as `failed` with `LLMUnavailableError`, and nothing was written. A throwaway diagnostic then made two calls outside the event log: a connectivity check (2.7 s) and the same Governor request (18.3 s, billed 1,267 input and 2,882 output tokens, 2,679 of them reasoning). The three runs above used the 180 s timeout, set for the command only. Governor calls took 17.4 s, 14.5 s and 2.8 s, and the slowest draft 27.0 s, so the timeouts were most likely a temporary slowdown at Cohere or on the network ([tool feedback](../../dev/tool-feedback.md)).

**Calls and tokens.** 38 calls in all: 2 timed out, 2 diagnostic (not in the event log) and 34 in the three runs. Billed tokens per run:

| Artifact | Governor (input, output) | Drafts (input, output) | Comparisons (input, output) | Embed input | Rerank input |
|---|---|---|---|---|---|
| ART-0006 | 1,267, 3,383 | 3,088, 6,839 | 3,407, 1,145 | 611 | 744 |
| ART-0007 | 1,160, 4,696 | 3,805, 9,376 | 3,744, 1,356 | 860 | 1,164 |
| ART-0008 | 924, 300 | none | none | none | none |

### The JSON instruction: ART-0009 (handoff 008)

One more meeting was written for handoff 008: the board meeting that ART-0008 announced, with a new decision on a topic close to an existing record, a confirmation that adds the alternatives the team set aside, a risk with its response, an open question and actions. It was ingested and processed on 2026-11-06 with the new prompt versions, each ending with an instruction to reply with one JSON object (`governor.v2`, `decision-registrar.v3`, `decision-comparator.v2`), thinking enabled. Everything was committed as written, without edits.

| Artifact | Meeting | Run ID | Work orders (decision, risk) | Calls |
|---|---|---|---|---|
| [ART-0009](artifacts/ART-0009-project-board-2026-06-30.md) | project board, 30 June | `13d7f5e8-71a0-499d-83f6-85c2e818ac66` | 2, 1 (expected 2, 1) | 11 |

| Work order | Expected | Actual |
|---|---|---|
| 1 | new `DEC-0008`, the first release date, `decided_by` "the board" or absent, `decided_on` 2026-06-30 | new `DEC-0008`: first release on 21 July 2026 for the pilot growers only, with the stated rationale; `decided_by` "the board", `decided_on` 2026-06-30 |
| 2 | update of `DEC-0007`, alternatives filled | update of `DEC-0007`, revision 2: alternatives filled (translating every screen; launching in English only), **and `impacts`**, which restates the decision |
| 3 | not routed (risk) | not routed: the first app store review could delay the release |

**What the run shows.** Every item matched, and the open question about label printers and the actions were left out. The release date was not mistaken for the launch decision: `DEC-0007` was not among its candidates, while for the confirmation it ranked first at 0.61. Two notes for the evaluation set: the `impacts` filled in `DEC-0007` only restates the decision, and the risk work order quotes the warning but not the agreed response (Sofia's test build), which the Risk Registrar (handoff 009) will need.

**Calls and tokens.** 11 calls (5 chat, 4 Embed, 2 Rerank), all on the first attempt; the Governor answered in 10.4 s. Billed tokens: Governor 1,234 input and 3,256 output; drafts 2,001 and 3,779; comparisons 2,572 and 827; Embed 737 input; Rerank 1,114 input. Before the run, a diagnostic checked every agent with the new prompts, with thinking disabled and enabled; its results are in [handoff 008, section 9](../../dev/handoffs/008-json-instruction.md).

## Views

The Markdown views are generated from the JSON records and are never edited by hand. To regenerate them:

```powershell
uv run knowledge-automata views --memory examples/sample-project
```

CI runs the same command with `--check`, which fails if the committed views differ from the generator's output.
