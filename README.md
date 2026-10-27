# Knowledge Automata

*Knowledge on autopilot.*
*The living memory of any group that makes decisions together.*

[![CI](https://github.com/miguelmog10/knowledge-automata/actions/workflows/ci.yml/badge.svg)](https://github.com/miguelmog10/knowledge-automata/actions/workflows/ci.yml)

## What it is

Knowledge Automata is a general-purpose institutional memory for any group that makes decisions together: a project team, a company department, a research group, a neighborhood association. A multi-agent LLM system turns messy artifacts (meeting notes, chats, documents) into validated, structured records, each traceable to the artifacts it came from, so people and AI tools can ask what the group knows and why. v0.1 targets project teams with PMI-aligned registers: a decision log and a risk register. It is open source (Apache 2.0) and built on Cohere's platform (Command, Embed, Rerank) behind a provider-agnostic service layer.

**See it working:** [a real decision record](examples/sample-project/views/decision-log/DEC-0001.md) that Command drafted from [fictional meeting notes](examples/sample-project/artifacts/ART-0001-project-board-2026-02-03.md), with every quote checked against the source and committed unedited.

## Status

v0.1 in progress. Works today:

- An LLM service layer on Cohere's SDK: Command, Embed and Rerank behind provider-neutral interfaces, with a metadata-only log of billed units, latency and request IDs.
- The first end-to-end slice: one artifact goes through the Decision Registrar (specialist record keeper) on real Command calls and becomes one validated decision record, with generated Markdown views.

Next: the Sensor (intake) and the Artifact Ledger, then the Comparator (reconciliation), the Governor (orchestrator), the Risk Registrar and an evaluation set. Details in [dev/STATUS.md](dev/STATUS.md).

## Why

Knowledge is created constantly and lost just as fast. Decisions sit in meeting notes, chats and documents, so groups rediscover context and re-argue settled decisions over and over.

Even a perfect memory would still need a record. A record is shared truth that everyone can see and agree on. It makes ownership of decisions clear, keeps the history of how and why they changed, outlives any single tool, chat or model, and is what governance and audits rely on. Knowledge Automata keeps that record, so people and AI tools can answer from it.

Project management is the first application. Formal registers such as a decision log and a risk register solve this, but they are expensive to maintain by hand, which is why Agile teams often skip them. Knowledge Automata maintains them automatically as a side effect of normal work, so teams get PMI-quality records without the overhead.

## Design principles

- **The model proposes, code checks.** The LLM is used only where judgment is needed. Code assigns IDs, checks every evidence quote word for word against the source artifact, validates each record against its JSON Schema and stores it. An invalid draft gets one retry with its errors; if the retry fails, the record is rejected and nothing is written ([ADR-0014](docs/decisions/0014-registrar-drafting-loop.md)).
- **Measured, not assumed.** Every model call logs its billed units, latency and request ID ([ADR-0012](docs/decisions/0012-llm-service-layer-observation-and-cost.md)). Choices follow the numbers: in the smoke check, Command A+ with thinking enabled used about 6x the output tokens for the same validated draft, so thinking is disabled for the Decision Registrar until the evaluation set says otherwise.
- **Engineered like a product, scaled to a prototype.** More than 400 tests run offline with the network blocked. CI runs on Python 3.11 and 3.15 with a dependency audit and checks that the committed views match the records. Significant choices are recorded as short [architecture decision records](docs/decisions/) (14 so far), at a level set for a prototype ([ADR-0008](docs/decisions/0008-light-engineering-standard-for-v0-1.md)).

## How it works

The system works as a closed loop:

1. **Sensor (intake), planned:** checks, hashes and logs each incoming artifact in the Artifact Ledger, quarantining invalid or suspicious input.
2. **Governor (orchestrator), planned:** identifies what the artifact contains and sends work orders to the relevant Registrars.
3. **Comparator (reconciliation), planned:** retrieves related existing records and classifies the input as new, an update, a reaffirmation or a supersession. Embed and Rerank are already wired into the service layer and smoke-tested.
4. **Registrars (specialist record keepers), Decision Registrar built, Risk Registrar planned:** draft structured records; code validates them against a schema, assigns IDs and stores them.
5. **Governor, planned:** marks the artifact as processed in the Ledger, listing the records it produced.

Today the first slice runs step 4 on its own for the decision log. See [docs/architecture.md](docs/architecture.md) for roles, data flow and design rules.

## Getting started

Requires Python 3.11 or later and [uv](https://docs.astral.sh/uv/), which installs the exact dependency versions pinned in `uv.lock`. On Windows (PowerShell):

```powershell
uv sync --all-extras          # creates .venv and installs the locked dependencies
.\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env   # then add your Cohere API key
pytest
```

On macOS or Linux, activate with `source .venv/bin/activate` and copy with `cp .env.example .env`. Without uv, `pip install -e ".[dev]"` in a virtual environment still works, but does not use the lock file.

Tests never call the API. Commands that need your Cohere key load `.env` through uv, for example the manual smoke check, which makes a handful of real calls: `uv run --env-file .env python scripts/cohere_smoke.py`.

After changing dependencies in `pyproject.toml`, run `uv lock` and commit the updated `uv.lock`.

Keep the clone outside cloud-synced folders such as OneDrive or Dropbox: sync tools lock files inside `.git` and `.venv` while Git and uv are writing them. If you move the folder, delete `.venv` and run `uv sync --all-extras` again, because the editable install records the old path.

## Try it

To record the most significant decision in your own artifact (one real Command call, two if the first draft fails validation):

```powershell
uv run --env-file .env knowledge-automata record-decision notes.md --artifact-id ART-0001 --artifact-date 2026-02-03
```

The record is validated before it is stored as JSON in the memory folder (by default `runtime/memory`, git-ignored; choose another with `--memory`), and the Markdown views are regenerated next to it. Artifacts kept in `<memory>/artifacts/`, with names starting with their ID, are linked from the views. Until the Sensor (intake) and its Artifact Ledger exist, you give each artifact its ID and date, and a second run on the same artifact ID is refused without a call. To regenerate the views, or check that they match the records, without any call:

```powershell
uv run knowledge-automata views --memory examples/sample-project --check
```

## How this project is built

Knowledge Automata is built by a human-led team: Miguel (owner) with two AI assistants, Claude (discovery, architecture, review) and Copilot (implementation), following the [AI-Assisted Software Engineering principles](https://github.com/miguelmog10/ai-assisted-software-engineering/blob/main/PRINCIPLES.md). Decisions are recorded in [docs/decisions/](docs/decisions/) and the working process lives in [dev/](dev/). Team rules are in [AGENTS.md](AGENTS.md).

## Background

Knowledge Automata is a ground-up redesign inspired by lessons from Chronicle, an earlier course project by the author. No code or files were carried over (see [ADR-0002](docs/decisions/0002-clean-room-rebuild.md)).

## Security

To report a vulnerability, see [SECURITY.md](SECURITY.md).

## License

[Apache 2.0](LICENSE).
