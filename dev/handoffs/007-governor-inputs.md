# Handoff 007 inputs: sample artifacts and expected results

Written by Claude on 2026-10-31 for [handoff 007](007-governor.md), section 6. The Tallyleaf story continues after the April board meeting (ART-0005). The team, the app and the meetings are fictional.

## 1. The artifacts

Save each one exactly as written (UTF-8, LF line endings, one newline at the end) in `runtime/inbox/` (git-ignored), under the file name given, then check its SHA-256. `tech-sync-2026-06-09.md` contains one typographic apostrophe (U+2019) on purpose, in Aisha's survey, as ART-0005 did.

| Artifact | File | Date | SHA-256 of the file |
|---|---|---|---|
| ART-0006 | `project-board-2026-05-26.md` | 2026-05-26 | `b5311602197be16c006804916bccc20bd726d959f3582348e43cbebc01f8e08e` |
| ART-0007 | `tech-sync-2026-06-09.md` | 2026-06-09 | `c6c447daa83a0b6987c0e5aebf5c00226511a98a8d9cdc32b0476df617f7c43f` |
| ART-0008 | `status-update-2026-06-16.md` | 2026-06-16 | `5fb8ee63b0493b8c00bf0ee16c18236029e421eabc88580bc2e1493aee40c4f2` |

### ART-0006: `project-board-2026-05-26.md`

````markdown
# Tallyleaf greenhouse inventory app: project board meeting

Date: 26 May 2026
Present: Julie Tremblay (product owner, chair), Marc Gagnon (tech lead), Aisha Benali (UX designer), Paul Nguyen (pilot grower advisor), Sofia Ramos (contract developer)

## 1. Pilot status

Paul reported that the growers now use the status paths per crop type every day. Wrong
statuses dropped from 41 batches to 3 in the last four weeks. Julie confirmed that the
status paths per crop type stay as the board decided in April.

## 2. Bench labels

Aisha showed the label layout: the bench number in large type above a QR code.

Decision: the board chose printed QR code labels for every bench, starting at Paul's
greenhouse in June.

Marc warned that the label printer the team ordered may not arrive before the June
pilot. If it is late, the labels would have to be printed at a print shop, at about three
times the cost. Marc will check the delivery date every Monday and order from the print
shop if the printer has not shipped by 8 June.

## 3. Offline counts

Sofia showed the first version of the sync code. When two phones count the same bench
offline, the phone that syncs last overwrites the other count.

Decision: when two offline counts of the same batch conflict, the app keeps both changes
and adds them together, instead of keeping only the last count. Sofia explained that
growers often split one bench between two people, so both counts are usually real.

## 4. Languages

Julie asked whether the app should launch in French as well as English, since two of the
pilot growers speak French at work. No decision yet: Aisha will ask the growers which
screens they would need in French.

## Actions

- Aisha: send the label layout to the printer supplier by 29 May.
- Sofia: change the sync code to add conflicting counts together.
- Marc: check the label printer delivery every Monday.
````

### ART-0007: `tech-sync-2026-06-09.md`

````markdown
# Tallyleaf tech sync

Date: 9 June 2026
Present: Marc Gagnon (tech lead), Sofia Ramos (contract developer), Aisha Benali (UX designer)

## 1. Bench labels

Aisha explained why the board picked QR codes in May instead of NFC tags: half of the
growers' phones cannot read NFC, and a printed QR label costs a few cents. The QR code
labels for every bench stay the plan.

## 2. Offline counts

Adding conflicting counts together failed in testing. When one grower recounted a bench
that another had already counted, the app doubled the batch. Marc and Sofia agreed to
replace that rule: the app now keeps the most recent count and shows both counts to the
grower, who confirms which one is right.

Sofia suggested a dark mode for the evening shifts. Nobody has asked for it yet, so it
stays an idea for later.

## 3. Languages

Aisha’s survey found that the two French-speaking growers need the count screen and the
status picker in French. Marc agreed to launch with English and French for those two
screens only. Translating the other screens could delay the July release if the
translator is not available in June; Aisha will ask a second translator as a backup.

## Decisions

- QR code labels for every bench stay the plan.
- Offline count conflicts: keep the most recent count and ask the grower to confirm.
- Launch the count screen and the status picker in English and French.
````

### ART-0008: `status-update-2026-06-16.md`

````markdown
# Tallyleaf weekly status

Date: 16 June 2026
From: Julie Tremblay (product owner)

Pilot: 212 batches counted at Paul's greenhouse this week, all on printed QR labels.
Build: Sofia is finishing the new conflict screen, and Aisha is reviewing the French text.
Next board meeting: 30 June.

