---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#298"
phase: needs-review
status: in-progress
---

# Execution Log: control-plane UI redesign — the Classical system

> Append-only log of progress for the user's visibility.

## Process note

The owner opened [#298](https://github.com/MadaraUchiha-314/the-loop/issues/298) with a
**finished, signed-off design** attached (a Claude Design export on the Classical
design system) and a direct instruction: *"Remove whatever UI is there and use this.
… Only change the presentational component and UI/UX design. If we have written
connectors to the-loop's api, all that should remain the same."* As with issue-283,
the owner's issue text is the directive: the design phase arrived already locked (the
attached export is the visual contract, checked in under
[`design/`](design/)), the scope is presentation-only, and the work item is delivered
as one PR carrying the implementation, awaiting the tier-3 `human-approves-pr` gate.
No separate spec chain was authored — the requirement is one sentence of the issue,
and the design is the attachment.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| design | 2026-08-26 | @MadaraUchiha-314 (design attached to the issue) | The Classical export is the locked visual contract. |
| implementation | 2026-08-26 |  | Re-skin on `claude/github-issue-298-pi4sfr`. |
| verification | 2026-08-26 |  | See [`evidence/verification.md`](evidence/verification.md). |
| needs-review |  |  | PR raised; awaiting the owner. |
| complete |  |  |  |

## What was delivered

**Presentation only — every API connector, model join, route and control verb is
untouched** (`ui/src/api/`, `ui/src/state/`, `ui/src/demo/` unchanged):

- The **Industry** design system is replaced wholesale by **Classical**:
  `ui/src/styles/industry.css` deleted, `ui/src/styles/classical.css` vendored
  verbatim from the export's `_ds/…/styles.css` (Cormorant Garamond headings over
  Lora body, hairline rules, a single #b68235 accent applied as stroke, outlined
  buttons). `app.css` rewritten on those tokens against the two design screens.
- The **header bar is retired**; the Work sidebar is the navigation, per
  `Control Plane.dc.html`: brand block ("the-loop / Control plane") on top, the
  work-item rows (dot · ref · relative time / title · small-caps flag chip),
  standing sessions under a hairline, and a footer carrying Events →, Settings →
  and the health dot + popover (unchanged behaviour, new home).
- The labelled **node rail becomes the design's tick bar** — one slim tick per
  node (accent for done, taller pulsing accent for current, ink for blocked,
  shortened for skipped) captioned `current · n of m`; each node's name and state
  stay readable in the tick's tooltip and aria-label. Same component serves the
  outer loop (now in the detail header) and each PR card's inner loop.
- The **detail header** follows the design: `ref · Open on GitHub ↗ · session line`,
  the serif title, the tick rail beneath, session verbs at the right; the question
  card reads "The loop asks"; the **chat bar** sits under its own hairline at the
  pane's foot with the design's hint line, sticky at the bottom.
- The **transcript** renders as the design's editorial thread: "You" / "the-loop"
  speaker labels in small caps with the time beside, centered italic meta rows,
  bordered folds on the raised neutral for thinking and tool calls (mono summaries,
  Error chip preserved).
- **Settings** is the design's reading column ("← Work items", serif title,
  subtitle, bordered cards with small-caps accent kickers); **Events** and
  **Standing** — surfaces the export does not draw — are restyled onto the same
  system (Classical `.table`, tick-styled tags, stroke-only buttons including the
  ink-stroked danger variant).
- Docs updated in the same PR: `ui/README.md` (layout, vendored-stylesheet note,
  screen map) and `docs/capabilities/control-plane.md` (behaviour bullet + history
  row). `.markdownlint-cli2.jsonc` ignores `docs/specs/*/design/**` — the export is
  vendored verbatim, so the app is linted, not the artifact.
- Tests updated only where they asserted retired presentation: the "Outer loop ·"
  heading assertion became a rail-role assertion, and the question card's kicker
  text. All 168 tests pass; oxlint and `tsc --noEmit` clean; production build green.

## Verification

The testing plan for a presentation-only change: the existing unit/React suite
(behaviour must not move), lint/typecheck/build (the same three commands CI and the
Pages publish run), and UI/visual evidence per `design.uiArtifacts.screenshotEvidence`.
Results and raw output: [`evidence/verification.md`](evidence/verification.md);
screenshots of all five surfaces (overview, item, standing, events, settings) beside
it. Contract/integration/perf testing: n/a — no API, route or model change.

## Round two — the owner's decluttering direction (2026-08-26)

On [PR #299](https://github.com/MadaraUchiha-314/the-loop/pull/299) the owner replied
that round one was still too cluttered and restated the design's intent — *"a clean
design with just the sidebar and the main canvas and the settings page"* — with the
rendered design screenshot as the reference. Round two pares the surface to exactly
that:

- **Sidebar**: one flat "Work items" list, newest activity first (chips carry the
  attention); standing sessions as flowing `name — description` rows; the footer is
  Settings → plus the health dot. The inbox strip, the group headers and the
  no-sessions banner are gone.
- **Canvas**: header (ref line · serif title · tick rail with a parked/blocked note),
  the trace flowing unboxed at the reading measure, the chat bar at the foot. With
  nothing selected the most recently active item shows. Removed: the overview inbox,
  the waits/errors rows, the PR cards (PR sessions stay reachable as trace tabs), the
  control/tmux tags line and the second per-item event list.
- **The question card matches the design**: question + "Reply below" pointer — the
  chat bar is the reply box, posting the same `POST /sessions/reply`. The parked-gate
  card keeps its Approve (the one in-place action the design's flow needs).
- **The Events screen is retired** per the owner's sentence; the event trail remains
  as the trace's fallback and `#/events[/ref]` hashes land on Work (a ref permalink on
  that item's canvas). Connectors remain untouched.
- Tests reworked to the new surface (168/168 green); `WorkItemDetail` keyed by ref so
  switching items resets the viewed trace (a latent staleness the auto-selection
  exposed).

## Documentation

- `ui/README.md` — the design-system section, screen map and layout tree now
  describe Classical and the sidebar-as-navigation shape.
- `docs/capabilities/control-plane.md` — dashboard behaviour bullet extended;
  issue-298 history row added.
- No other user-facing doc describes the dashboard's look; the docs site embeds
  the README.
