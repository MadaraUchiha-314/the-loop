---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#300"
phase: needs-review
status: in-progress
---

# Execution Log: nesting work items and their PRs in the sidebar

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-26 | — | Tier 3 (`human-approves-pr`): one screen's structure, no contract change. Brainstorming skipped — the issue states the target shape outright |
| requirements-definition | 2026-08-26 | | [`requirements.md`](requirements.md) — five requirements, three abuse cases, scope boundary drawn at collapse/expand |
| design | 2026-08-26 | | [`design.md`](design.md) — render the existing `sessionTree`; move the viewed trace onto the route; three CSS rules |
| test-planning | 2026-08-26 | | [`testing-plan.md`](testing-plan.md) — eleven rows, six of them applicable |
| tasks-breakdown | 2026-08-26 | | [`tasks.md`](tasks.md) — seven tasks |
| implementation | 2026-08-26 | | On `claude/github-issue-300-ab9r0d` |
| verification | 2026-08-26 | | [`evidence/verification.md`](evidence/verification.md) — 171/171, lint and build clean, screenshots captured |
| needs-review | 2026-08-26 | | PR raised; awaiting the owner |
| complete | | | |

## What was delivered

The sidebar the issue-298 redesign shipped is flat by construction, while the board's
data is not: a work item's outer loop spawns a `pdlc-pr-loop` per pull request, each
with its own session and transcript. Those sessions had no row on this surface at all —
they were reachable only as unlabelled tabs inside an item's canvas.

- **Two-level sidebar.** Each work item's PR sessions render as nested rows beneath it
  (dot · `#216`, or `loop-docs#47` when the PR is in another repository · age), inside a
  `<ul>` named for the item so the nesting is in the accessibility tree and not only in
  the indent. Items with no PR sessions are unchanged; loops with no outer/inner split
  (`pdlc-adhoc-loop`, `pdlc-contribution-loop`, `pdlc-review-loop`) render treeless.
- **Rendered from the join that already existed.** `sessionTree` in `src/api/model.ts`
  was written for the pre-298 Sessions screen and has been dead production code since
  that screen retired — its only remaining caller was its own test. It already knew
  which items are treeless and which endpoints hang off an item, so it gained two fields
  for the row (`label`, `lastActivity`) instead of a second, divergent derivation being
  written beside it.
- **The hash became the single source of truth for the viewed trace.** `WorkItemDetail`
  held it in `useState` seeded once from a prop — sound while the pane's own tabs were
  the only way to change traces, and a latent bug the moment the sidebar can select a PR
  too (clicking a PR of the *already-open* item would have changed nothing). It is now a
  prop derived from the route, the trace tabs are links onto the same hashes the sidebar
  rows use, and the four consumers that read the old state — the transcript fetch, the
  caption's session, the event-fallback filter and **the chat bar's target** — read one
  resolved value.
- **A ref the shown item does not own falls back to that item's own session** rather
  than requesting a transcript for another item's (abuse case A1). The service's
  fail-closed path resolution (issue-209) is still the enforcing boundary; this keeps
  the page from knocking on the door.
- **Three row states**, because a selected PR would otherwise leave the sidebar reading
  as "nothing is open" while the canvas plainly shows an item: `current` for the
  selected row at either level, and a lighter `owner` tint on the work item whose PR is
  selected.

Presentation and client-side routing only: no endpoint, request shape or response shape
is touched, and `src/api/client.ts`, `src/api/types.ts` and `src/demo/` are unchanged.

## Verification

Full results in [`evidence/verification.md`](evidence/verification.md): 171/171 tests
(168 before), oxlint `--type-aware` clean at the version the lockfile pins,
`tsc --noEmit` + production build green, markdownlint clean on every doc touched, and
Chromium screenshots of the nested sidebar and of the canvas following a PR row —
`design.uiArtifacts.screenshotEvidence` requires them for a UI change.

## Documentation

- [`docs/capabilities/control-plane.md`](../../capabilities/control-plane.md) — the
  two-surfaces bullet now says the sidebar nests, a new bullet states the two-level rule
  (labels, treeless loops, the hash as the one source of truth for the viewed trace),
  and a history row records the change.
- [`ui/README.md`](https://github.com/MadaraUchiha-314/the-loop/blob/main/ui/README.md)
  — the screen description, the sidebar's row in the "where the screens get their data"
  table, and the routing note.
- No other user-facing doc describes the sidebar's structure.

## Decisions and open questions

No decision record was raised: nothing here changes a contract, a boundary or a
convention, and the two judgement calls are recorded where they belong — the
alternatives table in [`design.md`](design.md) (why not a count chip, why not
selected-item-only nesting, why not a collapse toggle) and the *Out of scope* section of
[`requirements.md`](requirements.md).

One question for the owner at the review gate: **collapse/expand was deliberately left
out.** Every board observed carries 1–3 PRs per item, so the list stays short and a
disclosure that always starts open and is never closed is a control that pays no rent.
If real boards grow deeper than that, the toggle is a small follow-up on this shape.
