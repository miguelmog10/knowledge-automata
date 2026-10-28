# 0016. Guide published with GitHub Pages

- **Status:** Proposed
- **Date:** 2026-10-28

## Context

The visual guide (`docs/guide/index.html`) is one HTML page. GitHub shows an HTML file in a repository as source code, not as a page, so readers need it served. The guide also fetches the diagram sources in `docs/diagrams/`, which needs HTTP rather than a file opened from disk. The repository already pins every CI action to a full commit SHA with least-privilege permissions (ADR-0010).

## Decision

- Publish the guide with GitHub Pages, built by a GitHub Actions workflow (`.github/workflows/pages.yml`), not by the "deploy from a branch" setting, which would publish every file under `docs/` through Jekyll.
- The workflow copies only `docs/guide/index.html` and `docs/diagrams/*.md` into the site, plus a redirect from the site root to `guide/`. The address is <https://miguelmog10.github.io/knowledge-automata/guide/>.
- It runs on pushes to `main` that touch those paths, and by hand. Actions are pinned to commit SHAs; the build job can only read the repository, and only the deploy job may write to Pages.
- Mermaid is loaded from jsDelivr at a pinned version with a subresource integrity hash, so a changed file is refused by the browser.

## Consequences

- The guide is one click away for readers, and the repository stays the single source: the page and its diagrams update when `main` changes.
- Pages must be enabled once in the repository settings (Settings, Pages, Source: GitHub Actions).
- The page depends on jsDelivr and Google Fonts at view time. If either is unavailable, diagrams fall back to a link to their source on GitHub and text falls back to system fonts.
- A fork does not publish unless its owner enables Pages.
