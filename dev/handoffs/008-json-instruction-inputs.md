# Handoff 008 inputs: ART-0009 and the expected results

Written by Claude on 2026-11-05 for [handoff 008](008-json-instruction.md), part 8B. The Tallyleaf story continues at the board meeting that ART-0008 announced. The team, the app and the meetings are fictional.

## 1. The artifact

Claude puts it in `runtime/inbox/` (git-ignored) on the computer. To recreate it, save the block below exactly as written (UTF-8, LF line endings, one newline at the end) under the file name given, then check its SHA-256. Copying from this file in a checkout with `core.autocrlf` gives CRLF line endings and a different hash. It is plain ASCII.

| Artifact | File | Date | SHA-256 of the file |
|---|---|---|---|
| ART-0009 | `project-board-2026-06-30.md` | 2026-06-30 | `154ba90cbbdee27595bbfaa32742337dadfb810e31ad8b8d9d72d2497c1ce857` |

### ART-0009: `project-board-2026-06-30.md`

````markdown
# Tallyleaf greenhouse inventory app: project board meeting

Date: 30 June 2026
Present: Julie Tremblay (product owner, chair), Marc Gagnon (tech lead), Aisha Benali (UX designer), Paul Nguyen (pilot grower advisor), Sofia Ramos (contract developer)

## 1. Release date

Paul reported that the pilot growers counted every bench with the app in June, and asked
when the other growers can start.

Decision: the board set the first release for 21 July 2026, for the pilot growers only.
Other greenhouses join after the pilot review in September. Julie explained that the team
wants a month of real use with a small group before more growers depend on the app.

## 2. Languages

Julie asked why only two screens will be in French at launch. Marc explained that the team
also considered translating every screen, and launching in English only. Both were set
aside: translating every screen would push the release to September, and English only
would leave the two French-speaking growers without the screens they use most. The board
kept the plan to launch the count screen and the status picker in English and French.

## 3. App store review

Marc warned that the first app store review could take more than a week. If the build is
rejected, the release could slip past 21 July. Sofia will submit a test build by 7 July to
find problems early.

Paul asked whether growers could print their own replacement labels. No decision yet:
Aisha will check the cost of a small label printer for each greenhouse.

## Actions

- Sofia: submit a test build to the app stores by 7 July.
- Aisha: price a small label printer for each greenhouse.
- Julie: invite the pilot growers to the release on 21 July.
````

## 2. Expected work orders

What a careful reader finds, in the order code sorts them. The quotes are examples that pass the evidence check, not the only right ones: a work order matches when it points to the same item.

| # | Register | Points to | Left out on purpose |
|---|---|---|---|
| 1 | decision-log | "the board set the first release for 21 July 2026, for the pilot growers only", with "Other greenhouses join after the pilot review in September." as part of the same decision | Paul's report on the pilot |
| 2 | decision-log | "The board kept the plan to launch the count screen and the status picker in English and French", with the alternatives Marc names | |
| 3 | risk-register | "the first app store review could take more than a week", with Sofia's test build by 7 July as its response | the replacement labels question (open question); the actions |

Expected counts (decision-log, risk-register): (2, 1). A separate item for "Other greenhouses join after the pilot review in September." would give (3, 1): a finding to report, not a borderline.

## 3. Expected records

The decision log starts with `DEC-0001`, `DEC-0003`, `DEC-0004`, `DEC-0006` and `DEC-0007` active, and `DEC-0002` and `DEC-0005` superseded.

| Work order | Expected change | Expected record |
|---|---|---|
| 1 | new | `DEC-0008`: first release on 21 July 2026, for the pilot growers only, with the stated rationale (a month of real use with a small group). `decided_by` is "the board" or absent, never the attendee list; `decided_on` 2026-06-30 |
| 2 | update of `DEC-0007` | `DEC-0007` revision 2, **alternatives filled** (translating every screen; launching in English only). Its rationale, `decided_by` and `decided_on` are already set, so an update leaves them as they are. `impacts` is also empty: filling it from the same paragraph (the release stays in July, the two growers get their screens) is an accepted borderline; filling it with the alternatives' consequences (a September release) is a finding |
| 3 | not routed | none (risk) |

ART-0009 ends `processed`, with 2 records produced and 1 work order not routed.

## 4. What ART-0009 tests

- The new prompts (`governor.v2`, `decision-registrar.v3`, `decision-comparator.v2`) through the real `process` command, the work orders file and the Ledger, with thinking enabled (the default). The Ledger entry and the records then cite the new versions.
- A new decision on a topic close to an existing record: the release date mentions the launch, like `DEC-0007`.
- An update where the meeting confirms a decision and adds the alternatives it set aside, the detail `DEC-0007` lacks.
- A risk with its response, which stays a saved, not-routed work order. Handoff 009 (the Risk Registrar) can start from it.
- An open question and action items, left out.

