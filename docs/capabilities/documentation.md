# Capability: documentation

> the-loop's documentation site — its information architecture, the rules that keep it
> honest, and the test that enforces them.

## What it is

A [VitePress](https://vitepress.dev) site under `docs/`, deployed to GitHub Pages by
`.github/workflows/docs.yml` and served from
<https://madarauchiha-314.github.io/the-loop/>.

Most of what the site publishes already lives under `docs/` and needs no copying. One
source cannot move — `skills/the-loop/reference/*.md` is read at **runtime** by the harness
from that exact path — so `docs/scripts/sync-content.mts` copies it in at build time.

## Current behaviour

### Information architecture

- The site SHALL present five top-level sections: **Guide** (the plugin), **CLI**,
  **Config**, **Reference** (plugin slash commands) and **Developer** (architecture,
  capabilities, decisions, operating model, specs, reports, contributing).
- The **CLI** SHALL be documented as a product in its own right, not as a single reference
  page: an overview, an installation page, a getting-started path, a concepts page, one
  page per registered command, and an extension guide (issue-117).
- **Config** SHALL be a top-level section covering **both** configuration files — the
  per-repo harness config and the machine-scoped CLI config — so a reader does not have to
  know which of the two they need before they can find either. The CLI config SHALL be
  split by area (webhook, routing, polling, integrations, observability) rather than
  presented as one page.
- Each onboarding page SHALL end with an explicit next-step link, so the path is walkable
  without the sidebar.

### The per-option format

- Every CLI-config option SHALL be documented under a `###` heading holding its path,
  in backticks, **relative to the page's `configBase` front-matter key**; and SHALL state
  its **Type** and its **Default**.
- The default SHALL equal the one declared in `.the-loop/cli-config.schema.json`, or, where
  the schema declares none, the value the code applies.
- Pages SHALL be **authored, not generated** from the schema. A generator would either drop
  the prose that makes an option's *rationale* legible — why sessions used to stall on a
  trust dialog, why `skipDangerousModePermissionPrompt` is user-global — or require the
  schema to carry long-form markdown. The schema is the **authority** the pages are checked
  against, not a template.

### The parity contract

`cli/tests/test_docs_parity.py` SHALL assert four properties, in both directions on both
axes, and SHALL be skipped only when `docs/` is absent (a source distribution):

| | Assertion | Prevents |
|---|---|---|
| P1 | every command in `the_loop.commands` has `docs/cli/commands/<name>.md` | a shipped command with no documentation |
| P2 | every page in `docs/cli/commands/` names a registered command | documentation for a command that is gone |
| P3 | every documented option resolves to a leaf in the CLI-config schema | documenting a removed key |
| P4 | every schema leaf has a documented option | an undocumented configuration block |

This exists because the failure it prevents already happened. `cli/README.md` was a
679-line flat file with nowhere to *put* a new command, so issue-109 shipped `check`,
`graph` and `migrate-config` with no entry, added the whole `integrations` block
undocumented, and removed `ghBinary` while five README references to it survived. Structure
alone does not fix that; structure plus a test does.

### The root `README.md` delegates; the site is the manual

- The README SHALL open on what the-loop **is** — an executable process graph and the
  daemon that runs it — before it names any harness. The Claude Code and Cursor plugins are
  a delivery surface for the operating model, documented after the graph, the two loops,
  the artifact chain and the CLI (issue-174).
- It SHALL cover only what a reader needs before deciding to read further, and SHALL
  **link** the site for anything the site documents in full: installation, the command
  reference, the CLI's per-command pages, the configuration reference, the operating model.
  Two copies of a fact is one copy that rots.
- Its documentation links SHALL be **absolute** `https://madarauchiha-314.github.io/the-loop/…`
  URLs, for the same reason `cli/README.md`'s are: the README renders on GitHub and on
  PyPI-adjacent surfaces where a relative site path is dead. Repository-relative links stay
  only for source the site does not render — `LICENSE`, `CLAUDE.md`, the graph YAMLs, the
  skill.
- It SHALL NOT carry a version-status block or a roadmap. Both must be re-approved every
  release to stay true, and neither was: the README described "v0 foundation" at v8.0.0.
- Anything it states about the process — the phase sequence, the loop names, the artifact
  chain — SHALL match the shipped graph, which `test_graph_parity.py`'s P4 pins for the
  phase sequence.

### The README's workflow diagram

- The README SHALL carry **one** diagram of the workflow, authored as an **Excalidraw**
  scene (the exception issue-150 established for the hero image; `diagramFormat: mermaid`
  continues to govern everything the harness produces). Two committed artifacts:
  `docs/assets/the-loop-workflow.excalidraw` (the scene) and
  `docs/assets/the-loop-workflow.svg` (what the README embeds, since GitHub cannot render
  `.excalidraw`).
- The SVG SHALL be **self-contained**: Virgil embedded as a `base64` data URI, no external
  URL, and no scripting construct — grepped before commit. Excalidraw's exporter emits
  `@font-face` rules pointing at *asset paths*, so the inlining step is not optional: without
  it the hand-drawn face degrades to a system font on GitHub with nothing failing.
- Both files SHALL round-trip into excalidraw.com — the SVG carries the embedded scene
  payload (`exportEmbedScene`).
- The scene's geometry SHALL be **computed by a committed generator** rather than placed by
  hand, so a regeneration is a command rather than a re-derivation
  (`docs/specs/issue-174/evidence/diagram/generate-scene.py`). The export tooling itself
  (headless Chromium plus `@excalidraw/excalidraw`) stays outside the repository.
- The diagram SHALL show what the shipped graphs declare, and is checked node-by-node
  against them — including the inner loop's `start:` node and the nodes it does **not**
  declare. It went stale for three releases before issue-174; being a picture is not an
  exemption from the gate below.

### Updating the user-facing docs is a completion gate (issue-174)

- A work item SHALL update the **user-facing documentation** its change made wrong — the
  root `README.md`, this site under `docs/`, and `skills/the-loop/SKILL.md` with its
  `reference/` docs — **in the same PR** as the change, and SHALL record what it changed in
  the execution log's **`## Documentation`** section.
- That section SHALL be gated by the outer loop's `capability-docs` node, alongside
  `## Capability docs` ([decision-066](../decisions/decision-066.md)). A work item that
  changed no user-facing document SHALL say so **with the reason**; the section is never
  deleted to shorten the log.
- The gate SHALL live on the existing node rather than a new one, and the node SHALL keep
  its id, `stage` and phase — `stage: capability-docs` is a public key in operators'
  `tokenEconomy.modelRouting.stages` and `thinkingEffort.stages` maps.
- The inner `pdlc-pr-loop` SHALL gate neither section: a work item's documentation is
  decided once, at the outer level.
- **What this proves SHALL be stated rather than implied**: the check is structural, so a
  heading holding placeholder text passes it. The gate proves the record exists; the
  reviewer judges whether the documentation is any good.

This exists because the failure it prevents already happened, twice over. issue-172 split
the PDLC into two loops and issue-163 added `testing-plan.md` to the spec chain, and the
README and the site's entry pages went on describing one loop and three artifacts —
because nothing read them before `complete`.

### `cli/README.md`

- SHALL remain a valid **standalone** document: it is the PyPI package readme
  (`cli/pyproject.toml` → `readme =`), rendered outside this repository.
- SHALL therefore use **absolute** `https://madarauchiha-314.github.io/the-loop/…` links —
  a relative link is dead on PyPI.
- SHALL NOT be copied into the site. It was, as `docs/cli.md`; issue-117 retired that copy
  in favour of authored pages, and `FILE_MAPPINGS` in `sync-content.mts` is now empty.

### Rendering constraints

- `markdown.html: false` — the docs are full of angle-bracket placeholder tokens in prose
  (`<session-id>`, `<phase>`, `<id>`) which VitePress's Vue-template compiler would treat as
  unclosed HTML. Escaping them to literal text matches how GitHub renders them. Consequence:
  **no raw HTML in any page**, so a meta-refresh redirect stub is not available.
- `ignoreDeadLinks: true` — `docs/decisions/` and `docs/capabilities/` link out to real
  files outside the site's `srcDir`. Consequence: **the build does not catch a broken
  internal link**, so link correctness is verified by grep, not by the build.
- Headings SHALL NOT contain an em dash. VitePress's slugify does not replace `—`, so it
  survives into the anchor id (`#collaborators-—-the-loop-collaborators-yaml`).
- Anchor ids come from VitePress's slugify, which replaces a run of punctuation with a
  single `-`: `` `state.root` `` → `#state-root`, `` `sources[].provider` `` →
  `#sources-provider`. Note this **differs from GitHub's**, which strips dots — so
  markdownlint's MD051 and VitePress disagree on any dotted heading. Same-page fragment
  links SHALL therefore target dot-free `##` section headings.

## Design

[`docs/specs/issue-117/design.md`](../specs/issue-117/design.md) ·
[`docs/.vitepress/config.mts`](https://github.com/MadaraUchiha-314/the-loop/blob/main/docs/.vitepress/config.mts)

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-174 | The root `README.md` rewritten to lead with the graph, the two loops and the CLI and to delegate everything else to this site; the site's three entry pages brought current (two loops, the four-artifact chain, `testing-plan.md`); the workflow diagram regenerated from a committed generator after owner review found it three releases stale; and updating the user-facing docs became a completion gate — `## Documentation` joins `## Capability docs` on the `capability-docs` node | [spec](../specs/issue-174/), [decision-066](../decisions/decision-066.md), [process-graph](process-graph.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/174) |
| issue-117 | The CLI documented as a product (onboarding path + one page per command), Config made a top-level section split by area, the `cli/README.md` → `docs/cli.md` copy retired, and the docs↔code parity test added — which is what forced `check`/`graph`/`migrate-config` and `integrations`/`workspace`/`routing.graph`/`polling.maxRetries` to be written, and `ghBinary` to be removed | [spec](../specs/issue-117/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/117) |
| issue-73 | `CLAUDE.md` added so the-loop's own cloud/web sessions run the loop instead of shipping one-off PRs | [issue](https://github.com/MadaraUchiha-314/the-loop/issues/73) |
| PR #71 | Established the VitePress site and the GitHub Pages deploy, including the spec sidebar generated from the filesystem | [PR](https://github.com/MadaraUchiha-314/the-loop/pull/71) |
