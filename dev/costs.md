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
| #15 | feat: add the Governor (orchestrator) (handoff 007) | Claude Opus 5.5 | 2801.6 | 9109.4 | | First handoff split into parts: 7A (the Governor agent and decision-registrar.v2: plan, implementation and one review fix commit) with the 7B plan, 710.0; 7B implementation (Ledger entry schema 1.2 and the held status, the work orders file, the process command, release of held artifacts), 1137.1, the largest single step so far; 7C, in a new Copilot chat (a review fix commit, then the real run of ART-0006 to ART-0008 with its outputs and docs), 954.5. The real run used 38 Cohere calls of the 50 allowed, including two Governor timeouts and a two-call diagnostic; Claude's spike before 7A used 17 more. |
| #19 | feat: ask every agent for JSON in its prompts (handoff 008) | Claude Opus 5.5 | 137.6 | 9247.0 | | Smallest so far: Copilot built part 8A only (the agents switched to the six new prompts, the conformance test and the test updates), after a plan review with three comments. Claude wrote the prompt files, the docs and the diagnostic. The evidence used 67 Cohere calls of the 80 allowed: 56 in the diagnostic (two of them Governor timeouts) and 11 in the real run of ART-0009. |
