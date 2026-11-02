# 0006. Artifact Ledger

- **Status:** Accepted (amended 2026-10-27: storage, transitions and the Operator release in ADR-0015; amended 2026-11-01: the `held` status and the Governor's transitions, ADR-0018)
- **Date:** 2026-10-24

## Context

Every record must trace back to its sources, re-runs must not duplicate work, and suspicious input must be visible to a human rather than silently dropped.

## Decision

Maintain a ledger of every artifact the system receives, holding:

- Identity: ID, title, source URI, source type, artifact date.
- Content hash.
- Status with a reason: `received`, then `accepted`, `quarantined` or `rejected`, then `processed`, `failed` or `held`. `held` means the Governor found more work orders than the configured limit and drafted nothing; the Operator releases it back to `accepted` (amended 2026-11-01, [ADR-0018](0018-governor-work-orders.md)). Storage, the allowed transitions and the Operator release are set out in [ADR-0015](0015-artifact-ledger-storage-and-sensor-checks.md).
- Timestamps.
- The records produced.
- The model, prompt and schema versions used.

Each status transition has a single owner. The Sensor (intake and input guardrail) sets accepted, quarantined or rejected. The Governor (orchestrator and router) sets processed, failed or held. The Operator (human in the loop) releases quarantined and held artifacts. Quarantined input is kept, never silently discarded.

## Consequences

- Two-way traceability between artifacts and records.
- Idempotent re-runs.
- Targeted reprocessing when prompts or schemas change.
- The Operator (human in the loop) can see what was accepted, quarantined or rejected, and why.
