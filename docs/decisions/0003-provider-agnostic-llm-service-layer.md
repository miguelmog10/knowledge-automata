# 0003. Provider-agnostic LLM service layer

- **Status:** Accepted
- **Date:** 2026-10-24

## Context

The system needs chat, embeddings and reranking. Cohere (Command, Embed, Rerank) is the first provider, but models and providers change, and tests must run without network calls.

## Decision

Define one internal interface each for chat, embeddings and reranking. Cohere is the first implementation. No provider SDK is imported outside its adapter.

## Consequences

- Swapping models or providers is a contained change.
- Tests use a fake implementation of the same interfaces.
- Observability (one structured event per LLM call) is captured in one place.
