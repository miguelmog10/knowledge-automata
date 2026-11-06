# 0014. Registrar drafting loop

- **Status:** Accepted (amended 2026-10-31: thinking enabled by default, handoff 006 Addendum A; note added 2026-11-02: the cause of the thinking-disabled failure; amended 2026-11-06: every JSON-mode prompt ends with the JSON instruction, handoff 008)
- **Date:** 2026-10-26

## Context

ADR-0005 and ADR-0011 require every draft to be validated before it becomes a record, and AGENTS.md says invalid output is retried or rejected, never written. The first Registrar (specialist record keeper) needs a concrete loop: what goes to the model, when to retry, and what is recorded about the attempt. The handoff 003 smoke check measured Command A+ with thinking enabled at about 6x the billed output tokens of thinking disabled, with the same validation result, on one artifact.

## Decision

- A Registrar is a register spec plus a versioned prompt file in `prompts/`. One drafting loop serves every Registrar.
- The system message holds only instructions. The user message holds only the artifact, between `<artifact>` tags. An artifact containing the closing tag is refused until the Sensor (intake and input guardrail) checks input.
- Each draft is checked with `validate_draft`: schema, semantic checks and evidence quotes. An invalid draft or an unusable response gets one retry, with the errors added to the system message from a versioned retry prompt. If the retry fails, the record is rejected and nothing is written. Configuration, authentication, request, rate-limit and availability errors are not retried by the loop.
- The record history stores the prompt version of the attempt that produced the stored draft, including the retry prompt when one was used (for example `decision-registrar.v1+registrar-retry.v1`).
- Prompt files are immutable once a record cites them; a change is a new version file.
- The Registrars and the Comparator run Command A+ with thinking enabled by default; `KA_CHAT_THINKING` overrides it. Thinking was disabled until 2026-10-31, to save output tokens; in the handoff 006 real run, most first attempts with thinking disabled came back with the reasoning in prose before the JSON and were rejected, after about as many output tokens as thinking uses (handoff 006, Addendum A). Note (2026-11-02): a reproduction found the cause on our side. Cohere's structured outputs docs ask that a JSON-mode request also tell the model, in the prompt, to produce JSON, and none of our prompts did. With one line added to the system prompt, thinking disabled returned clean JSON three times out of three, at 272 output tokens against 1,165 to 2,214 with thinking enabled (one prompt, one schema, one artifact). Thinking stays enabled until new prompt versions carry that line and thinking disabled is measured on the evaluation set (backlog). Amendment (2026-11-06): since handoff 008, every JSON-mode prompt ends with "Reply with one JSON object that matches the response schema, and nothing else." (`governor.v2`, `decision-registrar.v3`, `decision-comparator.v2` and their retry prompts), and a conformance test keeps the line in every prompt the pipeline uses, new Registrars included. Thinking stays enabled: in the handoff 008 diagnostic, thinking disabled still failed with the line for the Registrar on artifacts with several items and for the Comparator, while thinking enabled passed every check (handoff 008, section 9).
- The adapter parses the reply strictly: the text block must be one JSON object from its first character. Extracting a JSON object from surrounding prose was considered and rejected (2026-10-31): it is unreliable when the reasoning quotes the artifact, which can contain braces or JSON-like fragments; it still pays for the prose on every call; and it would let text echoed from an untrusted artifact reach the parser. Fixing the cause is better than hiding the symptom: thinking enabled avoided it, and the JSON instruction (see above) addresses it directly.

## Consequences

- At most two calls per record, visible in the event log.
- The retry feedback includes quotes from the model's previous output; they go back to the same model for the same artifact.
- A single retry will not fix a systematic prompt problem; rejection rates in evaluation runs will show it.
- Thinking costs about 1,000 reasoning tokens per call; a token budget is measured on the evaluation set.
- Thinking disabled can come back with the setting alone, without a code change, once the evaluation set shows clean JSON and records as good as with thinking enabled. Asking for JSON is necessary but, as handoff 008 showed, not sufficient: the tasks that need judgement will need more prompt work first. In the 2026-11-02 reproduction, an accepted call cost a quarter to an eighth of the output tokens.
