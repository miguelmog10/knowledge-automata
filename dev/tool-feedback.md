# Tool feedback

Notes on tools, SDKs and documentation used while building, so useful feedback is not lost and can later become upstream issues, pull requests or posts.

Entry format: date, tool, type (confusing, missing, bug, delight), note, suggested improvement.

<!--
### YYYY-MM-DD: Tool name (type)

Note: what happened.
Suggested improvement: what would have helped.
-->

## Entries

### 2026-10-24: GitHub (missing)

Note: secret scanning was the only security setting on by default for a new public repository. Dependabot alerts, Dependabot security updates and private vulnerability reporting needed manual setup.
Suggested improvement: offer a one-click secure baseline for new public repositories.

### 2026-10-24: GitHub (confusing)

Note: a ruleset can only require a status check that has already run, so required checks cannot be configured before the first pull request.
Suggested improvement: allow typing a check name in advance, or explain the limitation in the ruleset UI.

### 2026-10-24: GitHub (confusing)

Note: the squash merge pre-filled one `Co-authored-by:` trailer per commit, so identical trailers were duplicated and had to be trimmed by hand.
Suggested improvement: deduplicate identical trailers in the squash commit message.

### 2026-10-25: GitHub Copilot web fetch in VS Code (missing)

Note: fetching the raw `versions-manifest.json` from `actions/python-versions` (to check which Python versions `setup-python` supports) failed with "Failed to extract meaningful content". The GitHub releases API for the same repository worked and gave the answer.
Suggested improvement: return raw text for JSON responses instead of trying to extract page content.

### 2026-10-25: GitHub Copilot terminal tool in VS Code (confusing)

Note: the first `pip install -e ".[dev]"` inside the activated `.venv` was not run; the tool suggested Python environment tools instead. Running the identical command again worked.
Suggested improvement: explain why the command was redirected, or run it when a virtual environment is already active.

### 2026-10-25: ruff 0.17.2 (confusing)

Note: `ruff format --check` reported more files than the three Python and TOML files in the repo. Verbose output showed it includes Markdown files (README, ADRs, the handoff) by default. Everything passed, but the count was surprising.
Suggested improvement: make the included file types visible in the default summary.

### 2026-10-25: Cohere structured outputs docs (confusing)

Note: while designing the record schemas, the "parameter types in JSON" page showed supported keywords only through examples, every one of which marks all properties as required, so it did not say whether optional properties are allowed. The unsupported keywords (`minLength`/`maxLength`, `minimum`/`maximum`, `minItems`/`maxItems`, `allOf`/`oneOf`/`not`, `uniqueItems`) are listed on a different page.
Suggested improvement: one table of supported and unsupported JSON Schema keywords on the parameter types page, including whether optional properties are allowed.

### 2026-10-25: jsonschema (confusing)

Note: while checking the draft record schemas, a record with `"created_at": "yesterday"` passed validation even with `FORMAT_CHECKER` enabled. `date` is checked out of the box, but `date-time` is only checked when the optional `rfc3339-validator` package is installed; otherwise it is silently skipped.
Suggested improvement: warn, or fail, when a schema uses a format the installed checker cannot assert.

### 2026-10-25: Cohere structured outputs docs (confusing)

Note: the structured outputs guide sends the schema as `response_format: {"type": "json_object", "schema": {...}}`, while the Chat API reference names the same field `json_schema`. It is unclear which name the API expects, or whether both work.
Suggested improvement: use one field name in the guide, the API reference and the SDK, or document the alias.

### 2026-10-25: Cohere Chat API (missing)

Note: the Chat API reference says `response_format` is "not supported when used in combinations with the documents or tools parameters", and the structured outputs guide says JSON schema mode is not supported in RAG mode. The Comparator (reconciliation) and Oracle (query interface) will therefore need either retrieved records pasted into the message or a second call, rather than grounded generation plus a schema in one request. The limit appears only in parameter descriptions, not in the guide's overview.
Suggested improvement: state the limitation near the top of the structured outputs guide, with the recommended pattern for structured output over documents.

### 2026-10-25: Cohere structured outputs docs (confusing)

Note: the supported-keywords table marks `additionalProperties` as supported, with a footnote: "`additionalProperties` does not enforce `required`, `dependencies`, `propertyNames`, `anyOf`, `allOf`, `oneOf`". It is hard to tell what that means in practice (for example whether `required` is still enforced in a schema with `additionalProperties: false`). The docs are also silent on annotations (`$schema`, `$id`, `title`, `x-*` keys).
Suggested improvement: one table per keyword with "enforced", "accepted but ignored" or "rejected".

