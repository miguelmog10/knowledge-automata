# Handoff 003: LLM service layer and Cohere adapter

- **From:** Claude (discovery, architecture, review)
- **To:** Copilot (implementation)
- **Owner and approver:** Miguel
- **Date:** 2026-10-25
- **Branch:** `feat/llm-service-layer`
- **Scope:** the provider-agnostic LLM service layer (ADR-0003): interfaces for chat, embeddings and reranking, the Cohere adapter, a fake adapter for tests, an event log for every call, a dated price table, configuration, and a manual smoke check against the real API. No agents, no prompts as files, no storage.

---

## 1. Context

Handoff 002 (PR #3) delivered the record schemas and validators. Every agent from now on calls a model, so the service layer comes next: it is the only place that talks to a provider, the only place calls are observed and costed, and the reason tests never touch the network.

Two decisions frame this handoff:

- **Design principle** (now in `docs/architecture.md`): use the LLM only where judgement is needed; use deterministic code for everything that can be checked. The service layer returns model output as a proposal; validating it against the record schemas stays with the caller.
- **Reorder:** handoff 004 is a thin vertical slice (one sample artifact through the Decision Registrar to one validated record on a real Command call), ahead of the Sensor. This handoff must therefore leave a service layer the Registrar can use directly.

Read `AGENTS.md`, `dev/STATUS.md`, ADR-0003, ADR-0005, ADR-0011 and `docs/architecture.md` before planning.

**Already committed by Miguel on this branch:** this handoff, `schemas/core/llm-event.v1.json` (section 5), and the planning updates (STATUS, costs, AGENTS, README, architecture design principle, backlog, principles log, tool feedback). Do not modify this handoff. If you find a problem in the event schema, raise it in your plan instead of changing it silently.

## 2. How to work on this task

1. **Plan first.** Read this whole document, then reply with a short plan: files to create or change, anything in the Cohere SDK that differs from section 6, and the commit sequence. **Wait for Miguel's approval** before writing files.
2. **Check the Cohere SDK and docs** before planning: the current `cohere` package version and its dependencies (do they install on Python 3.11 and 3.15?), `ClientV2` method signatures for `chat`, `embed` and `rerank`, response fields for usage and billed units, built-in retry and timeout options, the embed batch limit, and the error classes. Section 6 marks every assumption to check with *verify*.
3. Implement in small commits (section 9), with tests in the same commit as the code they cover.
4. **No test may call the network.** Real calls happen only in the manual smoke check (6.9), which needs Miguel's API key in `.env`.
5. If anything here is ambiguous or seems wrong, ask instead of guessing, and add it to `dev/backlog.md` under *Open questions*.
6. Finish by updating `dev/STATUS.md` and reporting what you did, ending with the **Cohere notes** section required by `AGENTS.md`.

## 3. Agreed design

### 3.1 Three interfaces, structured chat only

`knowledge_automata.llm` defines one interface each for chat, embeddings and reranking (ADR-0003), with provider-neutral names. In v0.1 chat is structured only: `chat_json` takes instructions and the user content as **separate messages**, and returns a parsed JSON object. Plain-text chat is added when an agent needs it (P16).

Validating the JSON against a record schema, and retrying when it fails, stays with the caller (the Registrar, handoff 004). The service layer guarantees only that it returns a JSON object or raises a clear error.

### 3.2 One adapter per provider, Cohere first

- `llm/cohere_adapter.py` is the **only** module that imports `cohere`. It uses the official Python SDK (`cohere.ClientV2`), so the project uses Cohere's platform the way Cohere documents it.
- Before sending a schema, the adapter reduces it to the keywords Cohere documents (the allowlist from handoff 002, section 6.7). Unknown keywords raise an error instead of being sent or silently dropped.
- Model IDs are configuration, not code.

### 3.3 Every call is observed, with metadata only

An observation wrapper (`ObservedLLM`) wraps any adapter, fake included, and writes one event per call as JSON Lines. Events contain metadata only (timing, model, billed units, estimated cost, the agent and artifact ID), **never** prompts, artifact text, model output or keys. Logs are then safe to keep and share, and the log cannot become a second, unvalidated copy of the institutional memory. Each event is validated against `schemas/core/llm-event.v1.json` before it is written.

### 3.4 Cost from billed units and a dated price table

- Cost uses the **billed** units the provider reports (Cohere reports billed units separately from raw tokens; *verify* the fields).
- Prices live in a small TOML file inside the package, with the date they were checked and the source URL. Values are copied from Cohere's official pricing page, never estimated or taken from third-party sites. If a model has no published price, it is left out of the table and `cost_usd` is omitted from its events.
- Rerank may be priced per search unit (one query with up to 100 documents) or per token depending on the model; the table supports both.

### 3.5 Errors and retries

- Provider errors map to a small set of project exceptions with clear messages (6.3). Messages never contain the API key, prompts or artifact text.
- Retries: use the SDK's built-in retries for rate limits and server errors, bounded by configuration (*verify* how the SDK exposes `max_retries` and timeouts). Do not add a second retry loop on top.
- A monthly-cap 429 on a trial key is reported as such, because retrying cannot help.

### 3.6 Configuration through environment variables

Settings come from the environment, with defaults where safe. Locally, `.env` is loaded by uv: `uv run --env-file .env ...`. No new dependency for loading `.env`.

### 3.7 Tests stay offline

The fake adapter (deterministic, scripted) and a stub SDK client cover everything. An autouse test fixture blocks network sockets, so an accidental real call fails loudly instead of spending trial calls.

### 3.8 One manual smoke check against the real API

A script outside the package makes a handful of real calls (about six) with Miguel's key. It settles the open questions from handoff 002 (the `response_format` field name, `additionalProperties: false`, annotation keywords), and checks that Cohere accepts our real decision draft schema. It never runs in CI.

## 4. Target structure

New and changed files (existing files not shown):

```
schemas/core/llm-event.v1.json             # already committed by Miguel (section 5)
src/knowledge_automata/llm/
├── __init__.py                             # public names: interfaces, results, errors, build_llm
├── interfaces.py                           # CallContext, Usage, result types, the three Protocols
├── errors.py                               # LLMError and subclasses
├── settings.py                             # LLMSettings.from_env
├── provider_schema.py                      # Cohere keyword allowlist and strip function
├── cohere_adapter.py                       # the only module that imports cohere
├── fake.py                                 # FakeLLM for tests
├── observed.py                             # ObservedLLM wrapper and event sinks
├── pricing.py                              # price table loading and cost estimate
├── prices.toml                             # dated Cohere prices (packaged)
└── factory.py                              # build_llm(settings): adapter + wrapper + sink + prices
scripts/cohere_smoke.py                     # manual smoke check, never in CI
tests/llm/                                  # tests for the above (section 7)
docs/decisions/0012-llm-service-layer-observation-and-cost.md
```

Also change: `pyproject.toml` and `uv.lock` (the `cohere` dependency), `.env.example`, `.gitignore` (`logs/`), the CI `package` job (also load the price table from the wheel), `docs/architecture.md`, the ADR index, `dev/STATUS.md`, `dev/backlog.md`, `dev/tool-feedback.md`, and the README if setup changes.

`provider_schema.py` is a suggestion: if you prefer the strip function inside `cohere_adapter.py`, say so in the plan. Either way it must not import `cohere`, so it stays testable without the SDK.

## 5. Event schema

Committed by Miguel. Reproduced here so the handoff is a complete record of the design.

### 5.1 `schemas/core/llm-event.v1.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:knowledge-automata:schema:core:llm-event:v1",
  "x-version": "1.0",
  "title": "LLM call event",
  "description": "One line of the LLM event log: metadata about one call through the service layer. It never contains prompts, artifact text, model output or keys. Never sent to an LLM provider.",
  "type": "object",
  "properties": {
    "ts": {
      "type": "string",
      "format": "date-time",
      "description": "When the call finished (UTC)."
    },
    "event_id": {
      "type": "string",
      "format": "uuid"
    },
    "provider": {
      "type": "string",
      "pattern": "^[a-z][a-z0-9-]*$",
      "description": "For example cohere, or fake in tests."
    },
    "model": { "type": "string", "minLength": 1 },
    "operation": { "enum": ["chat", "embed", "rerank"] },
    "agent": {
      "type": "string",
      "pattern": "^[a-z][a-z0-9-]*$",
      "description": "The role that made the call, for example decision-registrar or smoke-check."
    },
    "artifact_id": {
      "type": "string",
      "pattern": "^ART-[0-9]{4,}$"
    },
    "prompt_version": { "type": "string", "minLength": 1 },
    "status": { "enum": ["ok", "error"] },
    "error_type": {
      "type": "string",
      "description": "Project exception class name, for example LLMRateLimitError. Present only when status is error."
    },
    "latency_ms": { "type": "integer", "minimum": 0 },
    "items": {
      "type": "integer",
      "minimum": 0,
      "description": "Texts embedded or documents reranked. 1 for chat."
    },
    "input_tokens": {
      "type": "integer",
      "minimum": 0,
      "description": "Billed input tokens, when the provider reports them."
    },
    "output_tokens": {
      "type": "integer",
      "minimum": 0,
      "description": "Billed output tokens, when the provider reports them."
    },
    "search_units": {
      "type": "integer",
      "minimum": 0,
      "description": "Billed rerank search units, when the provider reports them."
    },
    "cost_usd": {
      "type": "string",
      "pattern": "^[0-9]+(\\.[0-9]+)?$",
      "description": "Estimated cost as a decimal string. Omitted when the price table has no price for this model."
    },
    "price_table": {
      "type": "string",
      "format": "date",
      "description": "The checked_on date of the price table used for cost_usd."
    }
  },
  "required": ["ts", "event_id", "provider", "model", "operation", "agent", "status", "latency_ms", "items"],
  "additionalProperties": false,
  "allOf": [
    {
      "if": { "properties": { "status": { "const": "error" } }, "required": ["status"] },
      "then": { "required": ["error_type"] },
      "else": { "not": { "required": ["error_type"] } }
    },
    {
      "if": { "required": ["cost_usd"] },
      "then": { "required": ["price_table"] }
    }
  ]
}
```

## 6. Code requirements

### 6.1 Dependency

- Add `cohere` (current major version) as a runtime dependency and update `uv.lock`.
- Report in the plan which dependencies it brings (for example `httpx`, `pydantic`, `tokenizers`) and whether they publish wheels for Python 3.15. If one does not, follow the note in `dev/STATUS.md`.

### 6.2 Interfaces (`interfaces.py`)

Use these shapes; names may change if you explain why in the plan.

```python
@dataclass(frozen=True)
class CallContext:
    agent: str                       # role making the call, for example "decision-registrar"
    artifact_id: str | None = None   # ART-0001, when the call concerns one artifact
    prompt_version: str | None = None

