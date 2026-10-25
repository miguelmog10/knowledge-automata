# 0009. General-purpose core, project management as first domain

- **Status:** Accepted
- **Date:** 2026-10-24

## Context

The same knowledge-loss problem exists in any group that makes decisions together, not only in projects: knowledge is created constantly and lost just as fast, so groups rediscover context and re-argue settled decisions.

## Decision

- Keep the core roles, the Artifact Ledger and the write rules domain-neutral.
- Package Registrars (specialist record keepers) and their schemas per domain.
- Ship project management (PMI, ADR-0007) as the first domain.

## Consequences

- Broader vision and reuse: other groups, such as associations or research groups, can be served by adding a domain.
- Domain-specific vocabulary stays out of core modules.
- Slightly more care is needed when naming core concepts.
