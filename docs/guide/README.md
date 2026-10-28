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
5. Retake the preview screenshots (below), keeping the names `preview-light.png` and `preview-dark.png`, so the README needs no edit.

## Preview screenshots

`README.md` shows the top of the guide as `preview-light.png` or `preview-dark.png`, matching the reader's GitHub theme. To retake them after the guide changes, run this in PowerShell from the repository folder, on Windows with Microsoft Edge:

```powershell
$edge = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
$url  = "https://miguelmog10.github.io/knowledge-automata/guide/"
& $edge --headless=new --hide-scrollbars --blink-settings=preferredColorScheme=1 --window-size=1280,1200 --force-device-scale-factor=2 --virtual-time-budget=8000 --screenshot="$PWD\docs\guide\preview-light.png" $url
& $edge --headless=new --hide-scrollbars --blink-settings=preferredColorScheme=0 --window-size=1280,1200 --force-device-scale-factor=2 --virtual-time-budget=8000 --screenshot="$PWD\docs\guide\preview-dark.png" $url
```

`preferredColorScheme=1` forces light and `=0` forces dark, whatever the system setting. Then crop both images to the top of the page, down to the rule above "On the line" (2560 by 1330 pixels from the top left), and resize them to 1600 pixels wide. Any image tool works; Claude can do the crop when asked.
