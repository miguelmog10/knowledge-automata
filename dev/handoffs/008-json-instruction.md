# Handoff 008: the JSON instruction, then the v0.0.1 pre-release

- **From:** Claude (discovery, architecture, review)
- **To:** Copilot (implementation)
- **Owner and approver:** Miguel
- **Date:** 2026-11-05
- **Branch:** `feat/json-instruction`
- **Scope:** new prompt versions for the Governor (orchestrator), the Decision Registrar (specialist record keeper) and the Comparator (reconciliation), and their retry prompts, each ending with an instruction to reply with one JSON object; the pipeline switched to them; a test that keeps the instruction in every prompt the pipeline uses; a budgeted check of every agent with thinking disabled and enabled; one real run on a new sample artifact, ART-0009; then the v0.0.1 pre-release. No change to the thinking default, no Risk Registrar, no evaluation harness.
- **Inputs:** [008-json-instruction-inputs.md](008-json-instruction-inputs.md) holds ART-0009, its expected work orders and records, and the diagnostic's inputs and expected results.

**This handoff has three parts.** Copilot builds part 8A only. Part 8B is evidence (Claude's diagnostic and Miguel's real run), and part 8C is the pre-release (Claude's docs, then Miguel's tag and release). Plan and build only part 8A.

---

## 1. Context

In the handoff 006 real run, most first attempts with thinking disabled came back with the reasoning in prose before the JSON and were rejected; thinking was enabled to avoid it (handoff 006, Addendum A; ADR-0014). On 2026-11-02 a reproduction found the cause on our side: **none of our JSON-mode prompts asks for JSON**, which Cohere's structured outputs page requires of a `json_object` request. With one line at the end of the system prompt, "Reply with one JSON object that matches the response schema, and nothing else.", Command A+ with thinking disabled returned clean JSON three times out of three, at 272 output tokens, against 1,165 to 2,214 with thinking enabled. That was one prompt (`decision-registrar.v1`), one artifact (ART-0003) and SDK 7.3.0. The write-up is public at [cohere-feedback](https://github.com/miguelmog10/cohere-feedback); the `dev/tool-feedback.md` entry of 2026-11-02 has the details.

This handoff applies the fix to every live prompt, as its own change: it changes three prompts that are live, so a bad run must be traceable to this change alone, not mixed with a new Registrar. **The Risk Registrar is now handoff 009.**

Read `AGENTS.md`, `dev/STATUS.md`, ADR-0014, ADR-0017, ADR-0018, `src/knowledge_automata/core/prompts.py` and `tests/test_prompts.py` before planning.

**What Miguel and Claude decided (chat, 2026-11-05):**

