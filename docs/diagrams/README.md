# Diagrams

The architecture diagrams, written as Mermaid so GitHub renders them. Each file holds the one source of its diagram; `README.md`, `docs/architecture.md` and the [guide](https://miguelmog10.github.io/knowledge-automata/guide/) reuse them.

| Diagram | Shows |
|---|---|
| [System context](01-system-context.md) | The group, its Operator (human in the loop), the artifacts coming in and Cohere (C4 level 1) |
| [Containers](02-containers.md) | The app, its roles, the LLM service layer, the memory folder and the event log (C4 level 2) |
| [The closed loop](03-closed-loop.md) | One artifact from the Sensor (intake) back to the Artifact Ledger, with the roles around it |
| [ART-0001 to DEC-0001](04-art-0001-to-dec-0001.md) | The real run that produced the sample decision record |

## Conventions

- **Built versus planned:** solid boxes and arrows exist on `main` today; dashed boxes and dotted arrows are planned. Line style carries the meaning, so the diagrams also read in grayscale. Each diagram has a legend.
- **Style:** the paper theme from [mise-en-place](https://github.com/miguelmog10/mise-en-place) (`build/mermaid/starter.mmd`), with `fontFamily` at the root of the config. GitHub cannot load custom fonts or switch a diagram between light and dark, so these copies use system fonts on paper. The guide draws the same sources in its own light and dark styles.
- **C4 as flowcharts:** Mermaid's native C4 diagrams are experimental: no dashed lines, no legend and a fixed style. These diagrams are flowcharts that follow C4 conventions instead.
- **Copies:** `README.md` and `docs/architecture.md` embed copies between `<!-- diagram: ... -->` and `<!-- /diagram -->` markers. Edit the file here first, then the copies. A check script that keeps them identical is in the backlog.
