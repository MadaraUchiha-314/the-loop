---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#398"
---

# Documentation: a logo for the-loop (issue-398)

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| `docs/capabilities/documentation.md` | a *The mark* section under *Current behaviour*: the site, the root README, the PyPI page and the dashboard carry the mark from one generated source, pinned by `--check`; which surfaces use the light/dark files and which the self-switching one | issue-398 row added |
| `docs/capabilities/channels.md` | the Slack app's icon is the mark, uploaded by hand under *Basic Information → Display Information* (the manifest format carries no icon); the step is in the Slack guide | issue-398 row added |
| `docs/capabilities/design-artifacts.md` | not changed: this work item *used* the capability exactly as described — a self-contained gallery, iterated on the rendering with the designer over three reviews, screenshot evidence, the designer's sign-off recorded as a row-level `approved` | none |

## Documentation

| Document | What changed |
|----------|--------------|
| `README.md` | opens with the mark — a centred `<picture>` with a dark-scheme source and a light `<img>` (`docs/assets/the-loop-logo-dark.svg` / `-light.svg`) |
| the docs site — `docs/.vitepress/config.mts`, `docs/index.md` | `head` links the SVG favicon and the apple-touch icon; `themeConfig.logo` and the home page's `hero.image` use the light/dark files under `docs/public/`; the site builds (T4a) |
| `cli/README.md` (the PyPI page) | opens with the 1024 px raster, 128 px wide, from `main` |
| `ui/index.html` (the dashboard) | `<link rel="icon" href="favicon.svg">`, served from `ui/public/`; the dashboard builds (T4b) |
| `docs/guide/slack.md` | *The app's icon*: the manual upload step under *1. Create the Slack app from the manifest*, pointing at `docs/assets/the-loop-logo-1024.png` |
| `docs/specs/issue-398/design/logo-options.html` | the reviewable presentation of the ten colourways (round 3), unchanged by the adoption |
| the plugin manifests | not changed: neither format has an icon field |