### 2026-10-25: hatchling (confusing)

Note: with `force-include` mapping `schemas/` into the package, an editable install (`uv sync`) also copies a snapshot of the schema files into `site-packages/knowledge_automata/schemas`. The source package still wins the import, so code reads the live files, but the stale copy is easy to mistake for the real one while debugging.
Suggested improvement: skip `force-include` copies for editable installs, or document that they are copied.

### 2026-10-25: uv on OneDrive (bug)

Note: `uv sync` failed with "Access is denied" while replacing files in `.venv`, because OneDrive was syncing the folder. Retrying after a few seconds worked.
Suggested improvement (uv): retry briefly on Windows sharing violations, or name the locking process in the error.

### 2026-10-25: GitHub Copilot terminal tool in VS Code (confusing)

Note: a multi-line commit message passed with `git commit -m` from PowerShell was split at the embedded double quotes, and git treated the rest as file paths. Writing the message to a file and using `git commit -F` worked. uv also writes progress to stderr, which PowerShell reports as an error with exit code 1 even when the command succeeded.
Suggested improvement: pass multi-line messages through a file by default on Windows, and judge success by the process exit code rather than stderr.

### 2026-10-25: uv editable installs after moving a project (confusing)

Note: after the project folder was moved, the editable install in `.venv` (`_editable_impl_knowledge_automata.pth`) still pointed at the old `src` folder. Nothing failed: while the old copy existed, imports and tests would have silently used it. We deleted and rebuilt `.venv` rather than testing whether `uv sync` repairs it.
Suggested improvement: warn in `uv sync` or `uv run` when an editable install points outside the current project.

### 2026-10-25: Cohere pricing page (missing)

Note: cohere.com/pricing lists only Model Vault per-instance prices. It gives no per-token prices for `command-a-plus-05-2026` or `embed-v5.0-fast`, and no per-search-unit or per-token price for `rerank-v5.0-pro`. The docs page "How does Cohere pricing work" explains billed units but gives no numbers. The price table therefore ships with no Cohere models, and the event log carries no cost.
Suggested improvement: publish per-unit list prices for each API model, with the unit (tokens or search units) stated per model.

### 2026-10-25: Cohere Python SDK 7.3.0 (confusing)

Note: following up the `schema` versus `json_schema` entry above: the SDK's `JsonObjectResponseFormatV2` also names the field `json_schema`, like the API reference, while the structured outputs guide uses `schema`. The SDK model allows extra fields, so `schema` passes through unchecked, and only a real call shows which name the API enforces. The smoke check settles it.
Suggested improvement: one name across the guide, the API reference and the SDK.

### 2026-10-25: Cohere Python SDK 7.3.0 (confusing)

Note: the SDK pulls in 28 packages, including `tokenizers`, `huggingface-hub`, `hf-xet`, `fastavro`, `requests` and two HTTP stacks (`httpx` and `httpx2`). `cohere/client.py` imports `tokenizers` at the top, so the chain cannot be avoided even when local tokenization is never used. Through `huggingface-hub` it also needs PyYAML, which has no Python 3.15 wheel yet: on Windows with 3.15 the install fails without a C compiler.
Suggested improvement: make local tokenization an optional extra (for example `cohere[tokenizers]`) and import it lazily.

### 2026-10-25: Cohere Python SDK 7.3.0 (confusing)

Note: the SDK wraps HTTP error responses in `ApiError` subclasses (there is no `cohere.ApiError`; it lives in `cohere.core.api_error`), but lets `httpx` timeouts and connection errors through unwrapped, so an adapter has to import `httpx` as well. A 402 (billing limit) arrives as a plain `ApiError` with no subclass. The SDK also emits a Pydantic `__fields__` deprecation warning when parsing chat responses.
Suggested improvement: wrap transport errors in an SDK exception, add a subclass for 402, and move to Pydantic 2 `model_fields`.

### 2026-10-25: Cohere Python SDK 7.3.0 (delight)

