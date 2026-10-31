# Containers

What runs inside Knowledge Automata (C4 level 2): one Python command-line app and two file stores. The roles are components of the app. A pipeline stand-in for the Governor (orchestrator) does every file write, because agents never import storage.

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
flowchart LR
  classDef built fill:#e9e5de,stroke:#22201d,stroke-width:1.5px,color:#22201d
  classDef planned fill:#e9e5de,stroke:#57524b,stroke-width:1.5px,stroke-dasharray:6 4,color:#57524b
  classDef focus fill:#e9e5de,stroke:#9c4426,stroke-width:3px,color:#22201d
  accTitle: Knowledge Automata containers
  accDescr: Knowledge Automata is one Python command-line app plus two file stores. Inside the app, a pipeline stand-in for the Governor runs the Sensor, the Decision Registrar and the Comparator, and does every file write to the memory folder. Every model call goes through the LLM service layer to Cohere and is logged to the event log. The Governor, Risk Registrar, Observer and Oracle are planned.

  operator["Operator<br/>(human in the loop)<br/>[Person]"]:::built

  subgraph ka["Knowledge Automata"]
    pipeline["CLI and pipeline<br/>[Container: Python app]<br/>stand-in for the Governor,<br/>does every file write"]:::built
    subgraph roles["Roles [Components of the app]"]
      sensor["Sensor<br/>(intake and input guardrail)"]:::built
      decision["Decision Registrar<br/>(specialist record keeper)"]:::built
      risk["Risk Registrar<br/>(specialist record keeper)"]:::planned
      governor["Governor<br/>(orchestrator)"]:::planned
      comparator["Comparator<br/>(reconciliation)"]:::built
      observer["Observer (quality control)<br/>Oracle (query interface)"]:::planned
    end
    subgraph llm["LLM service layer [Component]"]
      command["Command<br/>structured chat"]:::built
      embed["Embed"]:::built
      rerank["Rerank"]:::built
    end
    subgraph memory["Memory folder [Container: files]"]
      ledger[("Artifact Ledger<br/>and read-only copies")]:::built
      declog[("Decision log")]:::built
      risklog[("Risk register")]:::planned
      views[("Markdown views")]:::built
    end
    events[("Event log<br/>[Container: JSON Lines]")]:::built
  end

  cohere["Cohere platform<br/>[External system]"]:::built

  operator -- "commands" --> pipeline
  pipeline -- "checks bytes" --> sensor
  pipeline -- "drafts" --> decision
  pipeline -- "compares the draft" --> comparator
  pipeline -- "writes" --> memory
  governor -. "work orders" .-> decision
  decision --> command
  risk -.-> command
  comparator --> embed
  comparator --> rerank
  comparator --> command

  comparator ~~~ observer
  llm -- "API calls" --> cohere
  llm -- "one event per call" --> events

  subgraph legend["Legend"]
    direction TB
    k1["Built"]:::built -- "built flow" --> k2["Built"]:::built
    k3["Planned"]:::planned -. "planned flow" .-> k4["Planned"]:::planned
  end
```

Solid boxes and arrows are built on `main` today. Dashed boxes and dotted arrows are planned.

See the [interactive version in the guide](https://miguelmog10.github.io/knowledge-automata/guide/#containers).

*Source of truth for this diagram. Copies: docs/architecture.md (Overview). Edit this file first, then update the copies between their `diagram` markers.*