@dataclass(frozen=True)
class Usage:                         # billed units; None when the provider does not report them
    input_tokens: int | None = None
    output_tokens: int | None = None
    search_units: int | None = None

@dataclass(frozen=True)
class ChatResult:
    data: dict[str, Any]             # parsed JSON object
    model: str
    usage: Usage
    finish_reason: str | None = None

@dataclass(frozen=True)
class EmbedResult:
    vectors: list[list[float]]       # one per input text, same order
    model: str
    usage: Usage

@dataclass(frozen=True)
class RankedDocument:
    index: int                       # position in the input documents
    score: float

@dataclass(frozen=True)
class RerankResult:
    results: list[RankedDocument]    # best first, at most top_n
    model: str
    usage: Usage

@runtime_checkable
class ChatModel(Protocol):
    def chat_json(self, *, system: str, user: str, schema: Mapping[str, Any],
                  context: CallContext) -> ChatResult: ...

@runtime_checkable
class EmbeddingModel(Protocol):
    def embed(self, texts: Sequence[str], *, input_type: Literal["document", "query"],
              context: CallContext) -> EmbedResult: ...

@runtime_checkable
class RerankModel(Protocol):
    def rerank(self, query: str, documents: Sequence[str], *, top_n: int,
               context: CallContext) -> RerankResult: ...