Note: the SDK's built-in retries are well designed: exponential backoff with jitter, honouring `Retry-After`, for 408, 409, 429 and 5xx responses and connection errors, bounded by `max_retries` on the client. The service layer did not need its own retry loop. Passing an `httpx.Client` with `httpx.MockTransport` made it possible to test the adapter offline against the real SDK serialization and error classes.
Suggested improvement: document the retry policy (which statuses, the backoff and the timeout default of 300 seconds) in the SDK README.

### 2026-10-25: ruff 0.17.2 (confusing)

Note: following up the earlier ruff entry: `ruff format --check` also formats Python code blocks inside Markdown, and failed on the committed handoff, whose Python examples are not meant to be reformatted. We excluded `dev/handoffs` from formatting in `pyproject.toml`.
Suggested improvement: say in the summary that Markdown code blocks are checked, and make it easy to opt out per file type.

### 2026-10-25: Claude file bridge to the local computer (bug)

Note: several files Claude wrote into the repository and into Miguel's journal arrived as an earlier version, although every write reported success. The pattern was a second write of the same file: the revised handoff 003 and event schema were lost this way, so Copilot implemented the first version, and journal entries disappeared several times (first blamed, wrongly, on an editor). Found when Claude re-read the files from the computer and compared them.
Suggested improvement (Claude): verify the delivered content against what was sent, or fail the write; meanwhile Claude writes each version under a new name and reads it back from the computer to confirm it arrived.

### 2026-10-25: Cohere structured outputs (confusing)

Note: following up the two `schema` versus `json_schema` entries above: the smoke check found both names enforced on `command-a-plus-05-2026` (the model returned "vermilion" for the sky under each). SDK 7.3.0 logs "The `response_format.schema` parameter is an experimental feature and may change in future releases" on every call that uses `schema`, and nothing for `json_schema`. The adapter now sends `json_schema`; the smoke check keeps testing both names.
Suggested improvement: use `json_schema` in the structured outputs guide, or say there that `schema` is an experimental alias.

### 2026-10-25: Cohere Command A+ reasoning (missing)

Note: Command A+ thinks by default, and thinking tokens are billed as output tokens. For the same decision draft, thinking enabled used about 6x the billed output tokens of thinking disabled (1,320 versus 223, then 1,256 versus 223), with the same validation result. Latency was 6.3x in one run and 1.6x in the other. One artifact only, so not yet a conclusion about quality. Chat responses also report raw token counts (`usage.tokens`) that differ from billed ones (raw input 728 versus 256 billed), without saying what the difference is.
Suggested improvement: state in the reasoning guide that thinking is on by default and billed as output, with a typical cost ratio, and explain raw versus billed tokens.

### 2026-10-25: Cohere Rerank v5.0 Pro (confusing)

Note: `rerank-v5.0-pro` bills input tokens (`meta.billed_units.input_tokens`, 39 for one query and three short documents) and reports no search units, while the API reference and older pricing describe rerank in search units. Embed and rerank responses also report no raw `meta.tokens`, unlike chat.
Suggested improvement: state the billing unit per rerank model in the API reference and on the pricing page.

### 2026-10-25: Cohere Python SDK 7.3.0 (bug)

Note: parsing responses raises `PydanticDeprecatedSince20: The __fields__ attribute is deprecated, use the model_fields class property instead`, from `cohere/core/unchecked_base_model.py` line 328. pytest shows it on every adapter test; it will become an error when Pydantic 3 removes `__fields__`.
Suggested improvement: use `model_fields` in `unchecked_base_model.py` (a candidate upstream issue or pull request).

### 2026-10-26: Cohere Command A+ structured output (open observation)

Note: in the first real `record-decision` run, the first response, with thinking disabled, was unusable (`LLMResponseError`) after 10.3 s and 2,390 billed output tokens: more output than thinking enabled used for a similar draft in the smoke check (about 1,300). The retry was accepted with 322 output tokens. The cause is unknown, because events record only the error type, so this is not yet a finding about Cohere: it could be the prompt, the schema, the response or our parsing. One run only.
Suggested improvement: for us first, record `finish_reason` and the adapter's error message (metadata, no content) in events so the next failure can be diagnosed (backlog, *Open questions*).

### 2026-10-28: Cohere Python SDK 7.3.0 (confusing)

