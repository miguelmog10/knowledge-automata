# Knowledge Automata

*Knowledge on autopilot.*
*The living memory of any group that makes decisions together.*

[![CI](https://github.com/miguelmog10/knowledge-automata/actions/workflows/ci.yml/badge.svg)](https://github.com/miguelmog10/knowledge-automata/actions/workflows/ci.yml)

## What it is

Knowledge Automata is a general-purpose institutional memory for any group that makes decisions together: a project team, a company department, a research group, a neighbourhood association. A multi-agent LLM system turns messy artifacts (meeting notes, chats, documents) into validated, structured records, each traceable to the artifacts it came from, so people and AI tools can ask what the group knows and why. v0.1 targets project teams with PMI-aligned registers: a decision log and a risk register. It is open source (Apache 2.0) and built on Cohere's platform (Command, Embed, Rerank) behind a provider-agnostic service layer.

## Why

Knowledge is created constantly and lost just as fast. Decisions sit in meeting notes, chats and documents, so groups rediscover context and re-argue settled decisions over and over.

Even a perfect memory would still need a record. A record is shared truth that everyone can see and agree on. It makes ownership of decisions clear, keeps the history of how and why they changed, outlives any single tool, chat or model, and is what governance and audits rely on. Knowledge Automata keeps that record, so people and AI tools can answer from it.

Project management is the first application. Formal registers such as a decision log and a risk register solve this, but they are expensive to maintain by hand, which is why Agile teams often skip them. Knowledge Automata maintains them automatically as a side effect of normal work, so teams get PMI-quality records without the overhead.

## How it works

The system works as a closed loop:

1. **Sensor (intake):** checks, hashes and logs each incoming artifact in the Artifact Ledger, quarantining invalid or suspicious input.
2. **Governor (orchestrator):** identifies what the artifact contains and sends work orders to the relevant Registrars.
3. **Comparator (reconciliation):** retrieves related existing records and classifies the input as new, an update, a reaffirmation or a supersession.
4. **Registrars (specialist record keepers):** draft structured records; code validates them against a schema, assigns IDs and stores them.
5. **Governor:** marks the artifact as processed in the Ledger, listing the records it produced.

See [docs/architecture.md](docs/architecture.md) for roles, data flow and design rules.

## Status

Early development (v0.1 in progress). See [dev/STATUS.md](dev/STATUS.md).

## Getting started

Requires Python 3.11 or later and [uv](https://docs.astral.sh/uv/), which installs the exact dependency versions pinned in `uv.lock`. On Windows (PowerShell):

```powershell
uv sync --all-extras          # creates .venv and installs the locked dependencies
.\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env   # then add your Cohere API key
pytest
```

On macOS or Linux, activate with `source .venv/bin/activate` and copy with `cp .env.example .env`. Without uv, `pip install -e ".[dev]"` in a virtual environment still works, but does not use the lock file.

After changing dependencies in `pyproject.toml`, run `uv lock` and commit the updated `uv.lock`.

Keep the clone outside cloud-synced folders such as OneDrive or Dropbox: sync tools lock files inside `.git` and `.venv` while Git and uv are writing them. If you move the folder, delete `.venv` and run `uv sync --all-extras` again, because the editable install records the old path.

## How this project is built

Knowledge Automata is built by a human-led team: Miguel (owner) with two AI assistants, Claude (discovery, architecture, review) and Copilot (implementation), following the [AI-Assisted Software Engineering principles](https://github.com/miguelmog10/ai-assisted-software-engineering/blob/main/PRINCIPLES.md). Decisions are recorded in [docs/decisions/](docs/decisions/) and the working process lives in [dev/](dev/). Team rules are in [AGENTS.md](AGENTS.md).

## Background

Knowledge Automata is a ground-up redesign inspired by lessons from Chronicle, an earlier course project by the author. No code or files were carried over (see [ADR-0002](docs/decisions/0002-clean-room-rebuild.md)).

## Security

To report a vulnerability, see [SECURITY.md](SECURITY.md).

## Licence

[Apache 2.0](LICENSE).