```

`CallContext.agent` uses the same lowercase-hyphen form as the event schema. Validate it when the context is created.

### 6.3 Errors (`errors.py`)

`LLMError` (base) and:

| Exception | When |
|---|---|
| `LLMConfigError` | Missing or invalid settings, for example no `CO_API_KEY` |
| `LLMAuthError` | 401 or 403 |
| `LLMRateLimitError` | 429 after the SDK's retries; a flag or message says whether it is the trial monthly cap |
| `LLMRequestError` | Other 4xx: our request is wrong (for example a schema Cohere rejects). Include the provider's error message, which is safe because it describes our request. |
| `LLMUnavailableError` | 5xx after retries, timeouts and network errors |
| `LLMResponseError` | The response is not usable: not valid JSON, not a JSON object, truncated (`finish_reason` signals the token limit), or missing fields |

Map provider errors by HTTP status code where possible rather than by SDK class names, so the mapping survives SDK renames (*verify* how the SDK exposes the status code and how it raises timeouts).

### 6.4 Settings (`settings.py`)

`LLMSettings.from_env(env: Mapping[str, str] = os.environ)`, a frozen dataclass:

| Variable | Default | Notes |
|---|---|---|
| `CO_API_KEY` | none | Required only when the Cohere adapter is built. The error message says to copy `.env.example` to `.env` and run with `uv run --env-file .env`. |
| `KA_CHAT_MODEL` | `command-a-plus-05-2026` | *verify* on Cohere's models page, and that it supports structured outputs |
| `KA_EMBED_MODEL` | `embed-v5.0-fast` | *verify* |
| `KA_RERANK_MODEL` | `rerank-v5.0-pro` | Cohere's recommendation for new projects; *verify* |
| `KA_LLM_TEMPERATURE` | `0` | Low temperature for extraction |
| `KA_LLM_TIMEOUT_SECONDS` | `60` | |
| `KA_LLM_MAX_RETRIES` | `2` | Passed to the SDK |
| `KA_EVENT_LOG` | `logs/llm-events.jsonl` | Add `logs/` to `.gitignore` |

Invalid values (for example a non-numeric timeout) raise `LLMConfigError` naming the variable. The API key never appears in `repr`, logs or messages. Update `.env.example` with the `KA_` variables, commented out with their defaults.

### 6.5 Provider schema (`provider_schema.py`)

`to_cohere_schema(schema) -> dict` returns a new schema containing only the keywords Cohere documents:

- **Kept:** `type`, `properties`, `required`, `items`, `enum`, `const`, `description`, `title`, `format` (only `date`, `date-time`, `time`, `uuid`), `additionalProperties`.
- **Removed:** `$schema`, `$id`, `x-version`, `x-pmi-mapping` and any other `x-` key, `maxLength`, `minLength`, `minItems`, `maxItems`.
- **Anything else raises `ValueError`** naming the keyword and its JSON path, so a future schema change cannot silently send something unsupported.
- Keys inside `properties` are **property names, not keywords**: keep them all, even names such as `title` or `format` (the decision and risk schemas have a `title` property), and recurse into each value.
- The input is never mutated.

Whether `title` is truly accepted, and whether `additionalProperties: false` is enforced, is settled by the smoke check (6.9). If either fails, move it to the removed list and log it.

### 6.6 Cohere adapter (`cohere_adapter.py`)

`CohereAdapter(settings, *, client=None, schema_field=RESPONSE_SCHEMA_FIELD)` implements all three interfaces. `client` lets tests inject a stub; when it is `None`, build `cohere.ClientV2` with the API key and timeout from settings.

- **Chat:** send `messages=[{"role": "system", ...}, {"role": "user", ...}]`, the chat model, the temperature, and `response_format={"type": "json_object", <schema_field>: to_cohere_schema(schema)}`. `RESPONSE_SCHEMA_FIELD = "schema"`: Cohere's guide uses `schema` while the API reference names `json_schema`, so the field name is one constant, and the smoke check confirms it. Parse the first text content block as JSON; it must be an object.
- **Embed:** map `document` and `query` to Cohere's `search_document` and `search_query`. Request float embeddings. Split inputs into batches no larger than Cohere's per-call limit (*verify*; 96 texts in earlier versions) and keep the output order.
- **Rerank:** return results best first with the input index and relevance score; `top_n` is capped at the number of documents.
- **Usage:** read billed units: input and output tokens for chat; input tokens for embed; search units for rerank (*verify* the response fields, and whether rerank v5 bills tokens instead).
- **Retries and timeout:** pass `KA_LLM_MAX_RETRIES` and `KA_LLM_TIMEOUT_SECONDS` to the SDK (*verify* the mechanism, for example `request_options`).
- **Errors:** as in 6.3.

### 6.7 Fake adapter (`fake.py`)

`FakeLLM` implements all three interfaces with no network and no randomness:

- `chat_json` returns scripted responses in order (`FakeLLM(chat_responses=[{...}, ...])`). An `Exception` in the list is raised instead. Running out of responses raises a clear `AssertionError`-style message, so tests fail loudly.
- `embed` returns a deterministic vector per text (for example derived from a SHA-256 hash, 8 dimensions, normalized), so equal texts get equal vectors.
- `rerank` scores documents by word overlap with the query (for example Jaccard similarity), best first.
- Usage is deterministic (for example characters divided by four).
- Every call is recorded in `fake.calls` (operation, context and inputs), so tests can assert what was sent.

### 6.8 Observation, events and cost (`observed.py`, `pricing.py`, `prices.toml`)

- `ObservedLLM(inner, *, provider, sink, prices, clock=...)` implements the three interfaces by delegating to `inner`. Per call it measures latency, builds one event (5.1), validates it against `core/llm-event.v1.json` (reusing the schema loading from handoff 002), and writes it to the sink. On error it writes an event with `status: "error"` and `error_type`, then re-raises the original exception.
- Sinks: an `EventSink` protocol with `emit(event: dict)`, a `JsonlFileSink(path)` that appends one line per event and creates the folder, and a `MemorySink` for tests.
- `prices.toml` lives inside the package (so it ships in the wheel) and has this shape:

```toml
# Cohere list prices in USD, copied from the official pricing page.
# Never estimate a price; leave a model out if no price is published.
checked_on = "2026-10-25"
source = "https://cohere.com/pricing"
currency = "USD"

