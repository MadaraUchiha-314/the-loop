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
| issue-117 | The CLI documented as a product (onboarding path + one page per command), Config made a top-level section split by area, the `cli/README.md` → `docs/cli.md` copy retired, and the docs↔code parity test added — which is what forced `check`/`graph`/`migrate-config` and `integrations`/`workspace`/`routing.graph`/`polling.maxRetries` to be written, and `ghBinary` to be removed | [spec](../specs/issue-117/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/117) |
| issue-73 | `CLAUDE.md` added so the-loop's own cloud/web sessions run the loop instead of shipping one-off PRs | [issue](https://github.com/MadaraUchiha-314/the-loop/issues/73) |
| PR #71 | Established the VitePress site and the GitHub Pages deploy, including the spec sidebar generated from the filesystem | [PR](https://github.com/MadaraUchiha-314/the-loop/pull/71) |
