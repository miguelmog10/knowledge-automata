# The closed loop for one artifact

Steps 1 to 5 of "How it works" in the README. The Registrars draft before the Comparator compares, so it only judges checked drafts ([ADR-0017](../decisions/0017-comparator-reconciliation.md)). Today `record-decision` skips step 2, and a pipeline stand-in marks the artifact processed. Dotted lines back toward the start are planned feedback loops.

```mermaid
---
config:
  theme: base
  fontFamily: "system-ui, -apple-system, \"Segoe UI\", \"Roboto\", \"Helvetica\", \"Arial\", sans-serif"
  themeVariables:
    background: "#e9e5de"
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", \"Roboto\", \"Helvetica\", \"Arial\", sans-serif"
    fontSize: "16px"
    primaryColor: "#e9e5de"
    primaryTextColor: "#22201d"
    primaryBorderColor: "#22201d"
    secondaryColor: "#e9e5de"
    secondaryTextColor: "#22201d"
    secondaryBorderColor: "#57524b"
    tertiaryColor: "#e9e5de"
    tertiaryTextColor: "#22201d"
    tertiaryBorderColor: "#c9c2b7"
    lineColor: "#807a71"
    textColor: "#22201d"
    titleColor: "#22201d"
    nodeTextColor: "#22201d"
    clusterBkg: "#e9e5de"
    clusterBorder: "#c9c2b7"
    edgeLabelBackground: "#e9e5de"
    noteBkgColor: "#e9e5de"
    noteTextColor: "#22201d"
    noteBorderColor: "#c9c2b7"
    actorBkg: "#e9e5de"
    actorBorder: "#22201d"
    actorTextColor: "#22201d"
    actorLineColor: "#807a71"
    signalColor: "#807a71"
    signalTextColor: "#807a71"
    labelBoxBkgColor: "#e9e5de"
    labelBoxBorderColor: "#c9c2b7"
    labelTextColor: "#22201d"
    loopTextColor: "#807a71"
---
flowchart TB
  classDef built fill:#e9e5de,stroke:#22201d,stroke-width:1.5px,color:#22201d
  classDef planned fill:#e9e5de,stroke:#57524b,stroke-width:1.5px,stroke-dasharray:6 4,color:#57524b
  classDef focus fill:#e9e5de,stroke:#9c4426,stroke-width:3px,color:#22201d
  accTitle: The closed loop for one artifact
  accDescr: An artifact enters through the Sensor, which records it in the Artifact Ledger. The planned Governor sends work orders to the Registrars, which draft records that code validates. The Comparator compares each validated draft with related records and code applies the write rule (new, update, reaffirmation or supersession); the Governor then marks the artifact processed in the Ledger. Today the record-decision command sends an accepted artifact straight to the Decision Registrar, then the Comparator, and a pipeline stand-in marks it processed. The Operator releases quarantined files today; the Observer and Oracle are planned, and Oracle insight notes approved by the Operator will re-enter as new artifacts through the Sensor.

  artifact["Artifact<br/>(file)"]:::built
  sensor["1. Sensor<br/>(intake)"]:::built
  ledger[("Artifact Ledger")]:::built
  governor["2. Governor<br/>(orchestrator)"]:::planned
  subgraph registrars["3. Registrars (specialist record keepers)"]
    decision["Decision Registrar"]:::built
    risk["Risk Registrar"]:::planned
  end
  comparator["4. Comparator<br/>(reconciliation)"]:::built
  registers[("Registers and views")]:::built

  operator["Operator<br/>(human in the loop)"]:::built
  observer["Observer<br/>(quality control)"]:::planned
  oracle["Oracle<br/>(query interface)"]:::planned

  artifact --> sensor
  sensor -- "accepted, quarantined<br/>or rejected" --> ledger
  operator -- "releases quarantine" --> ledger
  ledger -.-> governor
  governor -. "work orders" .-> registrars
  ledger -- "today: record-decision" --> decision
  decision -- "validated draft" --> comparator
  risk -.-> comparator
  comparator -- "new, update, reaffirmation<br/>or supersession" --> registers
  comparator -. "5. Governor marks processed" .-> ledger
  comparator -- "today: stand-in<br/>marks processed" --> ledger
  observer -. "checks health" .-> registers
  oracle -. "answers with citations" .-> registers
  operator -. "approves sensitive changes" .-> registers
  oracle -. "insight notes, after Operator approval" .-> artifact

  subgraph legend["Legend"]
    direction LR
    k1["Built"]:::built -- "built flow" --> k2["Built"]:::built
    k3["Planned"]:::planned -. "planned flow" .-> k4["Planned"]:::planned
  end
  registers ~~~ k1
  registers ~~~ k3
```

Solid boxes and arrows are built on `main` today. Dashed boxes and dotted arrows are planned.

See the [interactive version in the guide](https://miguelmog10.github.io/knowledge-automata/guide/#loop).

*Source of truth for this diagram. Copies: README.md (How it works), docs/architecture.md (Data flow for one artifact). Edit this file first, then update the copies between their `diagram` markers.*
