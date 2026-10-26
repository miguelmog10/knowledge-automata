# 0012. LLM service layer: structured chat, observation and cost

- **Status:** Accepted
- **Date:** 2026-10-25

## Context

ADR-0003 requires one internal interface each for chat, embeddings and reranking, with Cohere as the first provider. Before agents are built, the details need to be fixed: what the interfaces return, how calls are observed and costed, how errors are handled, and how tests stay offline. The design principle in `docs/architecture.md` applies: the model proposes, code checks.

## Decision

- The interfaces live in `knowledge_automata.llm` and use provider-neutral names. In v0.1 chat is structured only (`chat_json`): instructions and user content go in separate messages, and the result is a parsed JSON object. Validating it against a record schema, and retrying, stays with the caller.
- The Cohere adapter uses the official Python SDK and is the only module that imports it. It reduces schemas to the keywords Cohere documents and raises an error on any other keyword. Model IDs are configuration.
- Retries for rate limits and server errors use the SDK's built-in mechanism, bounded by configuration. Provider errors map to a small set of project exceptions whose messages never contain keys, prompts or artifact text.
- An observation wrapper records one event per call as JSON Lines, validated against `schemas/core/llm-event.v1.json`. Events hold metadata only (timing, model, the billed and raw units the provider reports, estimated cost, agent, artifact ID, a run ID grouping the calls of one run, and the event schema version), never prompts, artifact text or output.
- The event log is append-only and survives across runs: lines are only ever added, never rewritten. If the file is deleted, the next call starts a new one.
- Cost is estimated from billed units and a dated price table copied from the provider's official pricing page. A missing price is left out, never guessed; the units are always recorded, so cost can be computed later.
- Settings come from environment variables (`CO_API_KEY`, `KA_*`); locally `.env` is loaded with `uv run --env-file .env`.
- Tests never touch the network: a fake adapter and a stub SDK client cover the code, and a test fixture blocks sockets. Real calls happen only in a manual smoke check.

## Consequences

- Swapping a model or provider stays a contained change, and the fake makes every agent testable offline.
- Cost per artifact and per record can be derived from the event log, because every event carries the artifact ID.
- The event log is safe to keep and share, and cannot become an unvalidated second copy of the institutional memory.
- Metadata-only events make it harder to debug a bad output; opt-in debug capture to a git-ignored folder is in the backlog.
- The SDK adds dependencies to the supply chain; they are pinned in `uv.lock` and audited by pip-audit.
- Trial keys are rate limited and capped per month, so real calls (smoke checks, evaluation runs) must be budgeted.