Note: `ChatResponse.finish_reason` is typed `ChatFinishReason`, which is `typing.Literal["COMPLETE", "STOP_SEQUENCE", "MAX_TOKENS", "TOOL_CALL", "ERROR", "TIMEOUT"]` joined with `typing.Any`, so a type checker accepts any value and the documented values cannot be relied on. Our event writer keeps the value only when it is a string, cut to 64 characters.
Suggested improvement: type it as the literal plus `str` (the usual pattern for forward-compatible enums), or document why `Any` is needed. The file (`cohere/types/chat_finish_reason.py`) is generated by Fern, so the change belongs in the API definition.

### 2026-10-28: Windows PowerShell 5.1 (confusing)

Note: `Set-Content -Encoding UTF8` writes a byte order mark, which turned up as a stray character in a Python source file, and quoting a multi-line `python -c` argument is mangled. Piping a here-string to `uv run python -` and writing files with `[IO.File]::WriteAllText` and a `UTF8Encoding($false)` avoided both.
Suggested improvement: for us, prefer the editor's file tools for source files and here-strings for scripts; PowerShell 7 writes UTF-8 without a BOM by default.

### 2026-10-28: Claude file bridge to the local computer (bug, again)

Note: the same problem as on 2026-10-25. A second write of the Cohere journal, sent from the same staging path as the first, delivered the earlier version although the write reported success. Reading the file back and comparing hashes caught it; writing the same content from a new staging path delivered it correctly.
Suggested improvement (Claude): as before, verify delivered content or fail the write. Workaround that worked: stage every new version of a file from a new path, then read it back and compare hashes.

### 2026-10-28: Mermaid 11 theme configuration (confusing)

Note: `fontFamily` set under `themeVariables` in a diagram's frontmatter is ignored: the SVG uses Mermaid's default font (`"trebuchet ms", verdana, arial`). Set at the root of `config`, it applies. Found with Mermaid CLI 11.16.1 while drawing these diagrams with the mise-en-place starter.
Suggested improvement: document which theme variables each diagram type reads, or warn on unused keys. For us: fixed in the mise-en-place brief.

### 2026-10-28: Mermaid C4 diagrams (missing)

Note: C4 support is still experimental. Mermaid's own docs list dashed lines, legends and tags as unsupported, styling is fixed, and layout follows statement order. In a test render, relationship labels overlapped and the title and labels were unreadable on a dark background, so built versus planned cannot be shown by line style.
Suggested improvement: support `$lineStyle` and a legend as in C4-PlantUML. For us: flowcharts that follow C4 conventions.

### 2026-10-28: GitHub Mermaid rendering (confusing)

Note: GitHub draws every Mermaid node with a drop shadow, whatever the theme, and serves the diagram in a frame whose light or dark mode follows the account setting, not the page. Neither can be changed from the diagram source.
Suggested improvement: honor the diagram's own theme without extra effects, or document them.

### 2026-10-28: Claude file bridge to the local computer (confusing)

Note: two PNG previews written to the repository came back with different SHA-256 hashes and about 6 KB larger than the files sent, while the pixels were identical (compared pixel by pixel). The bridge appears to re-encode PNG files in transit. Text files came back byte for byte.
Suggested improvement (Claude): copy binary files unchanged, or say when a file is re-encoded. For us: verify images by pixels, text files by hash.

### 2026-10-28: Microsoft Edge headless screenshots (confusing)

Note: `msedge --headless=new --screenshot` follows the Windows color setting, so on a computer in dark mode the "light" preview came out dark. `--force-dark-mode` forces dark, but nothing forces light by default.
Suggested improvement: document how headless mode picks the color scheme. For us: `--blink-settings=preferredColorScheme=1` forces light and `=0` forces dark (steps in `docs/guide/README.md`).

### 2026-10-30: Claude file writing and JSON escape sequences (confusing)

Note: in handoff 006 as first committed, the JSON escape `\u003c` appeared as a literal `<` in all three places, so the rule read "every `<` escaped as `<`", which says nothing. The escape was decoded somewhere between Claude's draft and the file on disk. Copilot noticed it while planning, from the contradiction in the text, and Claude fixed it in a follow-up commit before any code was written. Cause, found by Claude on 2026-10-30: its own file-writing tool decodes `\u003c` in the content it is given, and it happened again the same day in another document. Claude now writes text that contains escape sequences through a script and checks the file afterwards.
Suggested improvement (Claude): write escape sequences in file content literally, or warn when text that looks like an escape is decoded. For us: when a handoff quotes an escape sequence, read it back from the committed file; Copilot's plan review is the second check.
