# Architecture

*Draft, v0.1*

## Overview

Knowledge Automata is designed as a closed-loop control system for the knowledge of any decision-making group: it senses inputs, decides what to do, compares against current state, acts, and monitors the result, with a human operator overseeing it.

## Roles

| Name | Plain role | Responsibility | v0.1 |
|---|---|---|---|
| Sensor | Intake and input guardrail | Validates, hashes, normalizes and logs incoming artifacts in the Artifact Ledger; quarantines invalid or suspicious input | Yes (deterministic checks only) |
| Governor | Orchestrator and router | Analyzes an accepted artifact and issues work orders to the relevant Registrars; marks artifacts processed or failed | Yes |
| Comparator | Reconciliation | Before anything is written, retrieves related existing records (Embed + Rerank) and classifies the input as new, update, reaffirmation or supersession | Yes |
| Registrars | Specialist record keepers | One per register; drafts structured records that code validates, assigns IDs to and stores | Decision and Risk |
| Observer | Quality control | Periodic health and cross-register consistency checks | Later |
| Oracle | Query interface | Answers questions over the registers with citations to records and source artifacts | Stretch |
| Operator | Human in the loop | Approves sensitive changes, reviews quarantine, overrides the system. A role, not an agent | Later (workflow) |

## Data flow for one artifact

1. **Sensor (intake):** the artifact arrives. The Sensor checks it, hashes it and records it in the Artifact Ledger as accepted, quarantined or rejected. If accepted, it normalizes the text and adds metadata.
2. **Governor (orchestrator):** reads the artifact, identifies its content (for example two decisions and one risk) and sends work orders to the Decision and Risk Registrars.
3. **Comparator (reconciliation):** for each work order, retrieves related existing records and tells the Registrar whether this is new, an update, a reaffirmation or a supersession.
4. **Registrars (specialist record keepers):** draft records as structured data. Code validates them against the schema, assigns IDs and stores them. Independent Registrars can run in parallel.
5. **Governor:** marks the artifact as processed in the Ledger, listing the records it produced.

Around this loop: the Observer (quality control) checks register health, the Oracle (query interface) answers questions from stored records, and the Operator (human in the loop) approves sensitive changes.

## Write rules

Raw artifacts are read-only. Each register defines its own write rule (append-only, update in place, or supersede with a link). Every record links back to its source artifacts, and every Ledger entry links forward to the records it produced.

## Domains and applications

The core (Sensor, Governor, Comparator, Observer, Oracle, Operator and the Artifact Ledger) is domain-neutral. A domain is a set of Registrars and their schemas. v0.1 ships the project-management domain, with registers aligned to PMI's PMBOK Guide (ADR-0007, ADR-0009). Possible future domains include an association (charter, motions, member decisions) or a research group (hypotheses, experiments, findings).

## Patterns and terminology

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

## Security: defence in depth

The Sensor is the first line of defence, not the only one. Artifact text is always treated as data, schema validation blocks malformed writes, and the Operator approves sensitive changes. Together these protect the institutional memory from contamination (memory poisoning). Prompt-injection and relevance checks in the Sensor are planned (see `dev/backlog.md`). These guardrails are also relevant evidence for future cybersecurity compliance work such as the EU Cyber Resilience Act.

Supply-chain security (dependency auditing, pinned CI actions and an SBOM per release) complements this runtime defence in depth (ADR-0010).

## Observability

Every LLM call is logged by the service layer as one structured JSON event: agent, model, operation, input and output tokens, latency and artifact ID. A small, dated price table in configuration converts tokens to cost. Because the Ledger links artifacts to records, cost per artifact and per record can be derived. The event format should stay compatible with a later move to a standard such as OpenTelemetry.

## Vision: an architecture, not just an implementation

Each role is defined by a contract: its inputs, its outputs, the schemas it must follow and what it may write. This Python package is the **reference implementation**. Anything that honours a role's contract could fill that role, for example a GitHub Copilot agent, an Atlassian Rovo agent or a CI pipeline step, connected to systems such as Jira, Confluence or Microsoft Teams.
