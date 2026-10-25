# 0010. Supply-chain security baseline

- **Status:** Accepted
- **Date:** 2026-10-24

## Context

The EU Cyber Resilience Act (CRA) expects a software bill of materials (SBOM), no known exploitable vulnerabilities, timely security updates and coordinated vulnerability disclosure. The CRA targets commercial products on the EU market and largely exempts non-commercial open source, so this decision is about readiness and good practice, not a compliance claim.

## Decision

- Dependabot alerts, security updates and weekly version updates.
- `pip-audit` in CI, failing the build on known vulnerabilities.
- Every CI action pinned to a full commit SHA, with least-privilege workflow permissions.
- `SECURITY.md` plus GitHub private vulnerability reporting.
- A lock file from the first runtime dependency.
- A CycloneDX SBOM generated in CI and attached to every tagged release, starting with v0.1.0.

## Consequences

- Vulnerable dependencies are caught before merge.
- Every release documents its components.
- Reporters have a private channel.
- Small ongoing cost of reviewing Dependabot pull requests.
