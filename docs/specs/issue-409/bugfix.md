---
type: bugfix
phase: requirements-definition
workItem: "github:MadaraUchiha-314/the-loop#409"
status: in-review            # draft | in-review | approved — tier 3: the PR approval is the human gate
approvedBy: []
severity: high
collaborators: [engineer]
overrides: {}
riskTier: 3                  # the bus's delivery path and a new state file; no auth, no credential, no schema
---

<!-- Authored per the the-loop:writing skill. -->

# Bugfix spec: a question that reaches no channel is lost, and the status surface stays green

> Phase 1 of 4 (bugfix → design → testing plan → tasks). Source:
> [issue-409](https://github.com/MadaraUchiha-314/the-loop/issues/409).

## Summary

**The bus drops an event that reached no channel, and says so only at `debug`.** When
`the-loop ask` publishes `session.awaiting_input`, the ledger records the question as a
comment first and the fan-out follows. If every channel refuses the post, the record
stands and the fan-out result is thrown away: one `channel.post_failed` line, one
`bus.published` line with `posted: 0` at `debug` level, and nothing anywhere that remembers
the event still needs delivering. Nothing retries it, the session is told only that "the
work item has it", and `the-loop status` reports every service healthy.

The reporter lost 144 of 144 asks over three days and found out by reading GitHub.

## Steps to reproduce

1. Configure a Slack channel subscribed to `session.awaiting_input`.
2. Make its posts fail — a rotated bot token, a renamed channel, a rate limit, or an
   unreachable network. (In the report: the service reloaded a rotated token, the
   already-running sessions kept the one they were spawned with, and every post came back
   `channel_not_found`.)
3. From a session, run `the-loop ask <ref> "A or B?"`.
4. Read the deployment's `.the-loop/logs/events.jsonl`, then run `the-loop status`.

Observed: `channel.post_failed`, then `bus.published` with `posted: 0` at `debug`, then
`session.awaiting_input` with `comment_posted: true`. `status` prints every service
running. The question sits on the ticket and no room ever hears it. Fix the token and
nothing re-delivers the backlog.

## Expected vs actual

| | Expected | Actual |
|---|---|---|
| an event no channel took | remembered, and retried when the channels recover | forgotten at the end of `publish` |
| the operator's `status` | says delivery is behind | every service `running`, exit 0 |
| the event log | a `warning` naming the undelivered event | one `debug` line with `posted: 0` |
| the asking session | told that nobody heard it | told "the work item has it" |
| a transient outage (rate limit, network blip) | costs a delay | costs the question |

## Root cause

**`publish` has no memory of a failed delivery, and no caller has one either.**
`cli/the_loop/channels/bus.py` records the event, posts to each subscribed channel, and
returns a `PublishResult`. The per-channel failure is logged (`channel.post_failed`,
`warning`) and the aggregate is logged (`bus.published`, `debug`, `posted: 0`) — both as
lines in whichever event log the *calling process* resolved. For a session, that is its own
checkout's `.the-loop/logs/events.jsonl`; the service's log, which the operator reads,
shows only the deliveries that worked.

`ask_session` (`cli/the_loop/core/sessions.py`) then computes its outcome from the
**record** alone: `ok = bool(record and record.ok)`. That is deliberate — the ticket is
the source of truth and a channel failure must not fail the ask — but it means the exit
code, the summary line and the `session.awaiting_input` event all say "asked" when no
human was reached.

So the loss has one cause with two faces: **the delivery is not durable** (nothing outlives
the failing call) and **the failure is not visible** (its only trace is a `debug` line in a
per-checkout file).

### What about the envelope refusal the report names?

The report's reading of `publishers.py` is correct — `if has_envelope(body): return False`
stops the poller mirroring the ask's comment as `comment.agent` — but making that refusal
conditional on a recorded `posted >= 1` cannot be the fix, for two reasons:

1. **The count cannot be in the comment when it is written.** The ledger records *before*
   the fan-out, precisely so the record's URL can ride onto the event every channel
   renders. A delivery count can only reach the comment as a second write, and both
   ingresses read the comment before that write lands — the webhook router within about a
   second of the POST. The fix would appear to work in a poller deployment and silently
   not work in a webhook one.
2. **A mirror is not the delivery that failed.** `comment.agent` reaches whoever subscribes
   to `comment.agent`, rendered as a comment, not as the question the loop is waiting on.
   The subscriber set and the rendering are both different from the ones the operator
   configured for `session.awaiting_input`.

Requirement 1 below therefore fixes the delivery at its source, and the envelope's claim
("the bus made this record; its source channel has it") becomes true again once an
undelivered event is remembered and retried rather than dropped.

## Requirements

### Requirement 1 — an undelivered event outlives the call that failed

**User story:** As an operator, I want an event no channel accepted to be remembered, so
that a transient failure costs a delay instead of the message.

#### Acceptance criteria (EARS)

1. WHEN the bus publishes an event, at least one channel is asked to post it, and none
   accepts it THEN the system SHALL write the event to a durable outbox under the
   deployment's state root.
2. WHEN the bus publishes an event and at least one channel accepts it THEN the system
   SHALL write nothing to the outbox.
3. WHEN no channel is asked to post an event — none is configured, none subscribes, or the
   only candidate is the event's own source — THEN the system SHALL write nothing to the
   outbox.
4. WHEN the outbox is written THEN the entry SHALL carry the event, the work item, the
   record's URL, the channels that were asked, the error each returned, and the time.
5. WHEN the outbox holds more entries than its cap THEN the system SHALL drop the oldest
   and SHALL emit one `warning` naming what was dropped.
6. WHEN writing the outbox fails for any reason THEN the system SHALL log it and SHALL
   NOT change what `publish` returns to its caller.

### Requirement 2 — the backlog is retried until it is delivered

**User story:** As an operator who has just fixed a bad token, I want the questions that
piled up to be delivered without my doing anything, so that recovery is one action.

#### Acceptance criteria (EARS)

1. WHEN a deployment runs the poller or the webhook receiver AND a channel is configured
   THEN the system SHALL drain the outbox on an interval.
2. WHEN a drain posts an outbox entry and at least one channel accepts it THEN the system
   SHALL remove that entry and SHALL emit one `info` event naming the event type, the work
   item and how long it had waited.
3. WHEN a drain posts an outbox entry and no channel accepts it THEN the system SHALL keep
   the entry, SHALL record the attempt and its error, and SHALL NOT retry it before the
   entry's backoff has elapsed.
4. WHEN a drain re-posts an entry THEN the system SHALL NOT record it on the ledger again.
5. WHEN a drain runs THEN it SHALL post at most a bounded number of entries per cycle, and
   a failure on one entry SHALL NOT stop the rest.
6. WHEN the drain thread raises THEN the daemon hosting it SHALL survive.

### Requirement 3 — the operator's status surface stops reporting green

**User story:** As an operator, I want `the-loop status` to tell me deliveries are behind,
so that I learn it from the command I already type instead of from a ticket.

#### Acceptance criteria (EARS)

1. WHEN the outbox holds at least one entry THEN `the-loop status` SHALL print one line
   naming how many events are undelivered, how long the oldest has waited, and the newest
   error.
2. WHEN the outbox is empty or absent THEN `the-loop status` SHALL print nothing about
   delivery.
3. WHEN `the-loop status --format json` is run THEN the report SHALL carry the same facts
   as a field of its own.
4. WHEN the outbox is unreadable THEN `status` SHALL still answer, reporting no backlog
   rather than failing.
5. The undelivered count SHALL NOT move `status`'s exit code, which answers "is every
   enabled service running".

### Requirement 4 — the bus says out loud that it delivered nothing

**User story:** As an operator reading the log, I want an undelivered event to be a
`warning`, so that it is visible beside the failures I already watch for.

#### Acceptance criteria (EARS)

1. WHEN an event is written to the outbox THEN the system SHALL emit a `warning` event
   naming the event type, the work item, the channels asked and the queue depth — ids
   only, never the message text.
2. WHEN `the-loop ask` publishes a question that no channel accepted THEN the verb SHALL
   print that no channel received it and that it is queued for redelivery.
3. WHEN `the-loop ask` publishes a question THEN its `session.awaiting_input` event SHALL
   carry how many channels took it.
4. WHEN no channel accepted the question THEN the ask's exit code SHALL stay what it is
   today — the record on the ticket decides it, so a channel outage never fails the verb.

## Security considerations

**The outbox holds message text on disk, which no other file under `channels/` does at
this scale.** An entry carries the event the bus was about to post: an agent's question, a
person's relayed reply, a decision record. The mitigations are the ones the state root
already relies on, stated so the reviewer can check them:

- It lives under the **deployment's state root** (`<root>/channels/undelivered.json`),
  written `0600`-by-default through the same tmp-file-and-rename as the channel state, and
  classified **local** in `GENERATED_PATHS` — it never travels into a repository, and
  `the-loop check`'s portability rules apply to it like any other generated path.
- The text is the **same text that was one API call from being posted to the channel**, and
  it is stored exactly as the renderer would have rendered it — no new scrubbing decision
  is taken here, and none is undone.
- The **event log keeps its ids-only rule**: every new event emitted by this change names
  the event type, the work item, channel names, counts and errors, and never the text.
- An entry is removed on delivery, and the file is capped, so a long outage bounds the
  text at rest at the cap rather than growing without limit.

**The drain must not become a second way to write to the ledger.** It re-posts to channels
only, never through the record path — R2.4 — so a replayed entry can never open an issue,
post a comment, or forge a gate answer. It posts to the channels the current config
resolves, so a channel an operator has since removed is never posted to, and a drained
entry is rendered by the channel from the event exactly as the original post would have
been.

**Replay is bounded and visible.** An entry redelivered after a long outage is a message
arriving late, which the channel's own rendering already dates; the alternative — silently
discarding it — is the defect. The retry is a fixed backoff per entry and a per-cycle
budget, so the drain cannot become a burst against a provider that is rate-limiting, which
is one of the failures that fills the outbox in the first place.
