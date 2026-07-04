# Decision 018: UI/UX design artifacts are first-class, tracked design-phase artifacts

- **Status:** accepted
- **Date:** 2026-07-04
- **Deciders:** @MadaraUchiha-314 (issue #18)
- **Work item:** issue-18

## Context

the-loop's design phase produces `design.md` — markdown + **mermaid**, which is the right
medium for architecture, HLD and LLD. It is the **wrong** medium for **UI/UX** design,
which is inherently visual. Modern UI/UX design is represented as **Figma files** and,
increasingly, as **HTML + CSS + JS** prototypes (e.g. how Claude's design artifacts express
a rendered, clickable design). Issue #18 asked that these be valid artifacts tracked by
the-loop, added to the design skill / loop, with **patterns defined for how designers
iterate** on the generated design artifacts.

## Decision

Treat visual UI/UX design as **first-class, tracked design-phase artifacts**, siblings of
`design.md`, not throwaway attachments. This mirrors the existing **contract-first API**
convention (`apiSpecs`): the locked artifact is the *visual contract* implementation
conforms to.

Concretely:

- **Home** — checked-in visual artifacts live under `docs/specs/<id>/design/`
  (`design.uiArtifacts.dir`). HTML prototypes are checked in (text, diffable,
  self-contained); Figma is a **link** (with optional exported stills for evidence).
- **`design.md` gains a *UI/UX design* section** — an inventory table (artifact · type
  `html-prototype`/`figma`/`image` · location/link · screen·requirement · lock status)
  plus flows/states, design-system/tokens, and accessibility/responsiveness intent.
- **New config `design.uiArtifacts`** — `dir`, `format` (`html`/`figma`/`both`, default
  `html`), `selfContained` (default true — inline CSS/JS, no external network deps, so a
  prototype renders standalone and as a Claude-style artifact), `screenshotEvidence`.
- **New manifest artifact** — optional `spec-design-artifacts` (`docs/specs/<id>/design/`,
  phase `design`), present only when the work item has a user-facing surface.
- **The designer iteration loop** — a new reference `reference/design-artifacts.md` defines
  the pattern: generate/curate → **render** → the **designer** reviews the *rendered*
  output (not the markup) → feedback as ticket comments → iterate (edit the checked-in
  artifact, not new copies) → **lock** (`status: approved`) → screenshots as evidence and
  hand-off to implementation. It reuses the existing iterate-until-locked rule,
  per-phase human review, the `designer` persona, and the paper-trail rule verbatim.
- **Wiring** — `create-design`/`work-on` produce and iterate the artifacts when the work
  item is user-facing (and skip with `N/A` otherwise); SKILL.md, `workflow.md`,
  `collaboration.md`, the design template and README document it.

## Consequences

- UI/UX work has a first-class, reviewable home in the design phase; visual intent is
  captured, iterated and locked with the same rigor as requirements/design/tasks.
- Reuses every existing mechanism (iterate-until-locked, per-phase review, designer
  persona, paper trail, reviewer briefing) — no new phase, no new state-machine label.
- **Backwards compatible & additive**: work items with no user-facing surface produce no
  `design/` folder and an `N/A` UI/UX section — nothing forces a visual artifact.
- One more (optional) artifact kind and config block to understand; mitigated by making it
  clearly optional and analogous to the existing contract-first API convention.

## Alternatives considered

- **Embed UI mockups inline in `design.md` (base64 images / ASCII)** — rejected: markdown
  cannot represent a clickable, responsive, theme-aware prototype; a diffable,
  self-contained HTML file (or a live Figma link) is the right medium and renders standalone.
- **A separate `ui-design` phase / state-machine label** — rejected as unnecessary
  ceremony: UI/UX design *is* design. Modelling it as artifacts *within* the design phase
  reuses the existing review gate instead of adding a phase (contrast decision-017, which
  genuinely needed a new optional phase for a distinct root artifact).
- **Only support Figma (links), not HTML** — rejected: agent-generated HTML prototypes are
  a primary way coding agents express design now (Claude artifacts) and, being checked in,
  are diffable and reviewable in the PR; support both, `format` picks the default.
- **Only support HTML, not Figma** — rejected: designer-led teams live in Figma; a link
  keeps Figma as the source of truth without forcing an export.
