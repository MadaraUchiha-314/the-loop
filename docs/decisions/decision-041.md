# Decision 041: the paused label is a control only authorized logins hold — it writes the ledger, it is never read as state

- **Status:** proposed
- **Date:** 2026-07-26
- **Deciders:** @MadaraUchiha-314 (review of PR #100, issue #98)
- **Work item:** issue-98
- **Spec:** `docs/specs/issue-98/`
- **Extends:** [decision-023](decision-023.md) / `the_loop.authz` — the
  authorized-actor guard now covers the pause control, not just content events.

## Context

Review comment on PR #100: *"When someone adds/removes a label on a gh issue, do
we get to know who did that action? I want the github label addition and removal
only to be affected if the person is listed as approved set of people in the
cli-config.yaml."*

The first cut of issue-98 read the label as **state**: an item was paused while
`routing.pausedLabel` was on it, OR while a local ledger record existed. The
reasoning was fail-safe — a label can only make the-loop do *less*, so who
applied it seemed not to matter.

That reasoning holds for additions and **breaks for removals**. A presence check
cannot distinguish "the label is gone because an authorized operator lifted the
pause" from "the label is gone because anyone with triage rights deleted it", so
an unauthorized user could silently resume an agent on a work item the operator
had deliberately parked. Authorization for the *removal* direction is
unimplementable while presence is the source of truth.

**Can we even know who?** Yes:

| Path | Actor available | How |
|---|---|---|
| Webhook `issues`/`pull_request` with action `labeled`/`unlabeled` | yes, free | `label.name` + `sender.login` in the payload (already what `event_actor()` reads) |
| Any other webhook event | no | the payload carries the label *set*, never its authorship |
| Poll listing (`gh issue list --json labels`) | no | same — presence only |
| Poll, on demand | yes, one call | `GET /repos/{o}/{r}/issues/{n}/events` — `labeled`/`unlabeled` entries carry `actor.login` and `label.name`, and answer for PRs too |

## Decision

**The label is a trigger that writes the pause ledger. The ledger is the only
thing the gate reads.**

| Transition | Actor in `routing.authorizedUsers` | Effect |
|---|---|---|
| paused label added | yes | pause record written (`source: label`, `by: <login>`) |
| paused label added | no / unidentifiable | nothing; `pause.unauthorized` logged |
| paused label removed | yes | pause record cleared |
| paused label removed | no / unidentifiable | **nothing — the item stays paused** |

- **Webhook path**: the `labeled`/`unlabeled` event carries the actor, so the
  control costs no API call. (The router's existing authz guard already drops
  unauthorized events; the dispatcher re-checks rather than relying on it.)
- **Poll path**: the poller works by *disagreement* — label present but no
  record, or a `source: label` record with the label gone. Only then does it
  spend one `issues/{n}/events` call to ask who moved it. A refused answer is
  remembered so the next cycle does not re-ask.
- **An unidentifiable actor is treated as unauthorized.** A control gated on who
  acted must never act on an actor it could not name.
- `sessions pause`/`resume` are unchanged and still write `source: local`; they
  need no `gh` and no network.

## Consequences

### Good

- Both directions are authorized. Someone with triage rights can no longer
  un-pause work by deleting a label.
- One source of truth. The old OR semantics meant an item could be "paused by
  the label" and "paused locally" with no single record to inspect; now
  `sessions show` names the source and the login.
- The poll path pays for attribution only on a disagreement — normally zero
  extra API calls per cycle.

### Costs and risks

- **The label and the ledger can diverge**: an item may be paused with no label
  (unauthorized removal) or labelled but not paused (unauthorized addition). The
  ticket UI then misleads slightly. `sessions show` reports the truth, and
  `pause.unauthorized` records every refusal. Deliberately *not* re-asserting
  the label from the daemon — that is a write-loop risk against whoever keeps
  removing it.
- **Attribution can fail** (no `gh`, API error, an event too old to be returned).
  That fails closed on the label, which means someone's pause attempt silently
  does not take. Mitigated by a loud warning, the event-log record, and
  `sessions pause` always working locally.
- One extra API call per label disagreement on the poll path.
- `authorizedUsers` being empty now also disables the label control — consistent
  with every other guard in `the_loop.authz`, and already warned about at start.

## Alternatives considered

- **Keep presence-as-state (the pre-review behaviour)** — simplest, no API
  calls, but cannot authorize removals, which is the hole the reviewer asked to
  close.
- **Authorize additions only, keep reading presence** — half the fix; an
  unauthorized removal would still resume work, and the semantics ("who added it
  matters, who removed it doesn't") would be hard to explain.
- **Re-assert the label when the ledger and the ticket disagree** — keeps the UI
  honest, but a determined (or scripted) remover turns it into a write loop
  against the GitHub API. Rejected for now; the event log is the audit trail.
- **Resolve the actor for every event rather than on disagreement** — an API
  call per event per cycle, for information that only changes on a transition.
