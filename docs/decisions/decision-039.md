# Decision 039: a PR closing ends only its own session — a work item may have several PRs

- **Status:** proposed
- **Date:** 2026-07-25
- **Deciders:** @MadaraUchiha-314 (issue #101)
- **Work item:** issue-101
- **Spec:** `docs/specs/issue-101/`
- **Refines:** [decision-036](decision-036.md) (a PR event routes to its linked
  issue first) — the routing direction is unchanged; this decides what a *close*
  on that route means.

## Context

Issue #101: *"make sure the-loop when it's tracking linked PRs to a work item can
track a 'list' of those items rather than a single item."*

A work item is regularly delivered by more than one PR: a spec PR then an
implementation PR, a stacked series, a follow-up fix after review, or one PR per
repository. The event → work-item direction has been list-shaped since
decision-036 (a PR resolves to *every* issue it links), and the poll path's
closure reconciliation is per-ref: it asks whether **the session's own item**
ended.

The webhook close path was not. `Dispatcher.handle` treated a `pull_request`
`closed` event as "the work item ended" and closed **every** session it matched —
including the session registered against the *linked issue*. So the first PR of a
series merging closed the work item's session, terminated its tmux harness and
deleted its checkout, while the ticket was still open and the next PR was still to
be written. The transcript of a live work item was lost to a routine merge.

The constraint that shapes the fix: the webhook path is deliberately
**payload-only** (no GitHub credentials, no per-event API call), and a PR-close
payload does not say whether the linked issue is still open.

## Decision

**A close event ends only the session registered against the object that
actually closed.**

- `issues` `closed` → the session for that issue (unchanged).
- `pull_request` `closed` (merged or not) → the session for **that PR's own ref**.
  A session registered against an issue the PR is merely *linked* to is left
  `active`, logged and recorded as `session.kept_open`.

The closing ref is derived from `RoutedEvent.work_items` by matching the number
the payload's own entity carries — data the router already extracted — so the
decision stays payload-only and provider-agnostic. A payload that names no number
closes nothing.

Everything else about the close branch is unchanged: a close never spawns, is
never rendered into a harness prompt, and keeps bypassing the authorized-actor
guard as a lifecycle signal. Workspace cleanup and tmux handling run per closed
session, so the work item's checkout now outlives any single PR without a second
change.

The loop's own guidance follows: every PR of a work item is labelled and listed in
the execution log's new **Pull requests** table, and `finish-tasks` requires all of
them to be merged/closed before completing the item.

## Consequences

- A multi-PR work item keeps one session, one tmux transcript and one checkout for
  its whole life; the next PR in a series is written from the same worktree.
- The end condition moves from "a PR merged" to "the work item closed". With the
  usual `Closes #N` body this is the same moment plus one webhook hop, because
  GitHub closes the issue on merge and fires `issues` `closed`.
- **A PR that merges without closing its ticket leaves the session active** until
  the ticket closes. `/the-loop:finish-tasks` closes the ticket; `the-loop
  sessions close` is the manual escape hatch. This is the accepted cost: an idle
  session is recoverable, a deleted worktree and a killed harness are not.
- Operators who narrow `webhooks.ghWebhook.events` and drop `issues` now leak
  sessions for GitHub-ticketed items. The receiver's existing startup / hot-reload
  warning for that exact omission covers it.
- The lifecycle-close bypass of the authorized-actor guard becomes strictly safer:
  a hostile `Closes #N` in a PR body can no longer end `#N`'s session, because a
  close only ever ends the session for the object that closed.
- The poll path needed no change — evidence that the provider contract
  (`owns`/`closure`/`closure_event`, issue-94) was already scoped correctly.

## Alternatives considered

- **Ask GitHub whether the linked issue is still open on each PR close.** Correct
  in principle and marginally faster to close finished items, but it puts a
  credentialed API round-trip on a path that is deliberately zero-API, and buys
  only latency: the ticket's own close event arrives moments later anyway.
- **A config flag to keep the old behaviour.** Preserves a default that loses
  state on multi-PR items, and the two behaviours coincide whenever the PR closes
  its issue. Rejected per the minimalism ladder (`config.minimalism`).
- **Store a `linkedPRs` list on the session record.** Needs a write on every PR
  open/close and drifts from GitHub's own linkage; the list is already derivable
  from the PR side on every event, which is why the fix needed no new data.
- **Close the issue's session only when the closing PR is the *last* open one.**
  Same API-call objection as the first alternative, plus a race: "last open PR" is
  not knowable from the payload, and guessing wrong deletes the checkout.
