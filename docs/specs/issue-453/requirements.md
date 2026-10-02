---
type: requirements
phase: requirements-definition
workItem: "github:MadaraUchiha-314/the-loop#453"
status: in-review
approvedBy: []
collaborators: [architect, engineer, security-reviewer]
overrides: {}
riskTier: 3                  # the ownership rule behind every lifecycle verb changes; no credential, no config key, no schema
---

<!-- Authored per the the-loop:writing skill. -->

# Requirements: a parked work item is owned by the instance that accepted it

> Phase 1 of 3 (requirements → design → tasks). Tier 3 (`human-approves-pr`): the rule
> that authorizes `ticket close`, `pr create`, `pr merge` and `pr resolve-thread` gains a
> second source of ownership. No credential, configuration key or schema changes.

## Introduction

[Issue #453](https://github.com/MadaraUchiha-314/the-loop/issues/453) follows
[#447](https://github.com/MadaraUchiha-314/the-loop/issues/447) and
[#450](https://github.com/MadaraUchiha-314/the-loop/issues/450).

**What is broken.** `the-loop sessions start --work-item <ref>` can accept a work item
and park it at its first human gate without launching a harness session (issue-358: the
daemon services `phase-selection` itself). The control record says `start_requested`
and the CLI reports `waiting`. That accepted item cannot then be closed through
`the-loop ticket close`, because the lifecycle guard decision-140 D8 established
recognises only a **session-backed** registration: a live session record for the ref, a
live session recording the ref as its pull request, or an ad-hoc `the-loop do` work item
naming it. A parked item has none of these. The operator falls back to `gh`, then runs
`the-loop sessions stop` by hand to disarm the start, as the issue's reproduction on
[the-loop-testing#5](https://github.com/MadaraUchiha-314/the-loop-testing/issues/5)
records.

**What this changes.** The instance that accepted a work item owns it from the moment it
recorded the acceptance, not from the moment a session exists. Ownership is read off the
record the instance already writes — the `control` section of the work item's portable
record, stamped with the instance's name (issue-322) — so nothing new is invented and no
session is spawned merely to register. Closing a parked item through the-loop also
cancels its pending start, so the close is complete in one act.

## Requirements

### Requirement 1 — an accepted, parked work item is owned by the instance

**User story:** As the operator of a the-loop instance, I want a work item this instance
accepted (armed and parked at a human gate) to count as this instance's, so the lifecycle
verbs act on it without a harness session having to exist first.

#### Acceptance criteria (EARS)

1.1 WHEN a work item's control record on this instance holds a command this instance
recorded (the record's `instance` is this instance's name — the empty name for an unnamed
instance) AND the record is not stamped `ended` THEN the lifecycle guard SHALL treat the
work item as registered on this instance, exactly as a live session record does.

1.2 The system SHALL NOT create a harness session, a tmux session, a session record or any
other artefact to represent that ownership: the control record the arming already wrote
is the representation.

1.3 Ownership read from a control record SHALL grant authority over the work item the
record names only. It SHALL NOT extend to any pull request, because a parked item has
recorded none.

### Requirement 2 — the operator closes or cancels a parked item through the-loop

**User story:** As the operator, I want `the-loop ticket close <ref> [--reason
not_planned]` — and the same operation over the control-plane route and the MCP tool — to
close an item this instance parked, so I never have to reach for `gh`.

#### Acceptance criteria (EARS)

2.1 WHEN `ticket close` is run for a work item owned through its control record THEN the
system SHALL close the ticket on GitHub with the given `state_reason` and exit 0.

2.2 WHEN the close succeeds AND the work item has no live session AND its control record
still requests a start THEN the system SHALL record a `stop` on the work item (source
`cli`, this instance's name), so the daemon's spawn gate reads it as **not** armed; it
SHALL forget the `work_item_start` hook mark with it, as a stop by comment does.

2.3 WHEN a start was cancelled by a close THEN the result SHALL say so (`startCancelled:
true` in the data and a line of output), and the event log SHALL carry a
`control.command` record for the stop with `effect: start-cancelled`.

2.4 WHEN the close is run again for the same work item THEN the system SHALL close the
ticket again (GitHub's no-op), exit 0, and leave the control record as it is: the
operation is idempotent.

2.5 WHEN a labelled or control-start event for the work item reaches the dispatcher after
such a close THEN the system SHALL NOT spawn a harness session for it.

2.6 A session-backed work item SHALL close exactly as it does today; its local closure
remains the daemon's, on the `closed` event (issue-329).

### Requirement 3 — nothing else is granted

**User story:** As the owner of the lifecycle guard, I want its refusals kept: a ref this
instance does not track is still refused, and a record this instance did not write grants
nothing.

#### Acceptance criteria (EARS)

3.1 WHEN the target has no session record, no owning session, no ad-hoc work item naming
it and no control record THEN the system SHALL refuse the act with the existing message,
and send nothing.

3.2 WHEN the target's control record was stamped by another instance (its `instance`
differs from this instance's name, including a named record on an unnamed instance and an
unnamed record on a named instance) THEN the system SHALL refuse the act.

3.3 WHEN the target's portable record is stamped `ended` THEN its control record SHALL
grant nothing: the item is over, and the daemon has already forgotten its arming.

3.4 WHEN the control record is unreadable THEN it SHALL grant nothing (fail closed).

## Non-functional requirements

- **No new I/O class.** The guard already opens the registry; it now also reads the
  portable record through the `ControlStore` the same module already uses for the ad-hoc
  check. One more small-file read per lifecycle act, only when the registry said no.
- **One rule, every surface.** The CLI, the `POST /work-items/tickets/close` route and the
  `close_ticket` MCP tool share `core.github_ops.close_ticket`; nothing is duplicated.
- **Documentation.** `docs/cli/commands/ticket.md`, `docs/capabilities/cli.md` and a
  decision refining decision-140 D8 say what owns a work item now.

## Security considerations

- **Actors & trust:** untrusted — anyone who can comment on a ticket, and any file a
  reader could plant that *looks* like a portable record; trusted — this instance's own
  state directory (`<state.root>/portable/`), written by `the-loop sessions start`
  and by the daemon on an **authorized** comment; the operator's shell or service access,
  which is already the authority behind every control verb.
- **Trust boundary:** `core.github_ops._authority`. It reads two stores the instance
  owns and nothing from GitHub. A control record grants authority only when its
  `instance` is this instance's name as the CLI config declares it; the name is never
  read off the record and trusted back.
- **Data:** no secrets. A control record holds a ref, a command, an actor login and a
  timestamp.
- **Abuse cases (EARS):**
  1. WHEN a record for an unrelated ref is planted in the portable directory with
     another instance's name THEN the system SHALL refuse the act (3.2).
  2. WHEN a record carries no instance name on a named instance THEN the system SHALL
     refuse: an unnamed record is not this instance's (3.2).
  3. WHEN the `ended` stamp exists THEN a surviving or re-planted control record SHALL
     not revive authority (3.3).
  4. WHEN a parked item is closed THEN no later event SHALL spawn a session for it
     (2.5): closure cannot become a launch.
- **Fail closed:** every unreadable or mismatched record resolves to "not owned", which
  is today's refusal.

## Out of scope

- Closing through the daemon's `closed`-event path for a session-backed item: unchanged.
- A config-declared `instance.scope.workItems` entry as a source of lifecycle authority.
  Declaring is not accepting; the issue asks for accepted items.
- Any change to `sessions start`'s parking behaviour (issue-358, issue-450).
