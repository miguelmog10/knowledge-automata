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
