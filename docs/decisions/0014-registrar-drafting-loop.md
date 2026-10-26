# 0014. Registrar drafting loop

- **Status:** Accepted
- **Date:** 2026-10-26

## Context

ADR-0005 and ADR-0011 require every draft to be validated before it becomes a record, and AGENTS.md says invalid output is retried or rejected, never written. The first Registrar (specialist record keeper) needs a concrete loop: what goes to the model, when to retry, and what is recorded about the attempt. The handoff 003 smoke check measured Command A+ with thinking enabled at about 6x the billed output tokens of thinking disabled, with the same validation result, on one artifact.

## Decision

- A Registrar is a register spec plus a versioned prompt file in `prompts/`. One drafting loop serves every Registrar.
- The system message holds only instructions. The user message holds only the artifact, between `<artifact>` tags. An artifact containing the closing tag is refused until the Sensor (intake and input guardrail) checks input.
- Each draft is checked with `validate_draft`: schema, semantic checks and evidence quotes. An invalid draft or an unusable response gets one retry, with the errors added to the system message from a versioned retry prompt. If the retry fails, the record is rejected and nothing is written. Configuration, authentication, request, rate-limit and availability errors are not retried by the loop.
- The record history stores the prompt version of the attempt that produced the stored draft, including the retry prompt when one was used (for example `decision-registrar.v1+registrar-retry.v1`).
- Prompt files are immutable once a record cites them; a change is a new version file.
- The Decision Registrar runs with Command A+ thinking disabled by default; `KA_CHAT_THINKING` overrides it. This is revisited with the sample project's evaluation set.

## Consequences

- At most two calls per record, visible in the event log.
- The retry feedback includes quotes from the model's previous output; they go back to the same model for the same artifact.
- A single retry will not fix a systematic prompt problem; rejection rates in evaluation runs will show it.
- Thinking disabled may miss harder decisions; the evaluation set decides.
