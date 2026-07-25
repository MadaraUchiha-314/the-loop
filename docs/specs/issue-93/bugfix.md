---
type: bugfix
phase: requirements-definition
workItem: issue-93
status: approved
approvedBy: []
severity: high
collaborators: [engineer]
overrides: {}
---

# Bugfix spec: an event on a PR spawns a second session instead of reaching the linked issue's session

> Phase 1 of 3 for a bug (bugfix → design → tasks). Human approval for this
> tier-3 change happens at the PR (`autonomy.tiers."3": human-approves-pr`).

## Summary

A work item's session is registered against its **GitHub issue**
(`github:OWNER/REPO#<issue>`), and its PR is a *delivery vehicle* for that same
work item. When activity happens on the PR — most commonly a **conversation
comment** — the-loop is supposed to route it into the issue's existing session
(the live tmux session the operator is watching). Instead it frequently resolves
the event to the **PR's own ref** (`github:OWNER/REPO#<pr>`), finds no session
for it, and spawns a **second** session/tmux for the same work.

The operator sees two tmux sessions for one work item, the continuity of the
conversation is lost, and the fresh session re-derives context the original one
already had. Reported as
[issue #93](https://github.com/MadaraUchiha-314/the-loop/issues/93):

> the-loop's poller should first check for any linked gh issues first when
> reacting to an event on a PR … if there's existing gh issue linked to a PR and
> there's already an existing tmux session for it, then the-loop should reuse the
> tmux session and forward the events to the same session to ensure continuity

## Steps to reproduce

1. Run `the-loop poll start` (or `gh-webhook start`) with `routing.runner: tmux`
   and `spawnOnUnmatched: labeled`.
2. Work an item whose ticket is GitHub issue `#93`: a session is registered
   against `github:OWNER/REPO#93` and hosted in tmux session `loop-github-…-93`.
3. Open the PR for it (`#94`) and give it the auto-execute label — the supported
   "stay monitorable" step (`commands/work-on.md` §2).
4. Add a **conversation comment** on PR `#94`.

**Observed:** a second session is spawned and registered for
`github:OWNER/REPO#94` (a new `loop-github-…-94` tmux session), while
`loop-github-…-93` is still active.
**Expected:** the comment is delivered into the existing `#93` session.

The same happens without step 4 whenever the PR→issue link is one the-loop's
heuristics cannot see (see root cause 2) — a labelled PR is then treated as an
unrelated work item and spawns its own session on first sight.

## Expected vs actual

- **Expected:** WHEN an event concerns a PR, the-loop SHALL first resolve the
  GitHub issue(s) that PR is linked to, prefer them when matching a registered
  session, and (when no session exists at all) spawn against the **issue** — so
  one work item never has two sessions and the PR's events keep flowing into the
  session that has the context.
- **Actual:** PR-linkage is resolved only for `pull_request*` events, only from
  the head-branch naming convention and a narrow `Closes #N` body pattern; PR
  **conversation comments** (delivered by GitHub as `issue_comment`) resolve to
  the PR number alone; and an unmatched PR event spawns against the PR ref
  because the PR number is first in the extracted list.

## Root cause (confirmed)

Three defects in `cli/the_loop/webhook/router.py` — the single work-item
extraction both ingress paths share (`Dispatcher.handle` for webhooks,
`GitHubPollProvider.refs` for the poller):

1. **`issue_comment` on a PR is treated as a plain issue event.**
   `extract_work_items` branches on `event in ("issues", "issue_comment")` and
   adds only `payload["issue"]["number"]` (`router.py:150`). GitHub delivers a
   **PR conversation comment** as `issue_comment` with `payload["issue"]`
   carrying a `pull_request` key — so the comment resolves to
   `github:OWNER/REPO#<pr>` and nothing else. No session matches; with
   `spawnOnUnmatched: labeled` and the auto-execute label on the PR
   (`event_carries_label` reads `payload["issue"]["labels"]`, i.e. the PR's
   labels) `_on_unmatched` spawns a brand-new session. This is the reporter's
   exact scenario.

2. **PR→issue linkage is heuristic-only and misses GitHub's own linkage.** For
   `pull_request*` events the issue is derived from (a) `issue[-/](\d+)` in the
   head branch and (b) `\b(close[sd]?|fix…|resolve[sd]?)\s+#(\d+)` in the PR
   body (`router.py:25-30`). Neither sees an issue linked through GitHub's
   **Development panel** (`closingIssuesReferences`), and (b) misses the equally
   valid `Closes OWNER/REPO#93`, `Closes GH-93` and
   `Closes https://github.com/OWNER/REPO/issues/93` forms. A PR whose branch
   does not encode the number and whose body links the issue by URL resolves to
   no issue at all, so `Poller._process_item`'s
   `has_session = any(registry.find_by_work_item(wi) …)` is False for every ref
   and `_try_spawn` fires.

3. **An unmatched PR event spawns against the PR, not the issue.**
   `Dispatcher._on_unmatched` spawns for `routed.work_items[0]`
   (`dispatcher.py:523`) and `extract_work_items` appends the PR number
   *before* the linked issue — so even when the linkage *is* resolved, a
   from-scratch spawn keys the new session to the PR ref rather than the work
   item's ticket.

## Acceptance criteria (EARS)

### Resolve the PR's linked issues (both ingress paths)

1. WHEN an event concerns a pull request (`pull_request`,
   `pull_request_review`, `pull_request_review_comment`, **or** an
   `issues`/`issue_comment` event whose `issue` carries a `pull_request` key)
   THEN the system SHALL resolve the GitHub issue(s) that PR is linked to and
   include them in the event's work items. (AC1)
2. WHEN a PR carries GitHub's own linked-issue references
   (`closingIssuesReferences`, i.e. the Development panel) THEN the system SHALL
   treat them as authoritative linked issues, in addition to the existing
   head-branch (`issue-<n>`) and closing-keyword conventions. (AC2)
3. WHEN a PR body links its issue as `OWNER/REPO#N`, `GH-N`, `Fixes: #N` or a
   full issue URL THEN the system SHALL recognise it, and WHEN the reference
   names a **different** repository THEN the system SHALL NOT treat it as a work
   item of the event's repository. (AC3)

### Reuse the existing session (continuity)

1. WHEN an event on a PR is resolved to a linked issue AND an **active session
   exists for that issue** THEN the system SHALL deliver the event into that
   session (reusing its tmux session) and SHALL NOT spawn a new session for the
   PR's own ref. (AC4)
2. WHEN an event on a PR is resolved to a linked issue AND **no** session exists
   for any of the event's work items AND the spawn policy allows spawning THEN
   the system SHALL spawn the session against the **linked issue's** ref, not
   the PR's. (AC5)
3. WHEN a PR is linked to **no** GitHub issue THEN the system SHALL keep today's
   behaviour and route it as its own work item
   (`github:OWNER/REPO#<pr-number>`) — the supported path for non-GitHub
   ticketing (Jira, …). (AC6)

### Poll path

1. WHEN the poller lists a labelled PR THEN it SHALL fetch that PR's linked
   issues from GitHub in the **same** `gh` call it already makes (no extra API
   round-trip per cycle), and WHEN the installed `gh` is too old to support the
   `closingIssuesReferences` JSON field THEN the poller SHALL degrade to the
   existing conventions with a warning rather than failing the poll cycle. (AC7)

### Regression coverage

1. The fix SHALL include regression tests that fail before it and pass after,
   covering a PR conversation comment reaching the linked issue's session on
   **both** the webhook and the poll path. (AC8)

## Out of scope

- **Retro-merging sessions that already diverged.** If a duplicate session was
  already spawned before this fix, both records remain; the operator closes the
  stray one (`the-loop sessions close`). Detecting and merging two live sessions
  for one work item is a separate concern.
- **Re-keying an existing registration.** A session deliberately registered
  against a PR ref (the Jira flow, AC6) keeps that ref; this change only decides
  which ref an *event* resolves to and which ref a *new* spawn uses.
- **Non-GitHub linkage** (a Jira ticket referenced in a PR body). The poll
  provider contract stays provider-agnostic; only the GitHub provider learns
  about `closingIssuesReferences`.
- **Cross-repository work items.** A closing reference to another repository is
  explicitly ignored (AC3) rather than routed.

## Security considerations

**No new attack surface; one narrowing.** The change alters *which work item ref*
an already-authorized event resolves to — it adds no new ingress, no new
credential, and no new command. Specifically:

- **Untrusted input, unchanged handling.** PR body text and
  `closingIssuesReferences` come from the same webhook payload / `gh` JSON the
  router already parses. They are used only to produce **integers** (issue
  numbers) that are formatted into a `WorkItemRef`; nothing is interpolated into
  a shell command, a path, or a prompt instruction. The payload continues to be
  embedded in the harness prompt framed as untrusted data.
- **Order of guards unchanged.** The authorized-actor guard
  (`routing.authorizedUsers`) and the self-reply marker guard both run on the
  event *before* work-item extraction is acted on; a hostile commenter still
  cannot get any event dispatched.
- **A hostile PR body cannot hijack an unrelated session** *in a new way*: it
  could already claim `Closes #<n>` today. The cross-repo qualifier check (AC3)
  makes this strictly **narrower** than today — a reference naming another
  repository is now dropped instead of being read as this repo's issue number.
  Within a repository, the actor writing the body must already be authorized.
- **Fail-closed degradation.** An unreadable/unsupported `closingIssuesReferences`
  field degrades to the existing conventions (AC7); it never widens routing and
  never aborts a poll cycle.
- **Bounded work.** Resolution is pure parsing over payload fields already in
  memory; no new network calls, no unbounded loops (matches are deduplicated
  into the existing ordered number list).

## Open questions

None. The reporter's ask is explicit (check linked issues first; reuse the
existing session). Ordering linked-issues-before-PR is the mechanism that
satisfies both "reuse" (AC4) and "spawn against the issue" (AC5) with one
change, and AC6 preserves the documented PR-as-work-item path.
