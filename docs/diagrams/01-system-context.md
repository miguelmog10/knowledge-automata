# System context

Who and what Knowledge Automata works with (C4 level 1). A group writes artifacts; its Operator (human in the loop) runs Knowledge Automata, which drafts records with Cohere Command and publishes Markdown views.

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
  accTitle: Knowledge Automata system context
  accDescr: A group writes artifacts. Its Operator runs Knowledge Automata, which turns the artifacts into validated records using Cohere Command and publishes Markdown views. Retrieval with Embed and Rerank and question answering are planned.

  subgraph group["The group, for example a project team"]
    members["Group members<br/>[Person]<br/>meet, chat, write documents,<br/>read the records"]:::built
    operator["Operator (human in the loop)<br/>[Person]<br/>runs the commands,<br/>reviews quarantined files"]:::built
  end
  artifacts["Artifacts<br/>[Input]<br/>meeting notes, chats, documents<br/>(.md and .txt files today)"]:::built
  ka["Knowledge Automata<br/>[Software system]<br/>turns artifacts into validated records<br/>that trace back to their sources"]:::focus
  cohere["Cohere platform<br/>[External system]<br/>Command, Embed, Rerank"]:::built

  members -- "write" --> artifacts
  artifacts -- "ingested from files" --> ka
  operator -- "runs ingest, record-decision, release" --> ka
  ka -- "drafts records with Command" --> cohere
  ka -. "finds related records with Embed and Rerank" .-> cohere
  ka -- "Markdown views" --> members
  ka -. "answers with citations" .-> members

  subgraph legend["Legend"]
    direction LR
    k1["Built"]:::built -- "built flow" --> k2["Built"]:::built
    k3["Planned"]:::planned -. "planned flow" .-> k4["Planned"]:::planned
  end
```

Solid boxes and arrows are built on `main` today. Dashed boxes and dotted arrows are planned.

See the [interactive version in the guide](https://miguelmog10.github.io/knowledge-automata/guide/#context).

*Source of truth for this diagram. Copies: docs/architecture.md (Overview). Edit this file first, then update the copies between their `diagram` markers.*
