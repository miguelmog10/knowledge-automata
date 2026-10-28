# Guide

A visual, interactive guide to Knowledge Automata, for the owner first and for outside readers later: the closed loop with built versus planned, the status at a glance, a click-through walkthrough of how `ART-0001` became `DEC-0001`, and links down into the ADRs, schemas and docs.

## Open it

- **Online:** <https://miguelmog10.github.io/knowledge-automata/guide/>, published by `.github/workflows/pages.yml` ([ADR-0016](../decisions/0016-guide-on-github-pages.md)) once GitHub Pages is enabled for the repository.
- **Locally:** GitHub shows an HTML file as source code, and a browser opening the file directly cannot load the diagrams. From the `docs` folder run `python -m http.server`, then open <http://localhost:8000/guide/>.

## How it is built

- One HTML file, `index.html`, with its styles and scripts inline. It loads Mermaid 11.16.1 from jsDelivr with a subresource integrity hash, and three Google Fonts (Newsreader, Instrument Sans, JetBrains Mono).
- It draws no diagram of its own. It fetches the Mermaid sources in [`docs/diagrams/`](../diagrams/) and swaps their GitHub paper style for the page's light or dark style, so every diagram keeps one source.
- The look is direction B ("The pass") from the 2026-10-28 design review, until the mise-en-place screen theme replaces the values at the top of the stylesheet.

## How to refresh

This is a living guide. A refresh never needs a special handoff:

1. Reread `README.md`, `dev/STATUS.md`, the latest file in `dev/handoffs/` and any new ADRs in `docs/decisions/`.
2. Update the diagrams in `docs/diagrams/` first (solid when built on `main`, dashed or dotted when planned), then their copies in `README.md` and `docs/architecture.md`.
3. Update `index.html`: the stations, the status figures and lists, and the walkthrough if a new real run replaces it. Every "built" label must match `main`.
4. Change the refresh date and commit in the footer, and check the page in light and dark, at desktop and phone width.
