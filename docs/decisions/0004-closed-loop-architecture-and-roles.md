# 0004. Closed-loop architecture and role names

- **Status:** Accepted (amended 2026-10-30: the Comparator reconciles checked drafts, ADR-0017)
- **Date:** 2026-10-24

## Context

The system senses inputs, decides what to do, compares against current state, acts and monitors the result, with a human overseeing it. The roles need names that describe this loop and stay general purpose.

## Decision

Adopt the roles described in [docs/architecture.md](../architecture.md), themed as a closed-loop control system:

- Sensor (intake and input guardrail)
- Governor (orchestrator and router)
- Comparator (reconciliation)
- Registrars (specialist record keepers)
- Observer (quality control)
- Oracle (query interface)
- Operator (human in the loop)

## Consequences

- Names are systems-oriented and general purpose, not tied to one domain.
- Every themed name is paired with its plain role in docs and docstrings, so readers do not need to learn the theme first.
- The Comparator reconciles each checked draft with existing records before anything is written, which prevents duplicates by design ([ADR-0017](0017-comparator-reconciliation.md)).