Nothing needs a decision this week.
````


## 2. Expected work orders

What a careful reader finds, in the order code sorts them (by first appearance). The quotes are examples that pass the evidence check, not the only right ones: a work order matches when it points to the same item. The spike (`runtime/diagnostics/spike_governor.py`) uses these counts.

| Artifact | # | Register | Points to | Left out on purpose |
|---|---|---|---|---|
| ART-0006 | 1 | decision-log | "Julie confirmed that the status paths per crop type stay as the board decided in April." | the French question (open question); the actions |
| | 2 | decision-log | "the board chose printed QR code labels for every bench, starting at Paul's greenhouse in June" | |
| | 3 | risk-register | "the label printer the team ordered may not arrive before the June pilot", with Marc's response (check every Monday, print shop by 8 June) as part of the same risk | |
| | 4 | decision-log | "the app keeps both changes and adds them together, instead of keeping only the last count" | |
| ART-0007 | 1 | decision-log | "The QR code labels for every bench stay the plan." and the reason (NFC). The summary line "QR code labels for every bench stay the plan." is part of that sentence, so it matches the same place | the dark mode suggestion (proposal) |
| | 2 | decision-log | "the app now keeps the most recent count and shows both counts to the grower", plus the summary line | |
| | 3 | decision-log | "Marc agreed to launch with English and French for those two screens only", plus the summary line | |
| | 4 | risk-register | "Translating the other screens could delay the July release if the translator is not available in June" | |
| ART-0008 | | | none: a status update with nothing to record | everything |

Expected counts (decision-log, risk-register): ART-0006 (3, 1), ART-0007 (3, 1), ART-0008 (0, 0). For the spike, the five earlier artifacts: ART-0001 (1, 1: the Flutter decision and the offline sync risk), ART-0002 to ART-0005 (1, 0) each.

## 3. Expected records

The Ledger starts with `DEC-0001` (active), `DEC-0002` (superseded) and `DEC-0003` (active).

| Artifact | Work order | Expected change | Expected record |
|---|---|---|---|
| ART-0006 | 1 | reaffirmation of `DEC-0003` | `DEC-0003` revision 2, a source from ART-0006 |
| | 2 | new | `DEC-0004`: printed QR code labels for every bench. **No rationale and no alternatives**: the meeting states neither. `decided_by` is "the board" or absent, never the attendee list |
| | 3 | not routed | none (risk) |
| | 4 | new | `DEC-0005`: add conflicting offline counts together, with the stated rationale (benches split between two people) |
| ART-0007 | 1 | update of `DEC-0004` | `DEC-0004` revision 2, **rationale and alternatives filled** (half the phones cannot read NFC, QR labels cost a few cents; NFC tags set aside) |
| | 2 | supersession of `DEC-0005` | `DEC-0006`: keep the most recent count and ask the grower to confirm; `DEC-0005` superseded |
| | 3 | new | `DEC-0007`: launch the count screen and the status picker in English and French |
| | 4 | not routed | none (risk) |
| ART-0008 | | nothing | `processed` with zero records and an empty work orders file |

## 4. What each artifact tests

- **ART-0006:** several decisions and a risk in one meeting; a reaffirmation found by the Comparator inside a busy meeting; a risk response that belongs with the risk, not the decision log; an open question left out; and the v2 fix for invented fields (the QR decision has no stated rationale).
- **ART-0007:** the split trap: each decision appears twice, in its section and in the summary at the end, and should be one work order. If the Governor splits one anyway:
  - Decision 1: the summary line is part of the section sentence, so the two items share a quote, the check fails and the retry asks for one item. If the retry fails too, the whole reply is rejected: `processed` with nothing recorded and a Governor-stage rejected item, and a rerun is allowed. Report it as a finding before any rerun.
  - Decisions 2 and 3: the summary lines use other words, so a split passes the check, and the second work order becomes a reaffirmation of the record the first one wrote from the same meeting: harmless, but a finding.

  It also tests an update that fills fields the ART-0006 draft left empty (the case that failed for `DEC-0002` in handoff 006), a supersession, and `decided_by` when two people of three agreed.
- **ART-0008:** nothing to record: one Governor call, no drafts.

Known borderlines, to note rather than fix if they happen:

- ART-0006 work order 1 could be classified as an update of `DEC-0003` with no field filled (the pilot numbers could read as a new detail). Either outcome keeps one record.
- ART-0007 work order 2 says "Marc and Sofia agreed to replace that rule" at a tech sync, while `DEC-0005` was a board decision. A supersession is still the expected classification: the group changed its mind.
