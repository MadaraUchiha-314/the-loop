---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#283"
phase: needs-review
status: in-progress
---

# Execution Log: control-plane UI audit — implement the whole of issue-283

> Append-only log of progress for the user's visibility.

## Process note

The audit ([#283](https://github.com/MadaraUchiha-314/the-loop/issues/283)) was first
triaged into per-item tickets (#284–#296) per the operating model; the owner then
directed, on the session thread, that the entire audit be implemented at once. This
work item therefore carries the implementation of every audit finding in one PR, at
the owner's explicit instruction, in place of the per-ticket spec chains. The
sub-tickets remain as the itemized record of what this delivers.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| implementation | 2026-08-25 | @MadaraUchiha-314 (direct instruction) | Whole-audit implementation on `claude/github-issue-283-4nt97c`. |
| verification | 2026-08-25 |  | See Verification below. |
| needs-review |  |  |  |
| complete |  |  |  |

## What was delivered

**Service (Python, `cli/`):**

- B1 — the poller caches each ticket's `title` in the portable record's poll section
  (`PollState.baseline_comments`/`finalize`), served verbatim by `/api/v1/work-items`.
- B5 / feature #10 — `core.attention` ages `recent-error` out after
  `RECENT_ERROR_MAX_AGE_HOURS` (24h) and clears a `poll.*` error once the item's
  `poll.lastPolledAt` is newer (a failed item skips that stamp, so the signal is
  sound); entries carry `at` so clients render age.
- B7 — `api.request` demoted to debug level in the router's route class.

**UI (`ui/`):**

- Bloat #1 / features #2 #3 #5 #6 #7 — three-pane redesign: Work · Events · Settings.
  Persistent sidebar (deduped tiered inbox with in-place gate Approve and question
  Reply; items grouped needs-you/running/idle; standing sessions under a divider),
  main pane = the item detail (rail, readable transcript, chat bar) or the full inbox.
  Legacy hashes (`#/dashboard`, `#/attention`, `#/sessions[/ref]`) still land.
- B3/B4/B6 — `attentionEntries` dedupes per (ref, kind) with a ×N count and tiers
  needs-input > gate > waits > errors, newest first within a tier; nav badge counts
  work items needing a human; the strip/inbox inherit it.
- B10 / feature #8 — one health dot + popover (stream state from the board's one
  `useStream`, daemon last-cycles, manual refresh) replaces the three header chips.
- B11 — sidebar rows show the frozen rail's progress (`planned · 0/9`) instead of
  "no graph state"; the detail rail already rendered it.
- B12 — relative time everywhere with the absolute stamp on hover; trace stamps
  include the date when not from today (`timeOf`).
- B13 — session dots are round; "no session" renders as a dash.
- B2 — the table that collapsed is gone; the sidebar rows that replaced it use
  nowrap/ellipsis throughout.
- B8/B9 — the detail pane's event-trail section renders only when a real transcript
  is shown, and the no-transcript fallback is two sentences on two lines.
- B7 UI / feature #4 — Events hides `api.request`/`mcp.call` unless asked, adds an
  event-namespace filter, a work-item filter with permalink (`#/events/<ref>`) and a
  live tail.
- Feature #9 — `fetchGraphs` answers dormant loops (session neither active nor
  paused) from the held report; items with no checkout were already skipped.
- Bloat #2/#3/#4/#5 — provenance notes and the route footer removed; Settings prose
  behind "Learn more" disclosures with a base-URL input wide enough for its value;
  blueprint corner marks and all-caps headings retired for sentence case.

## Verification

| Activity | Command | Outcome |
|---|---|---|
| Python unit + integration | `uv run pytest` (cli/) | 2677 passed, 1 skipped |
| New service behaviour | `tests/test_core_attention.py` (age-out, clean-poll clear), `tests/test_poller.py` (title caching) | pass |
| UI unit + React | `npx vitest run` | 168 passed (12 files) |
| UI typecheck | `tsc --noEmit` | clean |
| UI lint | `oxlint --type-aware` | the 6 pre-existing findings on `main`; none added |
| UI build | `vite build` | clean |
| Visual | Playwright over the built bundle in demo mode | [evidence/](evidence/) — overview, item, events, settings, standing |

## Documentation

- `docs/capabilities/control-plane.md` — redesigned-dashboard behaviour + history row.
- `docs/cli/state.md` — the poll section's `title` field.
- `docs/cli/service.md` — `api.request` at debug level.
- `ui/README.md` — the three-screen layout and per-surface reads.
