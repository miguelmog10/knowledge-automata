# Sample project: Tallyleaf

Tallyleaf is a small team building a mobile app for plant inventory in commercial greenhouses. Its project board meets regularly, and this folder is the team's institutional memory as Knowledge Automata keeps it. It follows the team's decisions over five meetings so far and will grow into a small evaluation set with expected records.

The team, the app and the meetings are fictional.

## Layout

This folder is a memory folder (see [ADR-0013](../../docs/decisions/0013-record-storage-json-files.md)):

```
artifacts/                            raw artifacts (meeting notes); read-only
ledger/ART-0001.json                  Artifact Ledger entry for each artifact
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

**Thinking disabled, then enabled.** The runs started with Command A+ thinking disabled, the default at the time. ART-0002 went through, but its draft and its comparison each needed the retry, and both draft attempts for ART-0003 were rejected as invalid JSON. A diagnostic showed why: with thinking disabled, the model writes its reasoning as prose before the JSON. Thinking was then enabled by default ([ADR-0014](../../docs/decisions/0014-registrar-drafting-loop.md), amended), and ART-0003 was run again, which the Ledger allows because its first run recorded nothing. So `DEC-0002` revision 1 was drafted with thinking disabled, and every later draft and comparison with thinking enabled; each passed on the first attempt. The rejected draft stays in ART-0003's Ledger entry as evidence.

**What the run shows.** All four classifications and targets matched the expected table. Rerank separated the right record clearly: the record each meeting relates to scored 0.29 to 0.61, and every other candidate 0.022 or less. The content is weaker in one place. ART-0002 states no rationale and no alternatives, but its draft (thinking disabled) filled both with invented content, so the ART-0004 update had no empty field to fill and kept them; ART-0004's real rationale and the alternative that was set aside are in `DEC-0002`'s sources, not in its content. `DEC-0003`, drafted with thinking enabled, left out the alternatives ART-0005 does not give. These are candidates for the next Decision Registrar prompt, to be judged on the evaluation set ([backlog](../../dev/backlog.md)).

The command line crashed while printing the ART-0004 result (a character the Windows pipe could not encode, since fixed), after the record and the Ledger entry were written. That run is complete, but its printed Comparator reason was lost: reasons are shown, not stored.

## Views

The Markdown views are generated from the JSON records and are never edited by hand. To regenerate them:

```powershell
uv run knowledge-automata views --memory examples/sample-project
```

CI runs the same command with `--check`, which fails if the committed views differ from the generator's output.