[models."<model id>"]
input_per_million_tokens = "..."
output_per_million_tokens = "..."
# Rerank, whichever unit the pricing page uses for this model:
# per_thousand_search_units = "..."
# per_million_tokens = "..."
```

- Store prices as strings and compute with `Decimal`. `estimate_cost(model, usage, table) -> Decimal | None` returns `None` when the model or a needed unit price is missing. Log a warning once per unknown model.
- `build_llm(settings, *, sink=None)` in `factory.py` wires `CohereAdapter`, `ObservedLLM`, a `JsonlFileSink` at `KA_EVENT_LOG` and the packaged prices. Callers (agents, the smoke script) use only `build_llm` and the interfaces.

**Prices:** copy values only from Cohere's official pricing page and fill in `checked_on`. If the page does not list a price for a configured model, leave it out, say so in your report, and log it in `dev/tool-feedback.md`. Claude could not find per-token prices for the current Command, Embed v5 or Rerank v5 models on that page on 2026-10-25.

### 6.9 Smoke check (`scripts/cohere_smoke.py`)

Run by Miguel (or by you with his approval) once his key is in `.env`:

```
uv run --env-file .env python scripts/cohere_smoke.py
```

It uses `build_llm` with `agent="smoke-check"` and prints a short report. About six calls in total:

1. **Is the schema enforced, and under which field name?** `chat_json` with a schema whose only property is `{"color": {"type": "string", "enum": ["vermilion"]}}` (required) and the user message "What colour is a clear daytime sky?". If the schema is enforced the answer is `vermilion`; if it is ignored the answer is almost certainly `blue`. Run it with `schema_field="schema"`, and only if that is not enforced, again with `"json_schema"`. Report which one works.
2. **Does Cohere accept our real schema?** `chat_json` with `draft_schema(DECISION_LOG)` (handoff 002) and the fixture artifact `tests/fixtures/artifact-steering-group.txt`, with a one-line instruction such as "Extract the main decision from the meeting notes as JSON, with evidence quotes copied word for word." Then run `validate_draft` on the result and print whether it passed and any errors. This is a compatibility check, not the Registrar prompt: the real prompt comes as a file in handoff 004.
3. **Embed** two documents and one query, and print the vector dimensions.
4. **Rerank** one query over three short documents, and print the order and scores.
5. Print the events written during the run and the total estimated cost.

The output may be pasted into the pull request or the report; it contains only fictional data. Record the findings (field name, `title`, `additionalProperties`, whether the decision draft validated) in `dev/tool-feedback.md` and `dev/STATUS.md`, and adjust `RESPONSE_SCHEMA_FIELD` or the keyword lists if needed.

## 7. Tests

All under `tests/llm/`. No network: add an autouse fixture (in `tests/conftest.py`) that makes any socket connection raise.

- **Boundaries:** a test parses every module under `src/` and fails if any module other than `llm/cohere_adapter.py` imports `cohere`. `FakeLLM`, `CohereAdapter` and `ObservedLLM` satisfy the three protocols (`isinstance` with the runtime-checkable protocols).
- **Provider schema:** annotations and validation-only keywords are removed at every depth; property names such as `title` survive; an unknown keyword raises with its path; the input is not mutated; `to_cohere_schema(draft_schema(spec))` works for both registers and leaves only allowlisted keywords.
- **Cohere adapter (stub client):** the chat request has separate system and user messages, the model, the temperature and the `response_format` with the configured field name; valid JSON returns `ChatResult` with billed usage; invalid JSON, a JSON array and a truncated response raise `LLMResponseError`; embed batches (for example 200 texts become three calls when the limit is 96) and keeps order, and maps input types; rerank returns best first with indices; status codes map to the right exceptions (401, 403, 429, 429 monthly cap, 400, 500, timeout); no exception message contains the API key or the prompt text.
- **Settings:** defaults; missing `CO_API_KEY` raises `LLMConfigError` with the setup hint, only when the adapter is built; an invalid number names the variable; `repr` does not show the key.
- **Observation:** one event per call with the right operation, model, agent, artifact ID, items and usage; every event validates against `core/llm-event.v1.json`; the error path writes `status: "error"` and re-raises; a sentinel string placed in the prompt, the artifact text and the fake's response never appears in the serialized event; `cost_usd` is present when the table has the price and absent otherwise.
- **Pricing:** the packaged table loads and `checked_on` is a valid date; the cost arithmetic uses `Decimal` and is checked on known numbers from a test table (not the real one); an unknown model returns `None`.
- **Sinks:** the JSONL sink appends one valid JSON line per event and creates the folder (`tmp_path`).
- **Fake:** scripted responses come back in order, exceptions are raised, running out fails clearly, embeddings are deterministic, rerank ranks the obvious match first.
- **Package job:** extend the CI `package` job so it also loads the price table from the installed wheel.

## 8. Documentation changes

### 8.1 New ADR: `docs/decisions/0012-llm-service-layer-observation-and-cost.md`

Use this text, and add the ADR to the index in `docs/decisions/README.md`. Adjust it only if the smoke check or the SDK changes a stated fact, and say so in your report.

```markdown
# 0012. LLM service layer: structured chat, observation and cost

