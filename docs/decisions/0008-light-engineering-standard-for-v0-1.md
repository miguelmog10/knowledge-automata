# 0008. Light engineering standard for v0.1

- **Status:** Accepted
- **Date:** 2026-10-24

## Context

The full AI-Assisted Software Engineering framework is designed for production work. v0.1 is a portfolio prototype built in a short time.

## Decision

Apply the principles at a level that fits a prototype:

- The non-negotiables in `AGENTS.md`.
- Short ADRs.
- Schema validation.
- Prompts as files.
- A small evaluation set.
- Minimal CI.
- An explicit *Later* list in `dev/backlog.md`.

## Consequences

- The repo demonstrates good practice without production overhead.
- Relaxed items (threat model, benchmarks, coverage target) are deliberate and tracked, not gaps.
