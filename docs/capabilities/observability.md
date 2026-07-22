# Capability: observability

> End-to-end o11y of the actions the-loop's CLI processes take autonomously — a
> structured, durable, queryable audit trail of every trigger/reject/dispatch/failure
> decision.

## What it is

A structured JSONL event log (`.the-loop/logs/events.jsonl` by default, git-ignored)
that the webhook receiver, the poller and the sessions CLI append every decision to,
plus the `the-loop events` query command over it. It answers "which events triggered
this session?", "what was rejected, and why?" and "what failed, and will it retry?" —
for humans, coding agents and any dashboarding built on top.

## Current behaviour

- Every accept/reject/route/dispatch/spawn/close decision SHALL be appended as one JSON
  object per line with a common envelope (`ts`, `source`, `event`, `level`, `pid`) plus
  documented per-type fields (`work_item`, `delivery_id`, `reason`, `error`,
  `will_retry`, …).
- Rejections SHALL carry machine-readable reasons (`invalid-signature`,
  `unauthorized-actor`, `duplicate-delivery`, `spawn-policy`, …); failures SHALL carry
  the error and whether redelivery / the next poll cycle retries them.
- `the-loop events` SHALL filter by `--type`/`--work-item`/`--delivery-id`/`--source`/
  `--level`/`--since`, output `table|json|jsonl`, tail with `--follow`, and list the
  documented event-type catalog with `--types`.
- The catalog (`EVENT_TYPES` in `cli/the_loop/eventlog.py`) SHALL be the enforced
  single source of truth for event types (a unit test fails on drift).
- Writes SHALL be append-only and multi-process safe; a broken log SHALL never break
  ingress; emission SHALL be a no-op in library/test use until a CLI entry point
  configures it; `observability.eventLog.enabled: false` SHALL disable it.
- JSONL SHALL be the source of truth (no SQLite store); query/dashboard layers build on
  top of the file ([decision-025](../decisions/decision-025.md)).

## Design

[`skills/the-loop/reference/observability.md`](../../skills/the-loop/reference/observability.md)
(schema + querying, shipped with the plugin) ·
[`docs/specs/issue-50/design.md`](../specs/issue-50/design.md)

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-50 | Added the structured JSONL event log and `the-loop events` | [spec](../specs/issue-50/), [decision-025](../decisions/decision-025.md) |
