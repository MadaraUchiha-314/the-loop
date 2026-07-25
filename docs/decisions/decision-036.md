# Decision 036: an event on a PR routes to the PR's linked issue first

- **Status:** accepted
- **Date:** 2026-07-25
- **Deciders:** @MadaraUchiha-314 (issue #93)
- **Work item:** issue-93

## Context

A work item's session is registered against its **GitHub issue**; the PR is the
vehicle that delivers it. When something happened on the PR, the-loop resolved the
event to whichever work items `extract_work_items` could see — and for a PR
**conversation comment** (which GitHub delivers as an `issue_comment` whose `issue`
object carries a `pull_request` key) that was only the PR's own number. With
`spawnOnUnmatched: labeled` and the auto-execute label on the PR, that unmatched event
spawned a **second** session and a second tmux window for a work item that already had
a live one, breaking the continuity the operator was watching (issue #93).

Linkage discovery was also weaker than GitHub's own: only `issue-<n>` in the head
branch and a bare `Closes #N` in the body. An issue linked through GitHub's
**Development panel**, or written as `Closes OWNER/REPO#N` / `GH-N` / a full issue URL,
was invisible — so even `pull_request` events could look unrelated to their ticket.

Two forces pull against each other: the issue is the work item (continuity argues for
routing there), but decision-016's PR-as-work-item path (`work-on` labels the PR
directly when the ticket lives in Jira) must keep working — a PR with no GitHub issue
*is* its own work item.

## Decision

**`extract_work_items` resolves a PR's linked issues and emits them *before* the PR's
own number**, for every PR-shaped event — including an `issues`/`issue_comment` event
whose `issue` carries a `pull_request` key. Linked issues come from three sources, most
authoritative first: GitHub's `closingIssuesReferences` (the Development panel), the
`issue-<n>` head-branch convention, and closing keywords in the PR body in every form
GitHub accepts (`#N`, `OWNER/REPO#N`, `GH-N`, an issue URL) — a qualified reference
naming a *different* repository is ignored.

Ordering is the whole mechanism. `Dispatcher.handle` already matches every work item, so
the issue's session is found and reused; `_on_unmatched` already spawns for
`work_items[0]`, so a from-scratch spawn now keys to the issue; `Poller._process_item`
already computes `has_session` across the refs, so the poll path inherits it. The poller
asks `gh` for `closingIssuesReferences` inside the PR listing it already performs (no
extra API call), degrading to the conventions with a warning on a `gh` too old to know
the field.

A PR linked to **no** GitHub issue keeps routing as its own work item — decision-016's
Jira path is unchanged.

## Consequences

- One work item has one session again: PR comments, reviews and CI results all land in
  the session that holds the context, and the tmux session the operator attached to
  stays the one that keeps working.
- Where the linkage exists, the *issue* becomes the identity of the work — spawns,
  registry entries and tmux target names key to the ticket rather than to the PR.
- Routing is now as good as GitHub's own linkage rather than a naming convention, so
  branches that don't encode the issue number are fully supported.
- Cross-repository closing references are no longer mis-read as this repository's issue
  numbers (a narrowing, not a widening).
- A session deliberately registered against a PR ref before this change is not re-keyed;
  if both a PR-ref and an issue-ref session exist, both receive the event and the
  operator closes the stray one.
- The poll path depends on a recent-enough `gh` for the strongest source; older
  binaries silently keep today's behaviour plus a one-time warning.

## Alternatives considered

- **Keep the PR first and teach the dispatcher to prefer an issue when spawning.** Needs
  a second notion of "which of these is the ticket" inside the dispatcher, and does
  nothing for the poller's own `has_session` check, which calls `provider.refs`.
- **Resolve the linkage with a dedicated `gh pr view` call per event.** An extra API
  round-trip per PR per poll cycle, and unusable on the webhook path, which is
  deliberately zero-API (`event_carries_label` reads labels straight from the payload).
- **Re-key an existing PR-ref session onto the issue once a link appears.** Would break
  the deliberate Jira flow, where the PR ref *is* the work item's identity.
