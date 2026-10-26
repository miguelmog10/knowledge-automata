# Sample project: Tallyleaf

Tallyleaf is a small team building a mobile app for plant inventory in commercial greenhouses. Its project board meets regularly, and this folder is the team's institutional memory as Knowledge Automata keeps it. The sample project will follow the team's decisions over several meetings and grow into a small evaluation set with expected records.

The team, the app and the meetings are fictional.

## Layout

This folder is a memory folder (see [ADR-0013](../../docs/decisions/0013-record-storage-json-files.md)):

```
artifacts/                            raw artifacts (meeting notes); read-only
registers/decision-log/DEC-0001.json  decision records: the source of truth
views/decision-log.md                 decision log index (generated)
views/decision-log/DEC-0001.md        one page per decision (generated)
```

Start with the [decision log](views/decision-log.md).

## How the records were made

`DEC-0001` was recorded from [ART-0001](artifacts/ART-0001-project-board-2026-02-03.md) by one real run of `knowledge-automata record-decision` against Cohere Command (handoff 004). The first response was unusable, so the Decision Registrar (specialist record keeper) retried once, and the retry's draft passed validation. The record and its views were committed exactly as written and have not been edited. The record's history names the model and prompt version that produced it.

## Views

The Markdown views are generated from the JSON records and are never edited by hand. To regenerate them:

```powershell
uv run knowledge-automata views --memory examples/sample-project
```

CI runs the same command with `--check`, which fails if the committed views differ from the generator's output.
