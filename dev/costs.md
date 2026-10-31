# Costs

Copilot credits used per pull request, so the cost of AI-assisted work stays visible. Miguel adds each pull request's credits as the last commit on its branch, just before merging.

| PR | Title | Model | Copilot credits used | Cumulative credits | Prompts | Notes |
|---|---|---|---|---|---|---|
| #1 | chore: scaffold repository (handoff 001) | Claude Opus 5.5 | 333.7 | 333.7 | | |
| #2 | ci: add aggregate required check and handoff 001 follow-ups | Claude Opus 5.5 | 327.1 | 660.8 | | |
| #3 | feat: add register schemas and validation (handoff 002) | Claude Opus 5.5 | 501.3 | 1162.1 | | |
| #4 | feat: add LLM service layer and Cohere adapter (handoff 003) | Claude Opus 5.5 | 1145.4 | 2307.5 | | Added after the merge, on the next branch (the rule is the last commit before merging). Includes Addendum A. |
| #5 | feat: add the decision slice from artifact to decision log (handoff 004) | Claude Opus 5.5 | 682.6 | 2990.1 | | Added after the merge, in a follow-up pull request. Includes the real run. |
| #8 | feat: add the Sensor and the Artifact Ledger (handoff 005) | Claude Opus 5.5 | 1118.4 | 4108.5 | | Includes the plan review (four questions answered before implementation). |
| #11 | feat: add the Comparator (reconciliation) to record-decision (handoff 006) | Claude Opus 5.5 | 2199.3 | 6307.8 | | Largest so far. Includes the plan review (two questions), Claude's review fixes, Addendum A (thinking enabled after the real run failed with it disabled), the UTF-8 output fix, and the real run of ART-0002 to ART-0005 (28 Cohere calls, including 4 diagnostic). |
