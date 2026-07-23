# Decision 033: the documentation site reads `docs/` in place; no duplicated `docs-site/` mirror

- **Status:** accepted
- **Date:** 2026-07-23
- **Deciders:** @MadaraUchiha-314 (issue #70, PR #71 review)
- **Work item:** issue-70
- **Spec:** `docs/specs/issue-70/`

## Context

Issue #70 asked for a proper product-documentation site for the-loop — VitePress-style,
Markdown-only, deployed to GitHub Pages on merge to `main` — with two explicit
constraints: **do not maintain two authoring toolchains**, and **reuse the existing docs
rather than duplicating them**.

The first implementation (PR #71, initial revision) put the site in a new top-level
`docs-site/` folder and ran a build-time script that **copied all of** `docs/architecture`,
`docs/roadmap.md`, `docs/decisions/`, `docs/capabilities/`, plus `cli/README.md` and
`skills/the-loop/reference/`, into `docs-site/`. On review the owner rejected this: *"Why
did we create a new folder? Why can't we just use `docs`? I don't want contents to be
duplicated there … We might need to add stuff to our `docs/` or restructure it to make it
consumable as a product documentation site."*

The copy was the problem. Even though the copies were git-ignored, the mental model was
"the site is a mirror of docs/," which invites drift and a second place to look.

## Decision

Point VitePress's `srcDir` at the existing **`docs/`** directory. The files already under
`docs/` **are** the site's pages — there is no copy of them. Concretely:

- `docs/.vitepress/config.mts` holds the site config (`base: "/the-loop/"`, default
  theme, local search, nav/sidebar). `docs/package.json` + `docs/scripts/` hold the
  toolchain, scoped to the docs site only (the CLI stays Python — `decision-030`). The
  toolchain is **bun** (the-loop's declared TS package manager,
  `tooling.packageManager.ts`) and all scripts are **TypeScript** (`.mts`, run by bun
  directly via native type stripping) — no JS, one lockfile (`bun.lock`), matching the
  repo's own tooling contract.
- `docs/architecture/`, `docs/capabilities/`, `docs/decisions/`, `docs/specs/` and
  `docs/reports/` render **in place**. New hand-written site pages (`docs/index.md`,
  `docs/guide/*`, `docs/reference/*`, `docs/contributing.md`,
  `docs/operating-model/index.md`, `docs/specs/index.md`, `docs/reports/index.md`) live
  under `docs/` like any other doc.
- **The only** build-time sync that remains is the two sources that structurally cannot
  live under `docs/`:
  - `cli/README.md` → `docs/cli.md` — `cli/README.md` is the CLI package's PyPI readme
    (`cli/pyproject.toml` `readme = "README.md"`), so it must stay at `cli/README.md`.
  - `skills/the-loop/reference/*.md` → `docs/operating-model/reference/` — these are read
    at **runtime** by the harness from that exact path (progressive disclosure), so they
    cannot move.
  Both synced destinations are git-ignored and markdownlint-ignored: the canonical file
  is the one linted and versioned; the copy exists only inside a build.
- `docs/specs/<id>/` (per-work-item artifacts) and `docs/reports/` **are** part of the
  built site (PR #71 review: "why are we excluding docs and reports … we should keep
  it"). The `docs/specs/` sidebar is generated from the filesystem in `config.mts`, so
  new work items appear without manual nav upkeep.

## Consequences

- **One source of truth, visible.** A contributor edits `docs/decisions/decision-0xx.md`
  and it is *both* the repo's decision record and the site page — there is no second copy
  to update.
- **Residual sync is tiny and justified.** Two mappings, each for a file that genuinely
  cannot be relocated, documented in `docs/scripts/sync-content.mts` and
  `docs/contributing.md`.
- **`ignoreDeadLinks` stays on.** Canonical `docs/decisions` / `docs/capabilities`
  content links out to `cli/README.md`, `skills/the-loop/SKILL.md`, and into
  `docs/specs/<id>/` (excluded from the site). Rewriting those canonical links to satisfy
  the site would mutate the historical record for presentation's sake and re-break on
  every upstream edit; instead dead-link checking is disabled and the canonical files
  stay authoritative. Cost: the build won't flag a genuinely broken *site* link —
  mitigated by keeping hand-written pages' links consistent and preview-checked.
- **`docs/` now mixes "site" scaffolding with content.** `docs/.vitepress/`,
  `docs/package.json`, `docs/scripts/` sit alongside the Markdown. Accepted as the cost of
  no duplication; VitePress conventions (the `.vitepress/` dir, `node_modules/`) keep them
  out of the built output.
- **The specs sidebar is generated, not hand-listed.** Including ~20 work items × ~5
  artifacts each as a static nav would drift the moment a spec is added. `config.mts`
  enumerates `docs/specs/*/` at build time and orders each item by the loop's own phase
  order, so the nav self-updates — the same low-maintenance principle as reading `docs/`
  in place.

## Alternatives considered

- **A separate `docs-site/` that syncs all of `docs/`** (the rejected first revision).
  Simple to reason about as a build, but it duplicates the content into a second tree and
  reads as a mirror — exactly what the owner rejected. The residual-sync-only approach
  removes the duplication entirely.
- **Move `cli/README.md` and `skills/the-loop/reference/` under `docs/`** to eliminate the
  last sync. Rejected: `cli/README.md` must stay put for the PyPI package readme, and the
  reference docs are read at runtime by the harness from `skills/the-loop/reference/` —
  relocating either breaks a functional contract for a cosmetic gain.
- **Excluding `docs/specs/` and `docs/reports/` via `srcExclude`** (the first cut of this
  decision). The reasoning was that they're historical/internal and would clutter the
  vite.dev/guide-style IA. Reverted on review — the owner wanted them kept ("why are we
  excluding docs and reports … we should keep it"). They're now included; the generated
  specs sidebar keeps them navigable without hand-maintained nav.
- **Rewrite canonical cross-links instead of `ignoreDeadLinks`.** Rejected: it edits the
  historical record to serve the site and is fragile against future content changes.
