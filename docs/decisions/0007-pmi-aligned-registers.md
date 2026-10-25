# 0007. PMI-aligned registers

- **Status:** Accepted
- **Date:** 2026-10-24

## Context

Project managers recognize the registers and logs described in PMI's PMBOK Guide. PMI describes what these artifacts contain but does not publish formal schemas.

## Decision

- Record schemas are defined by this project and explicitly mapped to artifact descriptions in the PMBOK Guide: risk register, issue log, assumption log, change log, lessons learned register and stakeholder register. A decision log is included as a common project-management practice; whether the cited PMBOK edition names it as an artifact is part of the edition open question in `dev/backlog.md`.
- v0.1 implements the decision log and the risk register.
- These registers are the first domain under ADR-0009.

## Consequences

- Credible, recognizable structure for project managers.
- Agile-compatible, because maintenance is automated rather than manual.
- Each schema documents its own mapping to the PMBOK description.
- Open question: which PMBOK edition to cite.
