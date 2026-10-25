# Principles in practice

A running log of how the [AI-Assisted Software Engineering principles](https://github.com/miguelmog10/ai-assisted-software-engineering/blob/0d523881152cd622924aa800caf5264bb5e9ed81/PRINCIPLES.md) showed up while building this project: where they made the **product** better, where they helped the **team** of humans and AI assistants work together, and where a principle had to **bend**.

| # | Principle | # | Principle |
|---|---|---|---|
| P1 | Design before prompting | P9 | Testing is mandatory |
| P2 | Architecture is a first-class deliverable | P10 | Distrust the happy path |
| P3 | Plan continuously, adapt relentlessly | P11 | Build evidence, not just confidence |
| P4 | Maintain traceability | P12 | Optimise for outcomes, not code |
| P5 | AI generates. Humans own | P13 | Documentation is part of development |
| P6 | Small increments beat big bang development | P14 | Version everything that matters |
| P7 | Treat AI artifacts as engineering artifacts | P15 | Reduce technical debt as you go |
| P8 | Externalize memory | P16 | Reuse what compounds, delete what doesn't |

Entry format: date, principle, side (product, teamwork or bent), what happened, one line of evidence (file, ADR or commit). Newest entries go at the bottom.

## Entries

### 2026-10-24: P16 Reuse what compounds, delete what doesn't (product)

Rebuilt from scratch instead of forking Chronicle; carried forward learnings, not code.
Evidence: ADR-0002.

### 2026-10-24: P2 Architecture is a first-class deliverable (product)

Roles, data flow and contracts defined before any code.
Evidence: `docs/architecture.md`, ADR-0004.

### 2026-10-24: P4 Maintain traceability (product)

The Artifact Ledger links source artifacts and records in both directions.
Evidence: ADR-0006.

### 2026-10-24: P14 Version everything that matters (product)

The Ledger records model, prompt and schema versions so reprocessing can be targeted.
Evidence: ADR-0006.

### 2026-10-24: P10 Distrust the happy path (product)

The review of Chronicle showed duplicate decisions came from specialists having no context of existing records; fixed by design with the Comparator (reconciliation), not patched.
Evidence: ADR-0002, ADR-0004.

### 2026-10-24: P8 Externalize memory (teamwork)

The long planning chat was compacted, losing detail, which is why decisions were moved into the repo through a handoff.
Evidence: `dev/handoffs/001-scaffolding.md`.

### 2026-10-24: P5 AI generates. Humans own (teamwork)

Work split between Claude (design and review), Copilot (implementation) and Miguel (owner and approver); Copilot plans first and waits for approval.
Evidence: `AGENTS.md`.

### 2026-10-24: P11 Build evidence, not just confidence (bent)

The full framework was scaled down to a light standard to fit a weekend build, with deferred items tracked explicitly.
Evidence: ADR-0008.

### 2026-10-24: P2 Architecture is a first-class deliverable (product)

Separating a domain-neutral core from domain-specific Registrars (specialist record keepers) before writing code keeps the system open to other kinds of groups.
Evidence: ADR-0009.

### 2026-10-24: P5 AI generates. Humans own (teamwork)

Branch protection means every AI-generated change reaches `main` only through a pull request the owner merges.
Evidence: `.github/pull_request_template.md`, repository ruleset.

### 2026-10-24: Core thesis: AI lowers the cost of engineering discipline (teamwork)

The owner, a mechatronics engineer rather than a career software developer, set up industry-standard repository practice (branch protection, PR-only workflow, squash merges, secret scanning, CI as a required check) in one conversation, with an AI explaining each setting and flagging traps such as required reviews locking out a solo owner. Expert guidance on demand made proper engineering the cheap default, as argued in the [LinkedIn post](https://github.com/miguelmog10/ai-assisted-software-engineering/blob/0d523881152cd622924aa800caf5264bb5e9ed81/posts/linkedin-launch-post.md). Caveat: the AI is a strong second opinion, not an authority; important settings are still verified by the owner (P5).
Evidence: handoff 001 Addendum B, repository ruleset.

### 2026-10-24: P10 Distrust the happy path (product)

Supply-chain security planned into the first PR, prompted by the owner's study of the EU Cyber Resilience Act.
Evidence: ADR-0010, `SECURITY.md`.

### 2026-10-24: P11 Build evidence, not just confidence (product)

The SBOM and audit results give each release checkable evidence of what it contains.
Evidence: ADR-0010.

### 2026-10-25: P5 AI generates. Humans own (teamwork)

Copilot reviewed Claude's handoff before implementation and caught several inconsistencies (PR ownership, handoff recommit, CI triggers, version duplication); the owner resolved them.
Evidence: PR description for handoff 001.

### 2026-10-25: P10 Distrust the happy path (product)

One aggregate required check (`ci-ok`) avoids the stale-check and skipped-check traps: changing the Python matrix never leaves branch protection waiting on an old check name, and a skipped job cannot count as a pass.
Evidence: `.github/workflows/ci.yml`.

### 2026-10-25: P2 Architecture is a first-class deliverable (product)

The record schemas were designed by Miguel and Claude before implementation, as language-neutral JSON Schema files, and handed to Copilot as a contract rather than generated while coding.
Evidence: `schemas/`, `dev/handoffs/002-register-schemas.md`.

### 2026-10-25: P5 AI generates. Humans own (teamwork)

Miguel's review of Claude's record design caught that links between records are also LLM judgements. The design changed so code checks the Comparator's proposed links instead of trusting them.
Evidence: ADR-0011.

### 2026-10-25: P10 Distrust the happy path (product)

Every record must carry quotes from its artifact, and code checks they really appear there, so a record invented from nothing is rejected by a cheap, deterministic check.
Evidence: ADR-0011, `src/knowledge_automata/core/evidence.py`.

### 2026-10-25: P5 AI generates. Humans own (teamwork)

Copilot's plan review of handoff 002 caught three problems before any code was written: `enum` fields without `"type": "string"` (every Cohere structured-output example pairs them), a `date-time` check based on `datetime.fromisoformat` alone, which would have accepted loose forms such as `2026-10-25 11:43`, and a conflict between the handoff ("no README change") and the definition of done in `AGENTS.md` once the lock file changed the setup steps. Miguel decided each one and committed the schema fix before implementation started.
Evidence: handoff 002 "Revised" line, commit `62d0dc6`, `src/knowledge_automata/core/validation.py`.

### 2026-10-25: P12 Optimise for outcomes, not code (product)

Adopted the design principle "use the LLM only where judgement is needed; use deterministic code for everything that can be checked". Validation, IDs, evidence checks, views and cost tracking stay in code: cheaper, faster and repeatable, and focused on the outcome rather than on using AI everywhere because it is fashionable.
Evidence: `docs/architecture.md` (Design principle).

### 2026-10-25: P3 Plan continuously, adapt relentlessly (product)

Moved a thin vertical slice (one artifact through the Decision Registrar to one validated record on a real Command call) ahead of the Sensor, so the riskiest integration is proven early and the repository shows the Cohere path working end to end.
Evidence: `dev/backlog.md`, `dev/STATUS.md`.

### 2026-10-25: Core thesis: AI lowers the cost of engineering discipline (teamwork)

Moving the local clone out of OneDrive (which had locked `.venv` during `uv sync`) hid several traps for a newcomer: the editable install still pointed at the old folder, so tests would have silently run the old copy; uv had been installed inside the old `.venv`; and PowerShell blocked the activation script. Claude caught the silent one by inspecting the virtual environment before any test run, turning what could have been hours of confusion into a few guided steps. Caveat as before: the owner verified each step (P5).
Evidence: README "Getting started", `dev/tool-feedback.md`.

### 2026-10-25: P10 Distrust the happy path (product)

An autouse test fixture blocks every socket connection, so a test that accidentally reaches Cohere fails loudly instead of quietly spending trial calls (capped at 1,000 a month). The adapter is still tested against the real SDK, through an in-memory HTTP transport.
Evidence: `tests/conftest.py`, `tests/llm/test_cohere_adapter.py`.

### 2026-10-25: P4 Maintain traceability (product)

Every LLM call writes an event that names the agent and the artifact but never holds prompts, artifact text or output. Cost and failures stay traceable to artifacts and records, while the log stays safe to share and cannot become a second, unvalidated copy of the institutional memory.
Evidence: ADR-0012, `schemas/core/llm-event.v1.json`, `src/knowledge_automata/llm/observed.py`.

### 2026-10-25: P11 Build evidence, not just confidence (product)

The Cohere docs disagree on the `response_format` field name and are silent on some keywords. Instead of guessing, the field name is one constant, unsupported schema keywords raise an error, and a small manual smoke check with a schema the model would only follow if enforced ("vermilion" sky) settles the question with evidence.
Evidence: `scripts/cohere_smoke.py`, `src/knowledge_automata/llm/provider_schema.py`.

### 2026-10-25: P12 Optimise for outcomes, not code (product)

The price table ships empty for Cohere models because the pricing page publishes no per-token prices for them. Leaving the cost out, rather than copying a number from a third-party site, keeps the cost figures trustworthy when they do appear.
Evidence: `src/knowledge_automata/llm/prices.toml`, `dev/tool-feedback.md`.