1. **New versions of all six prompts the pipeline uses.** Prompt files are immutable once a record cites them (ADR-0014), so the fix is new files: `governor.v2`, `decision-registrar.v3`, `decision-comparator.v2`, and `governor-retry.v2`, `registrar-retry.v2`, `comparator-retry.v2`. On a retry, `retry_system_text` puts the retry prompt after the main prompt, so without new retry versions the instruction would sit in the middle and the error list would be the last thing the model reads; the line was only tested in last place. `decision-registrar.v1` stays as it is: the public reproduction uses it.
2. **One change per version.** Each new file is the previous version plus the instruction, nothing else. The content fixes waiting in the backlog (`decided_on` from a later meeting; an update that fills nothing) wait for later versions, so any difference in the checks can be traced to the instruction alone (changing one factor at a time). The `decided_on` line becomes a candidate for `decision-registrar.v4`.
3. **Wording and place, as tested:** the same sentence in all six files, after a blank line, as the last line, with no heading. On a retry it appears twice, at the end of the main prompt and at the very end; that is harmless.
4. **A conformance test** checks that every prompt the pipeline uses, including the retry prompts and every Registrar in `REGISTRARS`, ends with the instruction, so a new prompt (the Risk Registrar's in 009) cannot forget it. The frozen older versions are exempt.
5. **Thinking stays enabled by default.** Part 8B measures thinking disabled per agent as a starting point; the comparison that could change the default belongs to the evaluation set (backlog).
6. **The checks:** a diagnostic of every agent, outside the event log, in two passes (thinking disabled as a measurement, thinking enabled as a gate), at most 58 calls, then one real `process` run on ART-0009, about 11 calls. Cap: 80 calls in all. The existing sample records are evidence and are never rerun.
7. **The evaluation harness waits** for its own step. The diagnostic is git-ignored, but keeps its expected results in a data file and saves a report per run, so the harness can reuse both.
8. **Side-quest follow-ups are docs only** (tool feedback and backlog, already on this branch). Logging the trace ID, streaming and timeout semantics are backlog items.
9. **The pre-release:** an annotated tag `v0.0.1` on this pull request's squash commit, matching `__version__` (no bump), a GitHub release marked as a pre-release, and a new `CHANGELOG.md` from now on. ADR-0010's SBOM starts with v0.1.0, as written.

**Already on this branch (Claude wrote them, Miguel committed them):** this handoff and its inputs file; the six prompt files; docs only: `dev/STATUS.md` (the Risk Registrar renumbered to 009), `dev/backlog.md`, `dev/tool-feedback.md`, ADR-0016 accepted and the ADR index. **Do not modify the prompt files.** If you find a problem, raise it in your plan.

## 2. How to work on part 8A

1. **Plan first.** Read this whole document, then reply with a short plan: files to change, anything that does not fit the existing code, and the commits. **Wait for Miguel's approval.**
2. Small commits, tests in the same commit as the code. `ruff check`, `ruff format --check` and `pytest` before each commit. Trailers copied from the code block in `AGENTS.md`.
3. **No test may call the network.**
4. Ask instead of guessing; add open points to `dev/backlog.md` under *Open questions*.
5. End by updating `dev/STATUS.md` and reporting, with a **Cohere notes** section. Then stop.

## 3. The prompts (already committed)

| Agent | Prompt | Retry prompt | Replaces |
|---|---|---|---|
| Governor | `core/governor.v2` | `core/governor-retry.v2` | `governor.v1`, `governor-retry.v1` |
| Decision Registrar | `project-management/decision-registrar.v3` | `core/registrar-retry.v2` | `decision-registrar.v2`, `registrar-retry.v1` |
| Comparator | `project-management/decision-comparator.v2` | `core/comparator-retry.v2` | `decision-comparator.v1`, `comparator-retry.v1` |

Each new file is its predecessor's text unchanged (line endings aside), then a blank line, then:

```text
Reply with one JSON object that matches the response schema, and nothing else.
```

The register definitions (`decision-log.v1`, `risk-register.v1`) are not changed: they are parts of the Governor's prompt, not prompts of their own. The `{registers}` and `{errors}` placeholders are unchanged.

## 4. Part 8A: switch the agents to the new prompts (offline)

**Files:** `src/knowledge_automata/pipeline.py`, `tests/test_prompts.py`, `tests/test_pipeline.py`, `tests/test_cli.py`, `tests/test_process.py`, `dev/STATUS.md`. If anything else needs a change, say so in the plan.

**`pipeline.py`:**

- `governor()`, `decision_registrar()` and `decision_comparator()` load the six new prompts (section 3).
- The comment above `CHAT_THINKING_DEFAULT` gives today's reason: thinking disabled wrote its reasoning as prose before the JSON (handoff 006, Addendum A); the cause was prompts that never asked for JSON (ADR-0014); every prompt now ends with that instruction (handoff 008), and thinking stays enabled until the evaluation set measures thinking disabled. The value does not change.

**`tests/test_prompts.py`:**

- The listing and loading tests include the six new prompts, next to the old ones (old versions must keep loading: records cite them).
- The `{errors}` placeholder test covers the three v2 retry prompts; the `{registers}` test covers `governor.v2` (exactly once).
- **The conformance test.** The expected sentence is a constant in the test file (not in `src/`: prompt text lives in `prompts/`). For every agent the pipeline builds, collected from the pipeline's own factories (`governor()`, `decision_comparator()`, and every factory in `REGISTRARS`, so a new Registrar is covered without a test change):
  - the last line of `.prompt.text` and of `.retry_prompt.text`, after `rstrip()`, is exactly the sentence;
  - the retry system message, built with `retry_system_text` the way the agent builds it (for the Governor, from its rendered `system_text()`, not the raw prompt) and two sample errors such as `$.evidence[0]: quote not found in the artifact`, ends with the sentence after `rstrip()`, and both errors appear before it.
- One test that `decision-registrar.v1` does **not** end with the sentence, so nobody "fixes" the frozen file the public reproduction uses.

**Other tests, by one rule:** tests that check what the pipeline uses move to the new versions: `tests/test_pipeline.py` (the agents' prompt and retry versions), and `tests/test_cli.py` and `tests/test_process.py` (version constants such as `GOVERNOR_RETRY`, `RETRY_VERSION` and `COMPARATOR_RETRY`, the printed `prompt ...` lines, and the `prompt_version` values stored in the Ledger, records and work orders files). Tests that load a specific prompt to test an agent (`test_governor.py`, `test_registrar.py`, `test_registrar_work_orders.py`, `test_comparator.py`) and tests that use a version only as fixture data (records, Ledger, views) stay as they are: old versions keep loading, and records cite them. List every test changed in the report.

**Docs:** `dev/STATUS.md` (part 8A built, test count). **Commits:** `feat: switch every agent to the prompts that ask for JSON`, then `docs: update status after part 8A`.

## 5. Part 8B: evidence

**After Claude's review of 8A and Miguel's go.** Call budget: 60 for the diagnostic (58 planned, 2 spare), 20 for the real run. After a diagnosis, a single call that failed on a provider error may be rerun once from the spare calls; rerunning a whole pass, or going past either cap, needs a new budget from Miguel. Rules, as in handoffs 006 and 007: stop on a rejection or a provider error and diagnose before any rerun; `KA_LLM_TIMEOUT_SECONDS=180`; nothing is fixed by editing outputs; a result that differs from the expected tables is a finding for the backlog.

**Step 1: the diagnostic (Claude writes it, Miguel runs it).** A git-ignored script in `runtime/diagnostics/` with its expected results in a separate data file. It builds each request with the agents' own code (system text, user message, schema) and calls the adapter once per input, outside the event log, then runs the same check code would run (`validate_work_orders`, `validate_draft`, the Comparator's check). It never retries on its own, so each result is a first attempt. Inputs and expected results: inputs file, section 5. Each run saves a short report (JSON and a Markdown summary) in `runtime/diagnostics/reports/`.

| Agent | Inputs | Calls per pass |
|---|---|---|
| Governor v2 | ART-0001 to ART-0008 | 8 |
| Decision Registrar v3 | 11 decision work orders | 11 |
| Comparator v2 | 7 known comparisons (C1 to C7) | 7 |
| Retry prompts v2 | one per agent, with a made-up error | 3 |

- **Pass 1, thinking disabled (a measurement):** clean JSON, `finish_reason`, matches, output tokens and latency per agent. It does not block the merge; it is the evaluation set's starting point.
- **Pass 2, thinking enabled (a gate):** the default path. Every reply is clean JSON and passes its check; the Governor's counts, the Registrar's drafts and the Comparator's classifications match the inputs file (borderlines accepted). A mismatch stops the work for a diagnosis with Miguel before the real run: one run is a sample, so a mismatch is not by itself proof that the instruction caused it.

**Step 2: the real run (Miguel).** After Claude has read both reports and Miguel gives the go:

```powershell
uv run knowledge-automata ingest runtime/inbox/project-board-2026-06-30.md --artifact-date 2026-06-30 --memory examples/sample-project
uv run --env-file .env knowledge-automata process ART-0009 --memory examples/sample-project
uv run knowledge-automata views --memory examples/sample-project --check
```

Claude puts the file in `runtime/inbox/` on the computer (git-ignored, never committed); check its SHA-256 against the inputs file first. Expected: 1 Governor call and about 5 per routed decision, so about 11; stop at 20. Commit what comes out unedited (the copy, the Ledger entry, the work orders file, the records and views) in one commit, `feat: process ART-0009 with the prompts that ask for JSON`, and paste the full output into the pull request description.

**Step 3: docs (Claude).** The results appended to this handoff as section 9 (both passes and the real run, with the numbers); the sample project README (ART-0009, expected and actual); ADR-0014 amended (every JSON-mode prompt ends with the instruction since handoff 008; the thinking default is unchanged until the evaluation set); `dev/backlog.md` (the thinking comparison starts from the two reports); `dev/STATUS.md`. Commit: `docs: record the handoff 008 checks and real run`.

## 6. Part 8C: the v0.0.1 pre-release

**On the branch (Claude, docs only):**

- `CHANGELOG.md`, new, in the Keep a Changelog format. One section, `[0.0.1] - YYYY-MM-DD` (the tag date), with three short lists checked against what is on main: what works (the Sensor (intake and input guardrail), the Artifact Ledger, the Governor, the Decision Registrar, the Comparator, the views, the `process` and `release` commands, the sample project's real runs, ART-0009 included); what does not yet (the Risk Registrar, the folder command, the evaluation set, the SBOM); and the known findings (`decided_on` from a later meeting, an update that fills nothing, thinking disabled measured but not the default). Miguel fills in the date he will tag (normally the merge day) in the last commit before merging, with the `dev/costs.md` row, and tags that day.
- `README.md`: the status line links the v0.0.1 release, and the test count.
- `docs/guide/index.html`: the test count, a link to the release in "Where v0.1 stands", and the footer ("handoff 008"). The walkthrough stays as it is (it shows a past run, which stays true). Miguel retakes the previews only if the part they show changed.

**After the merge (Miguel):**

1. Wait for CI (`ci-ok`) to pass on `main` with the squash commit.
2. Tag and push:

   ```powershell
   git switch main
   git pull
   git log --oneline -5
   git tag -a v0.0.1 <squash-sha> -m "v0.0.1: first pre-release (handoff 008)"
   git show v0.0.1 --no-patch
   git push origin v0.0.1
   ```

   `<squash-sha>` is this pull request's squash commit, the one CI passed on, named explicitly so a later merge (the animation pull request, for example) cannot end up tagged. Check `git show` before pushing.
3. On GitHub, under Releases, draft a new release from the tag `v0.0.1`, titled `v0.0.1`, with the body Claude prepares from the changelog section. Check **Set as a pre-release**. If the animation pull request is merged by then, attach the four videos as release assets.
4. Then the case study and the LinkedIn post can link the release. The README link works from the moment the release exists, so tag soon after the merge.

**Suggested pull request title:** `feat: ask every agent for JSON in its prompts (handoff 008)`. Miguel adds the credits row to `dev/costs.md` as the last commit before merging.

## 7. Done when

- Part 8A: tests, `ruff check` and `ruff format --check` pass locally and in CI (`ci-ok`), including Python 3.15; no test touches the network; the six prompt files are unchanged from the branch.
- Part 8B: both diagnostic reports exist and pass 2 matches the inputs file, or each difference is diagnosed with Miguel; the ART-0009 run is committed unedited, `views --check` passes, and its output is in the pull request description.
- Part 8C: the changelog, README and guide match `main`; after the merge, the tag and the pre-release exist.
- Nothing was read from or copied from Chronicle, and `.env` stays untracked.

## 8. Out of scope

Changing the thinking default; a token budget; the content fixes for `decided_on` and for an update that fills nothing; the Risk Registrar; the evaluation harness; logging `x-debug-trace-id` and Cohere's server time; streaming; per-agent timeouts; the SBOM and the release workflow (v0.1.0); the diagrams (no architecture change).

## 9. Results (part 8B)

Run by Miguel on 2026-11-05 and 2026-11-06 with SDK 7.3.0 and Command A+ (`command-a-plus-05-2026`). The diagnostic's reports are in `runtime/diagnostics/reports/` (git-ignored); the numbers that matter are below. 67 calls in all, within the cap of 80: 56 for the diagnostic (two of them timed out) and 11 for the real run.

### 9.1 Pass 1: thinking disabled (a measurement)

24 calls. C4 to C7 and the Comparator retry did not run, because their drafts had failed.

| Inputs | Clean JSON | Matched | Output tokens | Latency |
|---|---|---|---|---|
| Governor, ART-0001 to ART-0008 | 8 of 8 | 4 of 8 | 4 to 156 (median 62) | 0.2 to 0.9 s |
| Decision Registrar, one-quote orders (ART-0001 to ART-0005) | 5 of 5 | 4 of 5 (R-ART-0002: a quote failed the evidence check) | 161 to 322 | 0.7 to 1.1 s |
| Decision Registrar, the Governor's orders (ART-0006, ART-0007) | **0 of 6** | 0 of 6 | 2,284 to 4,424 | 8.5 to 16.6 s |
| Comparator, C1 to C3 | **0 of 3** | 0 of 3 | 376 to 1,165 | 1.6 to 4.5 s |
| Retries (Governor, Registrar) | 1 of 2 | 1 of 2 | 117 and 2,476 | 0.6 and 8.7 s |

Every unusable reply ended with `finish_reason` COMPLETE and did not start with `{`: 1,800 to 21,300 characters came before any JSON, the failure of handoff 006, Addendum A. The Governor's replies were clean but its counts were off on four artifacts: an extra risk in ART-0002, an extra decision in ART-0005, a missing decision in ART-0006 and a missing risk in ART-0007.

**Finding: the instruction is necessary but not sufficient with thinking disabled.** It fixed the case of the 2026-11-02 reproduction (one decision, a short work order) but not the Registrar on artifacts with several items, nor the Comparator. Where the model has to judge, it seems to write that reasoning into the reply when its thinking is disabled (inferred from the replies' length and first character; the diagnostic never stores model text). Thinking disabled is not viable today for the Registrar and the Comparator on these inputs, and it lowered the Governor's recall. This is the third time one artifact gave a misleading result: the 2026-10-25 smoke check, the reduced schema of the reproduction, and "3 of 3" on ART-0003.

### 9.2 Pass 2: thinking enabled (the gate)

All 29 inputs answered, in five runs and 32 calls: two calls timed out, and one draft ran twice as a dependency of the Comparator retry.

| Inputs | Clean JSON | Matched | Output tokens | Reasoning tokens (median) | Latency |
|---|---|---|---|---|---|
| Governor | 8 of 8 | 7 of 8 | 344 to 5,628 (median 2,185) | 2,094 | 1.7 to 24.4 s |
| Decision Registrar | 11 of 11 | 11 of 11 | 1,393 to 3,136 (median 2,168) | 1,929 | 5.5 to 16.4 s |
| Comparator | 7 of 7 | 7 of 7 | 184 to 782 (median 357) | 313 | 1.0 to 4.3 s |
| Retries | 3 of 3 | 3 of 3 | 172 to 8,315 | 3,886 | 0.9 to 26.8 s |

**The gate passes.** Every reply was clean JSON and passed its check. The Comparator gave the expected class all seven times (C2 and C4 as the expected class, not the accepted borderline). The QR code draft (ART-0006, order 2) invented no rationale or alternatives. Each retry agreed with its first attempt; the Governor's retry on ART-0006 found exactly the four expected items.

- **G-ART-0002, a diagnosed borderline.** It returned (1, 1) in both passes, against (1, 0) expected. ART-0002 says "nobody has tested printed labels in a wet greenhouse", which fits the risk definition (an uncertain event); `governor.v1` returned (1, 0) in the handoff 007 spike. One sample per pass cannot tell the new line from ordinary variation. The expected results were not changed after the fact; the evaluation set decides.
- **The Governor on ART-0006 timed out again, twice:** the first attempt and the retry message, each at 180 s. The same requests then answered in 13.5 s (step A, 600 s timeout, 2,603 reasoning tokens) and 26.8 s (step D, 900 s timeout, 8,138 reasoning tokens). Every timeout in handoffs 007 and 008, four calls, was the Governor on ART-0006, two of them with `governor.v1`; every other call finished, the slowest in 27 s. So the instruction did not cause it, and a general slowdown is unlikely. Very long reasoning on this input is one explanation, a stall at Cohere for this request another. A call that times out returns nothing, so only streaming can tell them apart (backlog). A run that stops this way writes nothing and can be rerun.

### 9.3 The real run on ART-0009

Run `13d7f5e8-71a0-499d-83f6-85c2e818ac66` on 2026-11-06, thinking enabled, 180 s timeout: 11 calls (5 chat, 4 embed, 2 rerank), all OK. The Governor answered in 10.4 s. The outputs were committed unedited.

| Work order | Expected | Actual |
|---|---|---|
| 1, decision | new `DEC-0008` | new `DEC-0008`: first release on 21 July 2026, for the pilot growers only, with the stated rationale; `decided_by` "the board", `decided_on` 2026-06-30. Its candidates were `DEC-0004`, `DEC-0001` and `DEC-0006` (0.08 or less), so the related-topic borderline did not arise |
| 2, decision | update of `DEC-0007`, alternatives filled | update of `DEC-0007` to revision 2: alternatives filled (translating every screen; launching in English only), and `impacts` ("available in both English and French at launch"). That is the accepted borderline: an impact that restates the decision, not the September consequence of an alternative |
| 3, risk | not routed | not routed: the first app store review could delay the release. Its quotes are the slip and Marc's warning, not Sofia's test build, the agreed response |

The Ledger entry is `processed` (schema 1.2) and cites `decision-registrar.v3`; `views --check` passes. Billed tokens: Governor 1,234 input and 3,256 output; drafts 2,001 and 3,779; comparisons 2,572 and 827; Embed 737 input; Rerank 1,114 input.

### 9.4 What follows

In the backlog: the thinking comparison starts from these reports, and thinking disabled needs prompt work for judging tasks before a fair comparison; streaming moves up, as the only way to see what a stuck call does; the ART-0002 risk and the weak impact go to the evaluation set. For handoff 009: the Governor's risk work order left out the response, so the Risk Registrar should look for the response in the artifact, not only in the work order's quotes.