- **Status:** Accepted
- **Date:** 2026-10-25

## Context

ADR-0003 requires one internal interface each for chat, embeddings and reranking, with Cohere as the first provider. Before agents are built, the details need to be fixed: what the interfaces return, how calls are observed and costed, how errors are handled, and how tests stay offline. The design principle in `docs/architecture.md` applies: the model proposes, code checks.

## Decision

- The interfaces live in `knowledge_automata.llm` and use provider-neutral names. In v0.1 chat is structured only (`chat_json`): instructions and user content go in separate messages, and the result is a parsed JSON object. Validating it against a record schema, and retrying, stays with the caller.
- The Cohere adapter uses the official Python SDK and is the only module that imports it. It reduces schemas to the keywords Cohere documents and raises an error on any other keyword. Model IDs are configuration.
- Retries for rate limits and server errors use the SDK's built-in mechanism, bounded by configuration. Provider errors map to a small set of project exceptions whose messages never contain keys, prompts or artifact text.
- An observation wrapper records one event per call as JSON Lines, validated against `schemas/core/llm-event.v1.json`. Events hold metadata only (timing, model, billed units, estimated cost, agent, artifact ID), never prompts, artifact text or output.
- Cost is estimated from billed units and a dated price table copied from the provider's official pricing page. A missing price is left out, never guessed.
- Settings come from environment variables (`CO_API_KEY`, `KA_*`); locally `.env` is loaded with `uv run --env-file .env`.
- Tests never touch the network: a fake adapter and a stub SDK client cover the code, and a test fixture blocks sockets. Real calls happen only in a manual smoke check.

