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
