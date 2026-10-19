---
type: requirements
phase: requirements-definition
workItem: "github:MadaraUchiha-314/the-loop#340"
status: in-review            # draft | in-review | approved — tier 4: a named security sign-off is also needed
approvedBy: []
collaborators: [engineer]
overrides: {}
riskTier: 4                  # touches a schema file (cli-config.schema.json); no credential, no new write to a ticket
---

<!-- Authored per the the-loop:writing skill. -->

# Requirements: progress reports during long-running sessions

> Phase 1 of 4 (requirements → design → testing plan → tasks). Part 1 of 2: the verb,
> the event, the label gate, the rate limit and the Slack line. Part 2 (the silent-session
> watchdog, the issue's "nice to have") is specified at the end and ships in its own PR.

## Introduction

[Issue #340](https://github.com/MadaraUchiha-314/the-loop/issues/340): "Progress reports
during long-running sessions, opt-in per work item via a GitHub label."

**What is missing.** Every event the-loop publishes fires at a boundary: a gate, a block, a
question, the end. None fires during work. A session that runs for two hours is silent, and
a person on a phone cannot tell hard work from a stuck loop from a dead poller. The one
mid-flight signal, `the-loop ask`, *blocks* the session until a human answers, so it is the
wrong tool for "here is where I am".

**What this changes.** `the-loop progress` lets a session say where it is and what is next,
returns at once, and the session keeps working. The line becomes a new subscribable event,
`session.progress`. It is opt-in per work item by a label the operator names, rate-limited,
short by construction, and shown in Slack as one live line rather than a message per report.

## Requirements

### Requirement 1 — a non-blocking verb that reports progress

**User story:** As an agent on a long task, I want to report where I am without stopping,
so the person who handed me the work can tell I am alive.

#### Acceptance criteria (EARS)

1.1 WHEN `the-loop progress --work-item <ref> --text <line>` is run for a work item that
carries the progress label and is not rate-limited THEN the system SHALL emit
`session.progress` to the bus and the event log, print that it did, and exit 0 without
waiting for any reply.

1.2 The text SHALL be accepted from `--text` or from `--text-file` (`-` for stdin), exactly
one of the two.

1.3 The system SHALL cut the report to its first two non-empty lines, collapse the
whitespace inside each, and truncate the result to `progress.maxChars` with an ellipsis.

1.4 WHEN the text is empty or the ref is malformed THEN the system SHALL read and send
nothing and exit 2.

1.5 The verb SHALL be served as `POST /api/v1/sessions/progress` and, like `ask`, routed
through the control-plane service when one answers and in-process otherwise (issue-482).

### Requirement 2 — opt-in per work item, by label

**User story:** As an operator, I want to turn reports on for the one issue I handed over
and leave every other issue silent, without editing config or restarting.

#### Acceptance criteria (EARS)

2.1 The system SHALL emit only for a work item whose own tracker lists the label named by
`progress.label` (default `the-loop: progress`), read at the moment of the call.

2.2 WHEN the work item lacks the label THEN the system SHALL emit nothing, say so in one
line, and exit 0, so an agent may call the verb unconditionally.

2.3 WHEN `progress.label` is the empty string THEN the system SHALL emit nothing anywhere,
say the feature is off, and make no tracker call.

2.4 On Jira the configured label SHALL be compared in its Jira-safe form (issue-475).

2.5 WHEN the tracker cannot be read THEN the system SHALL emit nothing and exit 1, so a
flaky tracker cannot turn into a flood.

2.6 WITH the label absent from a work item, or `progress` unconfigured, behaviour SHALL be
identical to before this change.

### Requirement 3 — rate-limited

**User story:** As the person reading the room, I want a chatty agent unable to flood it.

#### Acceptance criteria (EARS)

3.1 The system SHALL emit at most one report per work item per `progress.minIntervalSeconds`
(default 300; `0` disables the limit).

3.2 WHEN a report arrives sooner THEN the system SHALL not emit it, SHALL say how many
seconds remain, and SHALL exit 0. The agent's next report is then the newest one.

3.3 The limit SHALL be per work item: one item's report never delays another's.

### Requirement 4 — a subscribable event, shown as one live line

**User story:** As a member in Slack, I want progress in the work item's own room without it
burying the gates.

#### Acceptance criteria (EARS)

4.1 `session.progress` SHALL be a row of the event catalog: subscribable, not publishable,
not recorded on the ledger, in no default subscription.

4.2 A channel SHALL hear it only when its `subscribe` list names it.

4.3 An agentic Slack room SHALL post the first report as one message and edit that message
in place for every later one, keyed apart from any phase's progress message.

4.4 The report's text SHALL be defused before it is rendered, including the plain-text
fallback: a broadcast or a user mention in it SHALL ping no one.

### Requirement 5 — configuration and the agent's instructions

5.1 The CLI config SHALL accept a top-level `progress` block with `label`,
`minIntervalSeconds` and `maxChars`, validated by `cli-config.schema.json`, documented on a
config page, and shown commented-out in the shipped template.

5.2 The skill SHALL tell the agent when to call the verb and that it never replaces `ask`.

## Part 2 — the silent-session watchdog (separate PR)

6.1 WHEN a session of a work item carrying the progress label has produced no event of any
kind for `progress.silenceSeconds` THEN the daemon SHALL emit one `session.silent` event.
6.2 The daemon SHALL NOT repeat it until the session has produced another event.
6.3 The check SHALL run inside a daemon that already exists; it SHALL NOT add a service.

## Security considerations

- **Untrusted text.** The report is written by the session. It is rendered as inert text:
  broadcasts and `<@U…>` mentions are defused in the text and in the plain-text fallback
  (R4.4). It is never written on the ticket, so it cannot carry a control keyword to an
  ingress.
- **Trust boundaries.** The label read and the room post need credentials a spawned session
  does not hold (issue-482), so the verb is served by the service that does. No new secret,
  scope or token.
- **Abuse cases.**
  - *A flood.* Mitigation: label gate, per-item interval, a two-line cap, and fail-closed
    on an unreadable label.
  - *A session turning reports on for itself.* The label is on the ticket, set by a person;
    the verb never writes it.
  - *The rate limit bypassed by disabling the event log.* The limit reads the event log, so
    with `eventLog.enabled: false` it cannot be enforced. Documented; the label gate still
    holds.
- **Fail-closed.** An unreadable label, an unconfigured feature or a missing label all emit
  nothing.
