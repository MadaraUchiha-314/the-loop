---
type: requirements
phase: requirements-definition
workItem: issue-101
status: approved
approvedBy: []
collaborators: [engineer]
overrides: {}
---

# Requirements: one work item may be delivered by several PRs

> Phase 1 of 3 (requirements → design → tasks). Human approval for this tier-3
> change happens at the PR (`autonomy.tiers."3": human-approves-pr`).

## Introduction

[Issue #101](https://github.com/MadaraUchiha-314/the-loop/issues/101):

> - make sure the-loop when it's tracking linked PRs to a work item can track a
>   "list" of those items rather than a single item
> - just check if it's already the case, if it's already the case, there's
>   nothing to do, else implement it.

A work item (GitHub issue / Jira ticket) is frequently delivered by **more than
one** pull request: a spec-only PR followed by an implementation PR, a stacked
series, a follow-up fix after review, or a change that spans repositories. The
loop is the unit of work; a PR is one *delivery vehicle* for it.

The audit below (Requirement 0) found the **event → work-item direction already
list-shaped** (a PR resolves to *all* the issues it is linked to — issue-93), but
the **work-item → PR direction assumes exactly one PR**: the first PR that closes
or merges ends the work item's session and deletes its checkout, even when the
ticket is still open and further PRs are in flight.

## Requirement 0 — Audit: where the single-PR assumption lives

**User story:** As the operator, I want to know exactly which parts of the-loop
already handle a list of PRs per work item, so that only the parts that don't are
changed.

### Findings

| # | Site | List-shaped today? |
|---|------|--------------------|
| A | `webhook/router.py::linked_issue_numbers` / `extract_work_items` | **Yes** — a PR resolves to *every* issue it links (`closingIssuesReferences` + branch + closing keywords), each becoming a `WorkItemRef` |
| B | `sessions/registry.py` | **Yes (neutral)** — refs are independent files; N PR refs and an issue ref coexist. It stores sessions, never "the PR" of an item |
| C | `poller/poller.py::_poll_provider` | **Yes** — `open_refs` unions **all** of each listed item's refs, so an issue stays "open" while any of its labelled PRs is listed |
| D | `poller/poller.py::_reconcile_closures` | **Yes** — registry-driven and per-ref: a session is closed only when **its own** ref is confirmed ended upstream, so another PR merging never ends it |
| E | `poller/github.py::closure_event` | **Yes** — `work_items=[ref]`, scoped to the ref that actually ended |
| F | `webhook/dispatcher.py::handle` (close path) | **No** — a `pull_request`/`closed` event closes **every** matched session, including one registered against a *linked issue* that is still open with other PRs in flight |
| G | `webhook/dispatcher.py::_cleanup_workspace` | **No** — consequence of F: the **work item's** worktree is deleted when any one of its PRs closes |
| H | Guidance (`commands/`, `skills/the-loop/reference/`, `docs/capabilities/`, `cli/README.md`) | **No** — written throughout as "**the** PR" of a work item, and "PR merge/close auto-closes the session" is stated as the work item's end condition |
| I | `skills/the-loop/templates/execution-log.md` | **No** — the per-work-item record has no place to list the PRs delivering it |

So: **F–I need implementing; A–E are already correct and MUST NOT regress.**

## Requirement 1 — A PR closing does not end a work item that is still open

**User story:** As an operator running the-loop's daemon, I want a work item's
session to survive one of its PRs merging, so that a multi-PR work item keeps its
session, its tmux transcript and its checkout until the *ticket* is done.

### Acceptance criteria (EARS)

1. WHEN a `pull_request` `closed` event (merged or not) is dispatched THEN the
   system SHALL auto-close only the session(s) registered against **that PR's own
   ref**, and SHALL NOT close a session registered against an issue the PR is
   merely linked to. (AC1)
2. WHEN a work item's ticket ends — an `issues` `closed` event, or the poll path's
   closure reconciliation confirming the item closed upstream — THEN the system
   SHALL auto-close its session exactly as today. (AC2)
3. WHEN a PR that is linked to an issue closes AND a session is registered
   against that issue THEN the system SHALL leave that session `active` and SHALL
   NOT deliver the close event into the harness conversation (a close is a
   lifecycle signal, never a prompt — unchanged from issue-94). (AC3)
4. WHEN a labelled PR carrying **no** linked issue closes THEN the system SHALL
   auto-close the session registered against that PR's ref — the non-GitHub
   ticketing path (Jira, …) is unaffected. (AC4)
5. WHEN a session is auto-closed THEN the `session.autoclosed` event SHALL keep
   naming the reason (`issue-closed` | `pr-merged` | `pr-closed`), and WHEN a
   close event matches only linked-issue sessions THEN the system SHALL log that
   the work item was left open (with the PR ref) rather than silently doing
   nothing. (AC5)

## Requirement 2 — A work item's checkout outlives a single PR

**User story:** As an operator using `routing.workspace`, I want the work item's
checkout to survive one of its PRs closing, so that the next PR in the series is
not written from a deleted worktree.

### Acceptance criteria (EARS)

1. WHEN a PR closes AND the session registered against the linked issue is left
   open (AC1) THEN the system SHALL NOT remove that work item's checkout. (AC6)
2. WHEN the session that is auto-closed *is* the closing PR's own session THEN
   workspace cleanup SHALL run exactly as today (subject to
   `keepCheckoutOnClose`). (AC7)

## Requirement 3 — The loop's guidance treats PRs as a list

**User story:** As an agent (or human) working an item under the-loop, I want the
operating model to say a work item may have several PRs, so that I label and
track every one of them instead of assuming the first is the last.

### Acceptance criteria (EARS)

1. WHEN a work item is delivered by more than one PR THEN the loop's guidance
   SHALL instruct the agent to add the auto-execute label to **each** PR (so each
   PR's activity routes back to the work item's session) and to record **all** of
   them in the work item's execution log. (AC8)
2. The execution-log template SHALL carry a **Pull requests** section that is a
   *list* (one row per PR, with its status and the tasks/scope it delivers), and
   `finish-tasks` SHALL verify that every listed PR is merged or closed before
   marking the work item complete. (AC9)
3. The capability docs, `reference/automation.md` and `cli/README.md` SHALL state
   the corrected end condition — a work item's session ends when the **work item**
   ends, not when one of its PRs does — and SHALL note the operational
   consequence: a session whose PR merged without closing the ticket stays active
   until the ticket closes. (AC10)

## Non-functional requirements

- **No new API calls.** The close decision SHALL remain payload-only, so the
  webhook path keeps working with no GitHub credentials and no per-event
  round-trip (a PR-close payload cannot tell whether the linked issue is still
  open, so the rule must be decidable from the refs alone).
- **Both ingress paths identical.** Webhook and poll SHALL reach the same
  outcome; the poll path is already correct (finding D/E) and SHALL be covered by
  a regression test rather than changed.
- **Observability.** Every close/non-close decision stays visible in the event
  log (`session.autoclosed`, plus the new "left open" log line).

## Security considerations

**No new attack surface; one narrowing.** The change removes an auto-close path;
it adds no ingress, credential, command, network call or parsed field.

- **Actors & trust:** unchanged. The close path is reached only by an `issues` /
  `pull_request` `closed` event that already passed HMAC verification (webhook) or
  came from the operator's own `gh` (poll).
- **Trust boundaries & data:** the decision reads `routed.work_items` (integers
  already extracted upstream) and the session's own registered ref. No untrusted
  text is newly interpreted, and close events continue to be **never** rendered
  into a harness prompt (AC3).
- **Abuse cases (EARS):**
  1. WHEN a hostile actor opens and closes a PR whose body claims `Closes #N`
     THEN the system SHALL NOT close the session for `#N` — previously this was
     the documented (and only) way to end another work item's session from a PR;
     the change makes that impossible. This is why the lifecycle-close bypass of
     the authorized-actor guard (issue-94) becomes strictly safer: the bypass now
     only ever ends the session for the *very object* that closed.
  2. WHEN a close event names a work item with no registered session THEN the
     system SHALL continue to do nothing and SHALL never spawn (unchanged).
- **Fail closed:** under doubt the session is now **left running** rather than
  closed. The failure mode moves from "a live work item loses its session and
  checkout" (data loss, unrecoverable transcript) to "a finished work item may
  keep an idle session until its ticket closes" (recoverable:
  `the-loop sessions close`). The safer default is the one that keeps state.

## Out of scope

- **Asking GitHub whether the linked issue is still open** on a PR close. That
  would make the webhook path depend on credentials and add a per-event API call;
  the ticket's own `closed` event (and poll reconciliation) already answers it.
- **A config knob for the old behaviour.** The old behaviour is wrong for
  multi-PR items and equivalent for single-PR ones whenever the PR closes its
  issue (`Closes #N` → the `issues` `closed` event follows within moments). Per
  the minimalism ladder, no new option is introduced.
- **One session per PR / splitting a work item across sessions.** The work item
  remains the unit of session identity (decision-036); this change is only about
  when that session *ends*.
- **A worktree per PR.** The work item's single checkout is unchanged; the
  harness switches branches within it as the PR series progresses.
- **Retro-closing sessions** already left active by previous behaviour, or
  reopening ones it closed early — the operator uses `the-loop sessions`.

## Open questions

None. The issue's instruction is explicit ("check if it's already the case …
else implement it"); Requirement 0 is that check, and Requirements 1–3 cover the
sites where it was not.
