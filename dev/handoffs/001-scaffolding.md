# Handoff 001: Repository scaffolding for Knowledge Automata

- **From:** Claude (discovery, architecture, review)
- **To:** Opus in GitHub Copilot, VS Code (implementation)
- **Owner and approver:** Miguel Morales
- **Date:** 2026-10-24
- **Scope:** repository structure, tooling, CI and foundational documents. No agent logic, no LLM calls.

---

## 1. Context

Knowledge Automata is a multi-agent LLM system that turns messy project artifacts (meeting notes, chats, documents) into structured, PMI-aligned project records such as a decision log and a risk register. The result is a living project memory that humans and AI tools can query, with full traceability back to the original artifacts.

Key facts:

- It is a public, open-source portfolio project (Apache 2.0), built on Cohere's platform (Command, Embed, Rerank) behind a provider-agnostic service layer.
- It is a deliberate application of Miguel's framework, *AI-Assisted Software Engineering* (four pillars: think before you generate, generate responsibly, prove it works, build for the future). The repo should read like good engineering, not a hackathon dump.
- It is built by a mixed human and AI team:
  - **Miguel:** owner. Approves plans, merges and decisions.
  - **Claude (claude.ai project):** discovery, architecture, schemas, review and second opinion.
  - **Opus (you, in VS Code):** planning and implementation.

