---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#302"
phase: needs-review
status: in-progress
---

# Execution Log: a pull request appears once on the board

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-26 | — | Tier 3 (`human-approves-pr`): a join-layer defect in one screen plus a three-line correction in a derived read. Brainstorming skipped — the issue states the mechanism and names the candidate directions |
| requirements-definition | 2026-08-26 | | [`requirements.md`](requirements.md) — four requirements, three abuse cases; R1.4/R1.5 and R2.5 added during self-review |
| design | 2026-08-26 | | [`design.md`](design.md) — reconcile in the join, widen the liveness lookup; five alternatives recorded, including the issue's own second direction and why it was not taken |
| test-planning | 2026-08-26 | | [`testing-plan.md`](testing-plan.md) — twelve rows, eight of them applicable |
| tasks-breakdown | 2026-08-26 | | [`tasks.md`](tasks.md) — eight tasks |
| implementation | 2026-08-26 | | On `claude/github-issue-302-xgsd62` |
| verification | 2026-08-26 | | [`evidence/verification.md`](evidence/verification.md) — 183/183 UI, 2679/2679 service, both linters and the build clean, before/after screenshots captured |
| needs-review | 2026-08-26 | | PR raised; awaiting the owner |
| complete | | | |

## What was delivered

A labeled pull request has **two identities** on this machine, and the service writes both
on purpose: a portable record keyed by the PR's own ref (the poller's ledger, which is
what stops the next cycle re-reading its comments) and a session endpoint nested under the
work item it delivers (`link_pull_request`). `buildWorkItemViews` unioned the two sources'
refs and never asked whether a top-level ref was already somebody's pull request — so once
PR #301 began rendering `sessionTree`, one PR drew twice: live under its parent, and again
as a top-level shell with a grey dot, because its session is nested elsewhere.

- **The join reconciles the two identities.** A ref that another item's row draws as its
  pull request is not a top-level work item. The claim is refused — leaving the PR
  top-level — in four cases, each of which would otherwise make the fix worse than the
  bug: a **treeless** owner draws no nested rows at all, so the PR would vanish rather
  than move; a ref with a **session record of its own** was worked standalone before it
  was linked, so its own record is the live one and the nested endpoint is a stub with no
  tmux target (`record_owning` resolves it the same way); and a **self-claim** or a
  **two-level claim** is a hand-edited record's way of hiding a row. A PR no session
  claims — one linked to no issue — is untouched: that is the standalone-PR path
  `extract_work_items` exists for.
- **The drop moves information rather than deleting it.** The nested row now carries the
  PR's own portable record, so its age falls back to `poll.lastPolledAt` the way a work
  item's row already does; the PR's attention and its open `the-loop ask` question surface
  on the **owning** item's inbox card and `needs input` chip, named for the pull request —
  the precedent the `human gate · PR` entry already set. Nothing else is promoted: a PR's
  human gate never had a top-level row to lose, and adding it would be a new feature
  wearing a bug fix's clothes. The fold applies only where a row was actually removed.
- **`list_attention` looks for a session where a PR's session actually is.** Liveness was
  tested against top-level session records only, so every linked, labeled PR reported
  `armed-without-session` forever — the "dead" look the duplicate rows wore, and a false
  stall report in its own right. Three lines widen the lookup to nested endpoints; only
  `active`/`paused` count, and a ref's own record still wins.
- **The demo fixture gained the missing half of the real shape** — the PR's own poll
  ledger — so the bundled data reproduces what a real board produces, and the screens stop
  being evaluated against a shape no service serves.

No endpoint, request shape or response shape changed. `GET /api/v1/work-items` still
serves every portable record: the ledger for a PR is a legitimate record, and the client
is where the two sources are supposed to meet.

## Verification

Full results in [`evidence/verification.md`](evidence/verification.md): **171 → 183** UI
tests and **2677 → 2679** service tests, oxlint `--type-aware` + `tsc --noEmit` +
production build green, ruff + pyright + the full pytest suite green, markdownlint clean
on every doc touched, and before/after Chromium screenshots of the sidebar —
`design.uiArtifacts.screenshotEvidence` requires them for a UI change. Every new test was
run against the unfixed code first and fails there.

## Documentation

- [`docs/capabilities/control-plane.md`](../../capabilities/control-plane.md) — two new
  behaviour bullets (the one-row-per-PR rule with its four refusals and the fold; nested
  endpoints counting for liveness) and a history row.
- [`ui/README.md`](https://github.com/MadaraUchiha-314/the-loop/blob/main/ui/README.md) —
  the screen description and the sidebar's row in the "where the screens get their data"
  table.
- No other user-facing doc describes what the sidebar lists.

## Decisions and open questions

No decision record was raised: no contract, boundary or convention changed. The one
judgement call that could have gone the other way is recorded in
[`design.md`](design.md)'s alternatives table — **the issue's second suggested direction**
(persist PR-kind / parent on the portable record and filter `list_work_items`) was not
taken, because it copies a fact the session registry already owns into a second store that
can go stale, puts `core/workitems.py` in the business of reading the registry, and
changes what `GET /work-items` serves for every other client.

Two things for the owner at the review gate:

1. **A PR's `recent-error` no longer raises a chip anywhere**, only an inbox entry. Before
   this change its own top-level row wore the `error` chip. Promoting it to the work
   item's row was deliberately left out (R2.4) — the question is the only chip the removed
   row is *restored* to, everything else would be new reporting. Say the word and the
   error chip follows the same path.
2. **A PR that has a session record of its own still shows twice** (R1.4). That state is
   reachable only when a PR was worked standalone and then linked to an issue, and hiding
   its live session behind a stub endpoint would be a worse answer than an extra row. If
   real boards hit it, the fix belongs in the registry — collapsing the stub — rather than
   in the join.
