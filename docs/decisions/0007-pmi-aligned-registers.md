# 0007. PMI-aligned registers

- **Status:** Accepted (amended 2026-10-25: PMBOK edition resolved)
- **Date:** 2026-10-24

## Context

Project managers recognize the registers and logs described in PMI's PMBOK Guide. PMI describes what these artifacts contain but does not publish formal schemas.

## Decision

- Record schemas are defined by this project and explicitly mapped to artifact descriptions in the PMBOK Guide, Eighth Edition (PMI, 2025): risk register, issue log, assumption log, change log, lessons learned register and stakeholder register.
- The decision log is included as a widely used project-management practice. It is not named as an artifact in the Eighth Edition (checked against summaries of its inputs and outputs on 2026-10-25), and its schema says so in its mapping note.
- v0.1 implements the decision log and the risk register.
- These registers are the first domain under ADR-0009.

## Consequences

- Credible, recognizable structure for project managers.
- Agile-compatible, because maintenance is automated rather than manual.
- Each schema documents its own mapping in `x-pmi-mapping`.
- When PMI publishes a new edition, the mappings are reviewed.