**The framework.** Full text: [PRINCIPLES.md](https://github.com/miguelmog10/ai-assisted-software-engineering/blob/0d523881152cd622924aa800caf5264bb5e9ed81/PRINCIPLES.md). Link to it from `README.md` (section 6) and from `AGENTS.md`. The principles, as referenced by
number (P1 to P16) in this repo:

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

Include this table in `AGENTS.md` and at the top of `dev/principles-in-practice.md`.

**Hard rule: clean-room rebuild.** Miguel previously built a course project called Chronicle. Do **not** open, read, copy or adapt any file from the Chronicle repository. Every file in this repo is written from scratch. Learnings are carried forward only as written decisions (see ADR-0002).

## 2. How to work on this task

1. **Plan first.** Read this whole document, then reply with a short plan: the file tree you will create and the commit sequence. **Wait for Miguel's approval** before writing files.
2. **Implement in small commits** following the commit conventions in section 5.
3. **Stop after scaffolding.** Do not implement agents, schemas or Cohere calls. Those come in later handoffs.
4. If anything here is ambiguous or seems wrong, ask instead of guessing, and add it to `dev/backlog.md` under *Open questions*.
5. Finish by updating `dev/STATUS.md` and reporting what you did.

## 3. Target structure

The repo already exists with `README.md`, a Python `.gitignore` and the Apache 2.0 `LICENSE` created by GitHub. Keep the licence untouched.

```
knowledge-automata/
├── AGENTS.md                     # Shared rules for every AI assistant and human contributor
├── README.md                     # Product-facing overview (rewrite the GitHub stub)
├── LICENSE                       # Apache 2.0 (already present)
├── .env.example                  # Documented environment variables, no real values
├── .gitignore                    # Extend the GitHub Python template (see 4.4)
├── pyproject.toml
├── .github/
│   └── workflows/
│       └── ci.yml
├── docs/                         # PRODUCT layer: what the system is and why
│   ├── architecture.md
│   └── decisions/
│       ├── README.md             # ADR index
│       ├── 0000-template.md
│       ├── 0001-license-apache-2.md
│       ├── 0002-clean-room-rebuild.md
│       ├── 0003-provider-agnostic-llm-service-layer.md
│       ├── 0004-closed-loop-architecture-and-roles.md
│       ├── 0005-validated-structured-records.md
│       ├── 0006-artifact-ledger.md
│       ├── 0007-pmi-aligned-registers.md
│       └── 0008-light-engineering-standard-for-v0-1.md
├── dev/                          # PROCESS layer: how we are building it
│   ├── STATUS.md                 # Handoff file: where we are, what's next
│   ├── backlog.md
│   ├── principles-in-practice.md
│   ├── tool-feedback.md
│   └── handoffs/
│       └── 001-scaffolding.md    # This document, committed as-is
├── prompts/                      # Versioned agent prompts (empty for now, .gitkeep)
├── schemas/                      # Record schemas (empty for now, .gitkeep)
├── examples/                     # Sample fictional project data (empty for now, .gitkeep)
├── src/
│   └── knowledge_automata/
│       └── __init__.py           # __version__ = "0.0.1" and a module docstring
└── tests/
    └── test_smoke.py             # Imports the package and checks __version__
```

**Why two documentation layers:** `docs/` explains the product and stays valuable forever. `dev/` holds the working process (status, backlog, handoffs) and gets lighter once the project matures. ADRs live in `docs/` because they explain why the system looks the way it does.

## 4. File-by-file requirements

### 4.1 Tooling

- **Python 3.11+**, `src/` layout, package name `knowledge_automata`.
- `pyproject.toml`: project metadata (name `knowledge-automata`, version `0.0.1`, licence Apache-2.0, author Miguel Morales), build backend of your choice, and optional dependency group `dev` with `pytest` and `ruff`. No runtime dependencies yet.
- Configure **ruff** (lint and format) and **pytest** in `pyproject.toml`. Keep the rule set moderate; this is a prototype.

### 4.2 CI (`.github/workflows/ci.yml`)

On push and pull request: set up Python 3.11 and 3.12, install `.[dev]`, run `ruff check`, `ruff format --check` and `pytest`. Keep it short and readable.

### 4.3 `.env.example`

```
# Cohere API key (https://dashboard.cohere.com). Never commit a real key.
CO_API_KEY=
```

### 4.4 `.gitignore` additions

Add: `.env`, `.venv/`, a `runtime/` directory for local pipeline data (registers, ledger, logs produced while running on real inputs), and common editor folders. Never ignore `examples/`.

### 4.5 `README.md`

Rewrite the stub. Sections:

1. **What it is:** one paragraph (use the context in section 1).
2. **Why:** project knowledge is scattered across meeting notes, chats and documents, so decisions get lost and context is rediscovered over and over. Formal registers (decision log, risk register) solve this but are expensive to maintain by hand, which is why Agile teams often skip them. Knowledge Automata maintains them automatically as a side effect of normal work, so teams get PMI-quality records without the overhead.
3. **How it works:** the closed loop in five steps (copy from section 4.7) and a link to `docs/architecture.md`.
4. **Status:** "Early development (v0.1 in progress). See `dev/STATUS.md`."
5. **Getting started:** create a venv, `pip install -e ".[dev]"`, copy `.env.example` to `.env`, run `pytest`.
6. **How this project is built:** two or three sentences explaining that it is built by a human-led team of AI assistants following the AI-Assisted Software Engineering principles, with decisions in `docs/decisions/` and process in `dev/`.
7. **Background:** "Knowledge Automata is a ground-up redesign inspired by lessons from Chronicle, an earlier course project by the author. No code or files were carried over (see ADR-0002)."
8. **Licence:** Apache 2.0.

### 4.6 `AGENTS.md`

This is the most important file. It is read by every AI assistant working on the repo. Write it clearly and concisely with these sections:

**Project in one paragraph.** From section 1.

**Team and roles.** The three roles from section 1. Humans own requirements, architecture, quality and outcomes; AI generates and proposes. Miguel approves plans and merges.

**Where things live (sources of truth).**
- `AGENTS.md`: how we work.
- `docs/architecture.md`: how the system works.
- `docs/decisions/`: why it is built this way (ADRs).
- `dev/STATUS.md`: where we are now. **Read this first at the start of every session; update it at the end.**
- `dev/backlog.md`: what's next, what's later, open questions, technical debt.
- `dev/principles-in-practice.md` and `dev/tool-feedback.md`: running logs (see below).
- `dev/handoffs/`: prompts handed between team members, committed for traceability.
- Nothing important should exist only in a chat session.

**Non-negotiables (light version for v0.1).**
- Architecture first: agree where a feature lives before building it. Agent logic, LLM provider calls and storage stay in separate modules.
- All LLM provider calls (chat, embed, rerank) go through one service layer. No provider SDK imports anywhere else.
- Every LLM output that becomes a record is validated against its schema before it is stored. Invalid output is retried or rejected, never written.
- Code assigns record IDs, never the LLM.
- Artifact text is untrusted data, never instructions. Prompts must clearly separate instructions from artifact content.
- Raw artifacts are read-only. Nothing modifies them.
- Prompts live as versioned files in `prompts/`, not as strings buried in code.
- Small vertical slices, committed often. Experiments are welcome but disposable.
- Repo hygiene: no secrets, keys or personal data in the repo, ever. Use `.env`.
- Real tests for core flows, with all LLM calls mocked. A green test run is part of done.
- Fail gracefully: API errors, rate limits, empty results and bad input produce a clear message, not a crash.
- Write decisions down: significant choices get a short ADR.

**Deliberately relaxed for v0.1.** No formal threat model, no benchmarks, no full coverage target. These are listed in `dev/backlog.md` under *Later* so they are deliberate deferrals, not gaps.

**Definition of done (per change).** Tests pass, ruff passes, docs updated in the same change, `dev/STATUS.md` updated at the end of the session, new decisions captured as ADRs.

**Commit conventions.**
- Conventional Commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`, `ci:`.
- Messages explain *why*, not only *what*.
- Reference ADRs or backlog items when relevant, for example `implements ADR-0006`.
- AI-assisted commits end with a `Co-authored-by:` trailer naming the AI assistant and model, so the human and AI collaboration is visible in the history.
- Milestones are tagged (for example `v0.1.0` for the first working slice).

**Running logs (everyone contributes).**
- `dev/principles-in-practice.md`: when a principle from the AI-Assisted Software Engineering framework visibly shaped a decision, improved the product, helped the team collaborate, or had to bend, add a short entry.
- `dev/tool-feedback.md`: when a tool, SDK or doc (Cohere, Copilot, Python libraries, anything) is confusing, missing something or surprisingly good, add a short entry. These may later become upstream issues or pull requests.

**Writing style for repo documents.** Plain, concise English. Do not use em dashes; use commas, colons or parentheses instead. Pair every themed role name with its plain role the first time it appears in a document, for example "Governor (orchestrator)".

**Clean-room rule.** Never read or copy files from the Chronicle repository (ADR-0002).

### 4.7 `docs/architecture.md`

A first version, clearly marked *Draft, v0.1*. Sections:

**Overview.** Knowledge Automata is designed as a closed-loop control system for project knowledge: it senses inputs, decides what to do, compares against current state, acts, and monitors the result, with a human operator overseeing it.

**Roles.**

| Name | Plain role | Responsibility | v0.1 |
|---|---|---|---|
| Sensor | Intake and input guardrail | Validates, hashes, normalizes and logs incoming artifacts in the Artifact Ledger; quarantines invalid or suspicious input | Yes (deterministic checks only) |
| Governor | Orchestrator and router | Analyzes an accepted artifact and issues work orders to the relevant Registrars; marks artifacts processed or failed | Yes |
| Comparator | Reconciliation | Before anything is written, retrieves related existing records (Embed + Rerank) and classifies the input as new, update, reaffirmation or supersession | Yes |
| Registrars | Specialist record keepers | One per PMI register; drafts structured records that code validates, assigns IDs to and stores | Decision and Risk |
| Observer | Quality control | Periodic health and cross-register consistency checks | Later |
| Oracle | Query interface | Answers questions over the registers with citations to records and source artifacts | Stretch |
| Operator | Human in the loop | Approves sensitive changes, reviews quarantine, overrides the system. A role, not an agent | Later (workflow) |

**Data flow for one artifact.**
1. **Sensor:** the artifact arrives. The Sensor checks it, hashes it and records it in the Artifact Ledger as accepted, quarantined or rejected. If accepted, it normalizes the text and adds metadata.
2. **Governor:** reads the artifact, identifies its content (for example two decisions and one risk) and sends work orders to the Decision and Risk Registrars.
3. **Comparator:** for each work order, retrieves related existing records and tells the Registrar whether this is new, an update, a reaffirmation or a supersession.
4. **Registrars:** draft records as structured data. Code validates them against the schema, assigns IDs and stores them. Independent Registrars can run in parallel.
5. **Governor:** marks the artifact as processed in the Ledger, listing the records it produced.

Around this loop: the Observer checks register health, the Oracle answers questions from stored records, and the Operator approves sensitive changes.

**Write rules.** Raw artifacts are read-only. Each register defines its own write rule (append-only, update in place, or supersede with a link). Every record links back to its source artifacts, and every Ledger entry links forward to the records it produced.

**Patterns and terminology.**

| Concept in this project | Established term |
|---|---|
| Overall system | Multi-agent system, orchestrator-workers pattern |
| Governor | Orchestrator, routing |
| Registrars working simultaneously | Parallelization |
| Comparator | Retrieval-augmented generation (RAG) for entity resolution |
| Oracle | Retrieval-augmented generation (RAG) with citations |
| Schema validation with retry | Evaluator-optimizer loop |
| Sensor | Input guardrails |
| Operator | Human-in-the-loop |
| Shared registers | Blackboard architecture |
| The full closed loop | MAPE-K loop (Monitor, Analyse, Plan, Execute over shared Knowledge), from IBM's autonomic computing work |

**Security: defence in depth.** The Sensor is the first line of defence, not the only one. Artifact text is always treated as data, schema validation blocks malformed writes, and the Operator approves sensitive changes. Together these protect the project memory from contamination (memory poisoning). Prompt-injection and relevance checks in the Sensor are planned (see backlog). These guardrails are also relevant evidence for future cybersecurity compliance work such as the EU Cyber Resilience Act.

**Observability.** Every LLM call is logged by the service layer as one structured JSON event: agent, model, operation, input and output tokens, latency and artifact ID. A small, dated price table in configuration converts tokens to cost. Because the Ledger links artifacts to records, cost per artifact and per record can be derived. The event format should stay compatible with a later move to a standard such as OpenTelemetry.

**Vision: an architecture, not just an implementation.** Each role is defined by a contract: its inputs, its outputs, the schemas it must follow and what it may write. This Python package is the **reference implementation**. Anything that honours a role's contract could fill that role, for example a GitHub Copilot agent, an Atlassian Rovo agent or a CI pipeline step, connected to systems such as Jira, Confluence or Microsoft Teams.

### 4.8 ADRs (`docs/decisions/`)

Use a lightweight format (`0000-template.md`): Title, Status, Date, Context, Decision, Consequences. Keep each one short. All dated 2026-10-24 with status **Accepted** unless noted. `README.md` is an index table of number, title and status.

- **0001 License: Apache 2.0.** Context: first open-source project; public portfolio. Decision: Apache 2.0. Consequences: permissive and commercial-friendly; adds an explicit patent grant and patent retaliation clause compared with MIT; requires attribution; does not grant trademark rights, so the project name stays with the owner. Future proprietary work can be built on top as separate code.
- **0002 Clean-room rebuild.** Context: the author's earlier course project, Chronicle, explored similar ideas. Decision: build Knowledge Automata from scratch; port zero files; carry forward only learnings, recorded as decisions. Consequences: clear ownership and a clean history; applies the principle "reuse what compounds, delete what doesn't". Learnings carried forward: keep planning separate from writing; inject the LLM client so tests run without network calls; combine deterministic and LLM-based quality checks; maintain traceability to source artifacts; keep prompts as files; keep a status file for session handoff. Gaps fixed by design: specialists lacked context of existing records (causing duplicates), free-form Markdown was the source of truth, the LLM generated IDs, the provider was coupled to the code, and schemas overlapped.
- **0003 Provider-agnostic LLM service layer.** Decision: one internal interface each for chat, embeddings and reranking; Cohere is the first implementation; no provider SDK is imported outside the adapter. Consequences: swapping models or providers is a contained change; tests use a fake implementation; observability is captured in one place.
- **0004 Closed-loop architecture and role names.** Decision: adopt the Sensor, Governor, Comparator, Registrars, Observer, Oracle and Operator roles described in `docs/architecture.md`, themed as a closed-loop control system. Consequences: names are systems-oriented and general purpose; every themed name is paired with its plain role in docs and docstrings.
- **0005 Validated structured records as the source of truth.** Decision: records are stored as structured data (JSON) validated against versioned schemas, and Markdown views are generated from them. LLM output must pass schema validation before storage; code assigns IDs. Consequences: malformed output cannot enter the memory; most structural audits become unnecessary; storage is git-friendly. Status: Accepted; storage backend details to be refined when the first register is built.
- **0006 Artifact Ledger.** Decision: maintain a ledger of every artifact the system receives: identity (ID, title, source URI, source type, artifact date), content hash, status (`received`, then `accepted`, `quarantined` or `rejected`, then `processed` or `failed`) with a reason, timestamps, the records produced, and the model, prompt and schema versions used. Each status transition has a single owner: the Sensor sets accepted, quarantined or rejected; the Governor sets processed or failed. Quarantined input is kept, never silently discarded. Consequences: two-way traceability, idempotent re-runs, targeted reprocessing when prompts or schemas change, and Operator visibility.
- **0007 PMI-aligned registers.** Decision: record schemas are defined by this project and explicitly mapped to artifact descriptions in PMI's PMBOK Guide (decision log, risk register, issue log, assumption log, change log, lessons learned register, stakeholder register). v0.1 implements the decision log and risk register. Consequences: credible, recognizable structure for project managers; Agile-compatible because maintenance is automated. PMI describes artifact contents but does not publish formal schemas, so each schema documents its mapping. Open question: which PMBOK edition to cite.
- **0008 Light engineering standard for v0.1.** Decision: apply the AI-Assisted Software Engineering principles at a level that fits a portfolio prototype: the non-negotiables in `AGENTS.md`, plus short ADRs, schema validation, prompts as files, a small evaluation set, minimal CI and an explicit *Later* list. Consequences: the repo demonstrates good practice without production overhead; relaxed items are deliberate and tracked.

### 4.9 `dev/STATUS.md`

Sections: *Last updated*, *Current phase* ("Scaffolding, handoff 001"), *Done*, *In progress*, *Next* (handoff 002: Decision and Risk register schemas, designed with Claude), *Blockers*, *Notes for the next session*. Keep it short and factual.

### 4.10 `dev/backlog.md`

**Now (v0.1, first working slice)**
- Decision and Risk register schemas, PMI-mapped (design with Claude first).
- LLM service layer with a Cohere adapter and a fake adapter for tests.
- Structured event logging for every LLM call, plus a dated price table and token-to-cost function.
- Sensor with deterministic checks (empty, unsupported format, oversized, encoding, duplicate hash), Artifact Ledger and quarantine path.
- Governor (classification and work orders).
- Comparator using Embed and Rerank.
- Decision Registrar and Risk Registrar.
- Fictional sample project in `examples/`, doubling as a small evaluation set with expected records.
- CLI entry point to run the pipeline over a folder.

**Stretch (v0.1)**
- Oracle: question answering over the registers with citations.

**Later**
- Observer: periodic health and cross-register consistency checks.
- Remaining registrars: issue log, assumption log, change log, lessons learned, stakeholder register; glossary as a minor register.
- Operator approval workflow for sensitive changes; quarantine review and release.
- Sensor relevance check and prompt-injection detection.
- Oracle insight feedback loop: Operator-confirmed conclusions from Oracle conversations are saved as new raw artifacts ("insight notes") and re-enter through the Sensor, so there is still one write path.
- Enterprise connectors (Jira, Confluence, Microsoft Teams) as Sensor sources.
- Alternative LLM providers behind the service layer.
- OpenTelemetry-compatible observability; analytics over the event log.
- Threat model and security review; cybersecurity compliance considerations (for example the EU Cyber Resilience Act).
- Role contracts documented so other platforms can implement roles (reference implementation vision).

**Open questions**
- Which PMBOK edition should the schemas cite?
- Storage details for records and the ledger (JSON files per record, one file per register, or SQLite).

**Technical debt**
- (empty)

### 4.11 `dev/principles-in-practice.md`

Intro: a running log of how the AI-Assisted Software Engineering principles showed up while building this project, both where they made the **product** better and where they helped the **team** of humans and AI assistants work together, plus where a principle had to bend. Format per entry: date, principle, side (product, teamwork or bent), what happened, one line of evidence (file, ADR or commit).

Seed entries, all 2026-10-24:
- **P16 Reuse what compounds, delete what doesn't** (product): rebuilt from scratch instead of forking Chronicle; carried forward learnings, not code. Evidence: ADR-0002.
- **P2 Architecture is a first-class deliverable** (product): roles, data flow and contracts defined before any code. Evidence: `docs/architecture.md`, ADR-0004.
- **P4 Maintain traceability** (product): the Artifact Ledger links source artifacts and records in both directions. Evidence: ADR-0006.
- **P14 Version everything that matters** (product): the Ledger records model, prompt and schema versions so reprocessing can be targeted. Evidence: ADR-0006.
- **P10 Distrust the happy path** (product): the review of Chronicle showed duplicate decisions came from specialists having no context of existing records; fixed by design with the Comparator, not patched. Evidence: ADR-0002, ADR-0004.
- **P8 Externalize memory** (teamwork): the long planning chat was compacted, losing detail, which is why decisions were moved into the repo through this handoff. Evidence: `dev/handoffs/001-scaffolding.md`.
- **P5 AI generates, humans own** (teamwork): work split between Claude (design and review), Opus (implementation) and Miguel (owner and approver); Opus plans first and waits for approval. Evidence: `AGENTS.md`.
- **P1 Design before prompting** (bent): the full framework was scaled down to a light standard to fit a weekend build, with deferred items tracked explicitly. Evidence: ADR-0008.

### 4.12 `dev/tool-feedback.md`

Intro: notes on tools, SDKs and documentation used while building, so useful feedback is not lost and can later become upstream issues, pull requests or posts. Format per entry: date, tool, type (confusing, missing, bug, delight), note, suggested improvement. Start with no entries other than a commented example.

### 4.13 `dev/handoffs/001-scaffolding.md`

Already committed by Miguel on this branch. Do not modify or recommit it.

## 5. Suggested commit sequence

1. `chore: add project tooling, package skeleton and smoke test`
2. `ci: add lint and test workflow`
3. `docs: add AGENTS.md with team conventions`
4. `docs: add architecture overview and ADRs 0001-0008`
5. `docs: add README`
6. `docs: add dev process files and handoff 001`

Each ends with a `Co-authored-by:` trailer for the AI assistant. Run `ruff` and `pytest` before each commit.

## 6. Done when

- The tree in section 3 exists, `pip install -e ".[dev]"` works, `ruff check`, `ruff format --check` and `pytest` pass locally, and CI is green on GitHub.
- No file was read from or copied from Chronicle.
- No secrets in the repo.
- `dev/STATUS.md` is updated and you have reported back with a summary and anything you were unsure about.

---

# Handoff 001 Addendum A: Positioning as general-purpose institutional memory

Note: this addendum wins where it conflicts with earlier sections.

## A.1 Positioning change

Knowledge Automata is not only a project-management tool. It is a general-purpose **institutional memory** for any group that makes decisions together: a project team, a company department, a research group, a neighbourhood association. In systems terms, any such group is a system that produces knowledge. **Project management is the first application**, implemented with PMI-aligned registers. The roles, the Artifact Ledger and the write rules are domain-neutral; only the Registrars and their schemas are domain-specific.

Avoid describing the product as "project memory" in headings or taglines. Use "institutional memory" or "collective memory" for the general idea, and "project" only when talking about the first application.

## A.2 Changes to specific files

**README.md**

- Directly under the title, add the tagline: *Knowledge on autopilot.* followed by: *The living memory of any group that makes decisions together.*
- *What it is:* describe the general purpose first, then state that v0.1 targets project teams with PMI-aligned registers (decision log, risk register).
- *Why:* open with the general problem (knowledge is created constantly and lost just as fast, so groups rediscover context and re-argue settled decisions), then give the project-management case as the first application.

**AGENTS.md**

- *Project in one paragraph:* use the general positioning from A.1.

**docs/architecture.md**

- *Overview:* describe a closed-loop control system for the knowledge of any decision-making group.
- Add a short section, *Domains and applications*: the core (Sensor, Governor, Comparator, Observer, Oracle, Operator, Artifact Ledger) is domain-neutral. A domain is a set of Registrars and schemas. v0.1 ships the project-management domain (PMI). Examples of possible future domains: an association (charter, motions, member decisions), a research group (hypotheses, experiments, findings).

**docs/decisions/**

- Add **ADR-0009 General-purpose core, project management as first domain.** Context: the same knowledge-loss problem exists in any decision-making group, not only projects. Decision: keep the core roles, Ledger and write rules domain-neutral; package Registrars and schemas per domain; ship project management (PMI) first. Consequences: broader vision and reuse; domain-specific vocabulary stays out of core modules; slightly more care needed when naming core concepts. Update the ADR index and the tree in section 3.
- ADR-0007: add one sentence noting the PMI registers are the first domain under ADR-0009.

**dev/backlog.md**

- *Later:* add "Additional domains beyond project management (for example associations or research groups), each as its own set of Registrars and schemas."

**dev/principles-in-practice.md**

- Add entry, 2026-10-24, **P2 Architecture is a first-class deliverable** (product): separating a domain-neutral core from domain-specific Registrars before writing code keeps the system open to other kinds of groups. Evidence: ADR-0009.

## A.3 Commit sequence

No new commits needed: include ADR-0009 in commit 4 and apply the other changes in the commits that create those files.

# Handoff 001 Addendum B: GitHub workflow and repo settings

Miguel configures the GitHub settings in B.1 by hand; Opus implements B.2 to B.4.

## B.1 Repository settings (Miguel, in GitHub)

- **Ruleset on `main`:** require a pull request before merging, block force pushes, block deletion. No required approvals (a solo owner cannot approve their own PR).
- **Required status checks:** add the CI jobs to the ruleset only after the first PR has run CI once, because GitHub can only require checks it has already seen.
- **Merge options:** allow squash merging only; automatically delete head branches after merge.
- **Security:** enable secret scanning with push protection, and Dependabot alerts.

## B.2 Branch and pull request workflow (everyone)

- Never commit directly to `main`. One short-lived branch per piece of work, named with a Conventional Commits type, for example `chore/scaffolding`, `feat/sensor`, `docs/adr-0010`.
- Opus works on the branch and opens a pull request; Miguel reviews and merges. This is "AI generates, humans own" built into the workflow.
- PR titles follow Conventional Commits, because the squash merge uses the PR title as the commit on `main`. The `Co-authored-by:` trailer goes in the squash commit body.
- Handoff 001 is delivered as a single PR from `chore/scaffolding`. Keep the small commits from section 5 inside the branch.

## B.3 New files

- `.github/pull_request_template.md` with four short headings: *What*, *Why*, *Related ADRs or backlog items*, *How it was tested*, plus a checklist: tests pass, ruff passes, docs updated, `dev/STATUS.md` updated.
- Add it to the tree in section 3.

## B.4 Changes to existing files

- **README.md:** add a CI status badge under the tagline.
- **AGENTS.md:** add a *Branches and pull requests* section summarising B.2.
- **dev/principles-in-practice.md:** add entry, 2026-10-24, **P5 AI generates, humans own** (teamwork): branch protection means every AI-generated change reaches `main` only through a pull request the owner merges. Evidence: `.github/pull_request_template.md`, repository ruleset.

- Add a second entry, 2026-10-24, **Core thesis: AI lowers the cost of engineering discipline** (teamwork): the owner, a mechatronics engineer rather than a career software developer, set up industry-standard repository practice (branch protection, PR-only workflow, squash merges, secret scanning, CI as a required check) in one conversation, with an AI explaining each setting and flagging traps such as required reviews locking out a solo owner. Expert guidance on demand made proper engineering the cheap default, as argued in the [LinkedIn post](https://github.com/miguelmog10/ai-assisted-software-engineering/blob/0d523881152cd622924aa800caf5264bb5e9ed81/posts/linkedin-launch-post.md). Caveat: the AI is a strong second opinion, not an authority; important settings are still verified by the owner (P5). Evidence: Addendum B, repository ruleset.

# Handoff 001 Addendum C: Supply-chain security baseline

It applies to the same scaffolding PR. Context: the EU Cyber Resilience Act (CRA) expects a software bill of materials (SBOM), no known exploitable vulnerabilities, timely security updates and coordinated vulnerability disclosure. The CRA targets commercial products on the EU market and largely exempts non-commercial open source, so this is readiness and good practice, not a compliance claim.

## C.1 Repository settings (Miguel, by hand)

- Settings, Code security: turn on the dependency graph (default for public repos), Dependabot alerts and Dependabot security updates.
- Turn on private vulnerability reporting, so people can report issues without opening a public issue.
- Secret scanning with push protection, as already listed in B.1.

## C.2 Files and changes for Opus

- `.github/dependabot.yml`: weekly version updates for the `pip` and `github-actions` ecosystems, a small open-PR limit (5), and Conventional Commit prefixes (`chore(deps):` for pip, `ci(deps):` for actions).
- `ci.yml`: set `permissions: contents: read` at the top (least privilege); pin every third-party action to a full commit SHA with the version in a comment; add a `pip-audit` step (add `pip-audit` to the `dev` extras) that fails the build on known vulnerabilities.
- `SECURITY.md`: supported versions (latest `main` only while pre-1.0); how to report (GitHub private vulnerability reporting, never public issues); a best-effort response target for a solo maintainer (acknowledge within 7 days); scope notes saying prompt injection and contamination of the project memory are in scope.
- `README.md`: a one-line Security section linking to `SECURITY.md`.
- No lock file yet, since there are no runtime dependencies. Add one with the first runtime dependency (the Cohere SDK); see the backlog.

## C.3 Documentation changes

- New ADR, next free number (expected **ADR-0010**), **Supply-chain security baseline**. Context: CRA expectations as above, stated as readiness rather than obligation. Decision: Dependabot alerts and updates; `pip-audit` in CI; pinned actions with least-privilege permissions; `SECURITY.md` plus private vulnerability reporting; a lock file from the first runtime dependency; a CycloneDX SBOM generated in CI and attached to every tagged release, starting with v0.1.0. Consequences: vulnerable dependencies are caught before merge, every release documents its components, and reporters have a private channel; small ongoing cost of reviewing Dependabot PRs.
- `docs/architecture.md`, Security section: add one sentence saying supply-chain security (dependency auditing, pinned CI actions, SBOM per release) complements the runtime defence in depth.
- `dev/backlog.md`, **Now**: add a lock file with the first runtime dependency; add a release workflow that generates a CycloneDX SBOM and attaches it to the v0.1.0 tag.
- `dev/backlog.md`, **Later**: CodeQL code scanning (free for public repos); OpenSSF Scorecard; build provenance and signed releases (GitHub artifact attestations, SLSA); mypy type checking, a coverage report, and an evaluation job against real Cohere models that runs manually or on `main` only, never on pull requests from forks.
- `dev/backlog.md`, **Later**, a new group *When collaborators join*: raise required approvals to 1; add CODEOWNERS with code-owner review for `schemas/`, `docs/decisions/` and `AGENTS.md`; dismiss stale approvals and require conversation resolution; add CONTRIBUTING.md, a code of conduct and issue templates; keep approval required for workflow runs from first-time contributors; decide between a CLA and a DCO before the first external pull request.
- `dev/principles-in-practice.md`, two entries dated 2026-10-24: **P10 Distrust the happy path** (product): supply-chain security planned into the first PR, prompted by the owner's study of the CRA. Evidence: ADR-0010, `SECURITY.md`. **P11 Build evidence, not just confidence** (product): the SBOM and audit results give each release checkable evidence of what it contains. Evidence: ADR-0010.

## C.4 Commits

Add one commit to the sequence: `ci: add supply-chain security baseline` (Dependabot config, pinned actions, permissions, pip-audit), and include `SECURITY.md` and ADR-0010 in the existing docs commits.
