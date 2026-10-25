# AGENTS.md

Shared rules for every AI assistant and human contributor working on this repository. Read this before making any change.

## Project in one paragraph

Knowledge Automata is a general-purpose institutional memory for any group that makes decisions together: a project team, a company department, a research group, a neighbourhood association. A multi-agent LLM system turns messy artifacts (meeting notes, chats, documents) into validated, structured records and keeps them current, with full traceability back to the original artifacts, so humans and AI tools can query what the group knows and why. The core is domain-neutral; project management is the first domain, implemented with PMI-aligned registers such as a decision log and a risk register. It is a public, open-source portfolio project (Apache 2.0), built on Cohere's platform (Command, Embed, Rerank) behind a provider-agnostic service layer, and a deliberate application of the [AI-Assisted Software Engineering](https://github.com/miguelmog10/ai-assisted-software-engineering/blob/0d523881152cd622924aa800caf5264bb5e9ed81/PRINCIPLES.md) framework.

## Team and roles

- **Miguel (owner):** approves plans, merges and decisions.
- **Claude (claude.ai: discovery, architecture, review):** discovery, architecture, schemas, review and second opinion.
- **Copilot (VS Code: implementation):** planning and implementation.

Humans own requirements, architecture, quality and outcomes. AI generates and proposes. Miguel approves plans and merges.

## Where things live (sources of truth)

- `AGENTS.md`: how we work.
- `docs/architecture.md`: how the system works.
- `docs/decisions/`: why it is built this way (ADRs).
- `dev/STATUS.md`: where we are now. **Read this first at the start of every session; update it at the end.**
- `dev/backlog.md`: what's next, what's later, open questions, technical debt.
- `dev/principles-in-practice.md` and `dev/tool-feedback.md`: running logs (see below).
- `dev/costs.md`: Copilot credits used per pull request.
- `dev/handoffs/`: prompts handed between team members, committed for traceability.

Nothing important should exist only in a chat session.

## Principles

The full text is in [PRINCIPLES.md](https://github.com/miguelmog10/ai-assisted-software-engineering/blob/0d523881152cd622924aa800caf5264bb5e9ed81/PRINCIPLES.md). This repo refers to them by number:

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

## Non-negotiables (light version for v0.1)

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

## Deliberately relaxed for v0.1

No formal threat model, no benchmarks, no full coverage target. These are listed in `dev/backlog.md` under *Later*, so they are deliberate deferrals, not gaps.

## Definition of done (per change)

Tests pass, ruff passes, docs updated in the same change, README.md updated if the change is visible to users (status, setup, features), `dev/STATUS.md` updated at the end of the session, new decisions captured as ADRs.

## Commit conventions

- Conventional Commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`, `ci:`.
- Messages explain *why*, not only *what*.
- Reference ADRs or backlog items when relevant, for example `implements ADR-0006`.
- AI-assisted commits end with a `Co-authored-by:` trailer naming the AI assistant and model, so the human and AI collaboration is visible in the history.
- Milestones are tagged (for example `v0.1.0` for the first working slice).

## Branches and pull requests

- Never commit directly to `main`. Use one short-lived branch per piece of work, named with a Conventional Commits type, for example `chore/scaffolding`, `feat/sensor`, `docs/adr-0010`.
- The AI assistant prepares the branch; Miguel opens the pull request, reviews it and merges it. "AI generates, humans own" is built into the workflow.
- Pull requests are squash-merged, so the PR title becomes the commit on `main` and must follow Conventional Commits. Put the `Co-authored-by:` trailer in the squash commit body.
- Fill in `.github/pull_request_template.md`.

## Running logs (everyone contributes)

- `dev/principles-in-practice.md`: when a principle visibly shaped a decision, improved the product, helped the team collaborate, or had to bend, add a short entry.
- `dev/tool-feedback.md`: when a tool, SDK or doc (Cohere, Copilot, Python libraries, anything) is confusing, missing something or surprisingly good, add a short entry. These may later become upstream issues or pull requests.

## Writing style for repo documents

- Plain, concise English.
- Do not use em dashes; use commas, colons or parentheses instead.
- Pair every themed role name with its plain role the first time it appears in a document, for example "Governor (orchestrator)".
- Use "institutional memory" or "collective memory" for the general idea, and "project" only when talking about the project-management domain.
- Name the team as Miguel, Claude and Copilot. Mention the underlying model only in commit trailers and in `dev/costs.md`.

## Clean-room rule

Never open, read or copy files from the Chronicle repository (ADR-0002).