## Consequences

- Swapping a model or provider stays a contained change, and the fake makes every agent testable offline.
- Cost per artifact and per record can be derived from the event log, because every event carries the artifact ID.
- The event log is safe to keep and share, and cannot become an unvalidated second copy of the institutional memory.
- Metadata-only events make it harder to debug a bad output; opt-in debug capture to a git-ignored folder is in the backlog.
- The SDK adds dependencies to the supply chain; they are pinned in `uv.lock` and audited by pip-audit.
- Trial keys are rate limited and capped per month, so real calls (smoke checks, evaluation runs) must be budgeted.
```

### 8.2 `docs/architecture.md`

- **Observability:** replace the section with a short description of the event log (metadata only, JSON Lines, validated against `core/llm-event.v1.json`), billed units, the dated price table and how cost per artifact can be derived from `artifact_id`. Link ADR-0012.
- **Roles or a new short "LLM service layer" section:** one paragraph: three interfaces, one adapter per provider, `build_llm`, the fake for tests, and that callers validate model output themselves (Design principle).
- **Patterns and terminology:** add rows for "Observation wrapper" (decorator pattern) and "Fake adapter" (test double).

### 8.3 `README.md`

Add one line to "Getting started": run commands that need the API key with `uv run --env-file .env ...`, and point to the smoke check. Keep the README free of model IDs and prices (they change).

### 8.4 `dev/backlog.md`

- **Now:** remove the service layer item once this PR is ready.
- **Later**, add:
  - Opt-in debug capture of prompts and responses to a git-ignored folder, for prompt tuning (never in the event log).
  - Plain-text `chat` in the service layer, when an agent needs it (for example the Oracle).
  - Budget guard: stop a run before it exceeds a call or cost limit (trial keys are capped).
- Add anything the SDK check or smoke check leaves open under *Open questions*.

### 8.5 `dev/tool-feedback.md` and `dev/principles-in-practice.md`

Log the smoke check findings and any SDK surprises in `tool-feedback.md`. Add principles entries where a principle visibly shaped the work (for example P10 for the network-blocking fixture, or P4 for metadata-only events that still link cost to artifacts).

### 8.6 `dev/STATUS.md`

Update at the end of the session, including the smoke check results.

## 9. Suggested commit sequence

1. `chore: add the cohere runtime dependency`
2. `feat: add LLM interfaces, errors and settings` (implements ADR-0003)
3. `feat: add the Cohere provider schema reduction`
4. `feat: add the Cohere adapter and the fake adapter`
5. `feat: add the observation wrapper, event log and price table` (implements ADR-0012)
6. `feat: add build_llm and the Cohere smoke check`
7. `docs: add ADR-0012 and update architecture, README, backlog and logs`
8. `docs: record smoke check results and update status`

Each commit includes its tests and ends with a `Co-authored-by:` trailer. Run `ruff check`, `ruff format --check` and `pytest` before each commit. Suggested pull request title: `feat: add LLM service layer and Cohere adapter (handoff 003)`. Miguel adds the Copilot credits to `dev/costs.md` as the last commit before merging.

## 10. Done when

- The interfaces, Cohere adapter, fake adapter, observation wrapper, price table and `build_llm` exist with the tests in section 7, and `ruff check`, `ruff format --check` and `pytest` pass locally and in CI (`ci-ok` green), including Python 3.15.
- No test touches the network, and only `llm/cohere_adapter.py` imports `cohere`.
- The smoke check has been run once with Miguel's key, and its findings are recorded.
- ADR-0012 is added and the docs in section 8 are updated.
- No file was read from or copied from Chronicle. No secrets in the repo; `.env` stays untracked.
- `dev/STATUS.md` is updated and you have reported back, ending with **Cohere notes**.

## 11. Out of scope

Agents and their prompts (the Decision Registrar is handoff 004), storage, the Sensor and Artifact Ledger, Markdown views, plain-text chat, budget guards and evaluation runs.
