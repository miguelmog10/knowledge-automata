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