It avoids the two known findings on purpose: `DEC-0007` already has `decided_on`, and the update has a field to fill.

Known borderlines, to note rather than fix if they happen:

- Work order 2 could be classified as a reaffirmation of `DEC-0007` if the Comparator judges the alternatives not to be a detail of substance. One record either way; report it.
- Work order 1 could be compared with `DEC-0007` (both mention the launch). The expected classification is new: a different decision on a related topic.

## 5. Diagnostic inputs (part 8B, step 1)

The diagnostic gives each agent fixed inputs, so a result measures that agent and its prompt only, and one agent's slip does not change another's inputs.

### 5.1 Governor (`governor.v2`): 8 calls per pass

ART-0001 to ART-0008, from `examples/sample-project/artifacts/`. Expected counts (decision-log, risk-register), from [007-governor-inputs.md](007-governor-inputs.md), section 2: ART-0001 (1, 1), ART-0002 to ART-0005 (1, 0) each, ART-0006 (3, 1), ART-0007 (3, 1), ART-0008 (0, 0). A reply matches when it passes `validate_work_orders` and its counts per register are the expected ones.

### 5.2 Decision Registrar (`decision-registrar.v3`): 11 calls per pass

One call per decision work order, each with its artifact:

- ART-0006 and ART-0007: the six decision-log orders in the committed work orders files (`examples/sample-project/work-orders/`).
- ART-0001 to ART-0005: one order each, register `decision-log`, with one evidence quote: the decision statement, taken from the record that artifact produced or changed (the first source excerpt from that artifact, which passed the evidence check in the real runs). The other excerpts, such as action items, are left out, as a Governor would leave them out:
  - ART-0001 (`DEC-0001`): "Decision: the board chose to build one Flutter app for iOS and Android, because a single codebase lets two developers ship the walkthrough count to both platforms at the same time."
  - ART-0002 (`DEC-0002`): "Decision: every batch of plants moves through one status ladder: propagating, growing, ready, sold. A batch can be marked discarded at any step."
  - ART-0003 (`DEC-0001`): "Decision: the platform decision stands, and Tallyleaf stays one Flutter app for iOS and Android."
  - ART-0004 (`DEC-0002`): "Decision: the board kept the one status ladder for every batch for version 1, and separate statuses per crop type were set aside."
  - ART-0005 (`DEC-0003`): "Decision: the board replaced the single status ladder with one status path per crop type."

A draft matches when it passes `validate_draft` with the work order quotes. For ART-0006 work order 2 (the QR labels) also check the 007 expectations: no rationale and no alternatives, `decided_by` "the board" or absent.

### 5.3 Comparator (`decision-comparator.v2`): 7 calls per pass

The new decision is that pass's Registrar draft for the same work order (skipped and counted if the draft did not pass). The candidates are those of that work order's `produced` item in the Ledger entry, in the same order, each rebuilt as it was when that work order was compared: its current content minus the fields filled by revisions dated at or after the work order's own write (the `at` of the revision it produced, from the records' `history`), and status active. An update only fills empty fields, so earlier revisions are kept as they were; for example, C7 sees `DEC-0004` with the fields ART-0007's first order had just filled. Three comparisons of the real runs that ended `new` (ART-0002, ART-0006 order 4, ART-0007 order 3) are left out to keep within the budget; C5 covers `new`.

| Comparison | Work order | Expected | Accepted borderline |
|---|---|---|---|
| C1 | ART-0003 | reaffirmation of `DEC-0001` | |
| C2 | ART-0004 | update of `DEC-0002` | reaffirmation of `DEC-0002` (the real run's update filled no field) |
| C3 | ART-0005 | supersession of `DEC-0002` | |
| C4 | ART-0006, order 1 | reaffirmation of `DEC-0003` | update of `DEC-0003` (as in the real run) |
| C5 | ART-0006, order 2 | new | |
| C6 | ART-0007, order 1 | update of `DEC-0004` | |
| C7 | ART-0007, order 2 | supersession of `DEC-0005` | |

A reply matches when it passes the Comparator's check (a target among the candidates, in the register, active) and its classification and target are the expected ones or the accepted borderline.

### 5.4 Retry prompts (v2): 3 calls per pass

One call per agent with the retry system message built as the agent builds it (`retry_system_text`: the main prompt, for the Governor its rendered system text, then the retry prompt with one made-up error). Inputs and errors: the Governor on ART-0006, `$.items[0].evidence[0]: quote not found in the artifact`; the Registrar on ART-0006 order 2, `$.evidence[0]: quote not found in the artifact`; the Comparator on C5 (with that pass's draft), `$.target_id: not one of the candidates shown`. A reply matches when it is clean JSON that passes the same check as a first attempt.

### 5.5 What each call records

Agent, input, thinking setting, clean JSON or not (parsed from the first character), `finish_reason`, the check's result and errors (error paths only, never model text), whether it matches, billed input and output tokens, reasoning tokens when the response reports them, and latency.
