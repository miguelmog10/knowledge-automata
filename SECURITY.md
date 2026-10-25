# Security policy

## Supported versions

Knowledge Automata is pre-1.0. Only the latest commit on `main` is supported; fixes are not backported.

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub private vulnerability reporting: open the repository's **Security** tab and choose **Report a vulnerability**.

Do not open a public issue, discussion or pull request for a security problem.

## What to expect

This project has a single maintainer, so responses are best effort. The target is to acknowledge a report within 7 days, then agree next steps and a disclosure timeline with the reporter.

## Scope

In scope:

- Vulnerabilities in the code and CI configuration in this repository.
- Prompt injection: artifact content that causes an agent to follow instructions instead of treating the text as data.
- Contamination of the institutional memory (memory poisoning): anything that lets invalid, malicious or unreviewed content be written into the records or the Artifact Ledger.
- Vulnerable dependencies that affect this project.
