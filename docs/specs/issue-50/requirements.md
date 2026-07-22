---
type: requirements
phase: requirements-definition
workItem: issue-50
status: draft
approvedBy: []
collaborators: [product-manager, architect, engineer]
overrides: {}
---

# Requirements: observability and logging of the-loop CLI's actions

> Phase 1 of 3 (requirements → design → tasks). Ticket:
> [issue #50](https://github.com/MadaraUchiha-314/the-loop/issues/50). This phase should
> be reviewed and approved before moving to design.

## Introduction

the-loop's CLI processes — the webhook receiver (`gh-webhook`, issue-15), the poller
(`poll`, issue-34) and the sessions CLI — decide autonomously which GitHub events to act
on, which sessions to spawn/resume, and what to drop. Today those decisions surface only
as free-text `logging` lines on the process's stderr: there is no durable, structured,
queryable record. A user cannot answer "which events triggered this session?", "what was
rejected, and why?", or "what failed, and was it retried?" without scrolling terminal
output; an agent (Claude/Cursor) has nothing machine-readable to dig through; a
dashboard has nothing to ingest.

This work item adds an **end-to-end structured event log**: every accept / reject /
dispatch / spawn / retry / close decision is appended as one JSON object per line to a
well-documented JSONL file, plus a `the-loop events` query command over it. JSONL (not
SQLite) is the storage decision — see
[decision-025](../../decisions/decision-025.md).

## Requirements

### Requirement 1 — every triggering decision is durably recorded

**User story:** As an operator running the-loop's automation, I want a durable record of
which events triggered which sessions, so that I can audit and debug what the system did
on my behalf.

#### Acceptance criteria (EARS)

1. WHEN the receiver accepts a webhook POST THEN the system SHALL record a
   `webhook.received` event carrying the GitHub event name, delivery id and whether the
   HMAC signature was verified.
2. WHEN a verified event is mapped to work item(s) THEN the system SHALL record a
   `routing.routed` event naming the work items, the actor and the delivery id.
3. WHEN a session is spawned or resumed for an event THEN the system SHALL record
   `session.spawned` / `dispatch.succeeded` events naming the work item, harness,
   harness session id and the triggering event — so "what triggered this session?" is
   answerable from the log alone.
4. WHEN a session is registered, closed or auto-closed (PR merge/close) THEN the system
   SHALL record the corresponding `session.*` lifecycle event.

### Requirement 2 — rejections are recorded with machine-readable reasons

**User story:** As an operator, I want to see which events were rejected and why, so that
I can tell a mis-configured filter from a prompt-injection attempt from a duplicate.

#### Acceptance criteria (EARS)

1. WHEN an inbound POST fails signature verification or payload parsing THEN the system
   SHALL record a `webhook.rejected` event with a `reason` of `invalid-signature` /
   `invalid-payload`.
2. WHEN a verified event is not routed THEN the system SHALL record a `routing.dropped`
   event whose `reason` distinguishes `disabled-event`, `duplicate-delivery`,
   `no-work-item` and `unauthorized-actor` (naming the actor).
3. WHEN a routed event is discarded at dispatch THEN the system SHALL record a
   `dispatch.dropped` event whose `reason` distinguishes `duplicate-delivery`,
   `already-processed`, `spawn-policy`, `session-vanished` and `no-adapter`.
4. WHEN the poller ignores an item or comment from an unauthorized author THEN the
   system SHALL record a `poll.unauthorized` event naming the author.

### Requirement 3 — failures and retries are observable

**User story:** As an operator, I want failure and retry scenarios logged, so that I know
whether a missed action will heal itself (redelivery / next poll cycle) or needs me.

#### Acceptance criteria (EARS)

1. WHEN dispatching an event to a harness fails THEN the system SHALL record a
   `dispatch.failed` (or `dispatch.error` for an unexpected crash) event at level
   `error`, carrying the error text and a `will_retry` flag reflecting whether the
   delivery id was released for redelivery.
2. WHEN spawning a session fails THEN the system SHALL record a `session.spawn_failed`
   event with the error and its retry semantics.
3. WHEN a poll provider or item errors THEN the system SHALL record
   `poll.provider_error` / `poll.item_error` events with `will_retry: true` (the next
   cycle retries).
4. WHEN writing to the event log itself fails THEN the system SHALL NOT fail ingress —
   o11y must never break the pipeline it observes.

### Requirement 4 — the log is queryable by humans and agents

**User story:** As a developer (or a coding agent asked to "dig through the events"), I
want to query the trail with filters, so that I can answer questions without writing a
parser.

#### Acceptance criteria (EARS)

1. WHEN `the-loop events` runs THEN the system SHALL print matching events filtered by
   `--type` (fnmatch patterns), `--work-item`, `--delivery-id`, `--source`, `--level`
   (minimum) and `--since` (ISO or relative like `2h`), in `table`, `json` or `jsonl`
   format, with `--follow` tailing live.
2. WHEN `the-loop events --types` runs THEN the system SHALL list every documented event
   type with its description (the catalog agents discover the schema from).
3. WHEN the log file is missing or contains corrupt/partial lines THEN the reader SHALL
   tolerate them (skip, not crash).

### Requirement 5 — one well-understood, documented format

**User story:** As a user pointing an agent or a dashboard at the log, I want one
documented, stable event schema, so that anything can be built on top of it.

#### Acceptance criteria (EARS)

1. The system SHALL write JSON Lines with a common envelope (`ts`, `source`, `event`,
   `level`, `pid`) plus documented per-type fields, one event per line, append-only
   (multi-process safe), to `observability.eventLog.path` (default
   `.the-loop/logs/events.jsonl`, git-ignored).
2. The system SHALL keep the event-type catalog (`EVENT_TYPES`) and the emitted types
   from drifting apart (enforced by a test) and SHALL document the schema in the
   observability reference shipped with the plugin.
3. WHEN `observability.eventLog.enabled` is `false` THEN the system SHALL emit nothing.
4. WHERE the CLI is used as a library or under unit test WITHOUT an entry point
   configuring the log, emission SHALL be a silent no-op (zero I/O).

## Out of scope

- A SQLite store or query engine — JSONL is the source of truth; anything (including a
  SQLite import or dashboard) can be layered on it later (decision-025).
- Log rotation/retention — the file is append-only runtime state; operators may rotate
  or truncate it externally (the reader and `--follow` tolerate truncation).
- Observability of the *harness sessions'* own work (that is issue-32's tmux
  attach/web terminal); this log covers the-loop's own ingress/dispatch decisions.
