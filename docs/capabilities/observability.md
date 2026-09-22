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
  configures it; `eventLog.enabled: false` in the **CLI config** SHALL disable it
  (independent of any repo's plugin config — decision-032).
- JSONL SHALL be the source of truth (no SQLite store); query/dashboard layers build on
  top of the file ([decision-025](../decisions/decision-025.md)).

## Design

[`skills/the-loop/reference/observability.md`](../../skills/the-loop/reference/observability.md)
(schema + querying, shipped with the plugin) ·
[`docs/specs/issue-50/design.md`](../specs/issue-50/design.md)

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-409 | Three `channel.*` rows for delivery that did **not** happen — `undelivered` (`warning`: an event every asked channel refused, now queued; names the type, the work item, the channels and the queue depth), `delivered_late` (a queued event a later attempt landed, with its attempts and how long it waited) and `undelivered_dropped` (`warning`: the queue was full and its oldest entry went). `session.awaiting_input` gains `channels_posted`. Ids and counts only, the rule unchanged: the queued message text lives in the outbox, never in the log. Before this, delivering to nobody was one `debug` line with `posted: 0` | [spec](../specs/issue-409/), [channels](channels.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/409) |
| issue-377 | `session.spawned` and `session.respawned` carry the argv the session was launched with — `harness_args`, `model`, `effort`, each omitted when empty — and `session.pr_spawned` carries `harness_args`, so "was this session launched with the flag the config declares?" is answerable from `events.jsonl` alone, which is the regression check the issue asked for | [spec](../specs/issue-377/), [interactive-sessions](interactive-sessions.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/377) |
| issue-245 | Six `channel.*` event types joined the catalog — `posted`, `post_failed`, `reply_received`, `dropped` (reasons: `unmapped` \| `self-authored` \| `unauthorized-actor` \| `undeliverable`), `mirrored`, `mirror_failed` — tracing a question's fan-out to the conversation channels and a reply's round-trip back; payloads carry ids, never message text or tokens | [spec](../specs/issue-245/), [decision-094](../decisions/decision-094.md) |
| issue-239 | The event log gained a second reader: `stream.subscribed`, `stream.refused`, `stream.desync` and `stream.disconnected` record who is watching a workstation, what was refused and why, and when a subscriber was told to resynchronise. `api.request` and `mcp.call` are excluded from what the stream carries — the log still serves them to `the-loop events` | [spec](../specs/issue-239/), [decision-087](../decisions/decision-087.md) |
| issue-63 | `observability.eventLog` moved into the independent, repo-agnostic CLI config as top-level `eventLog` | [spec](../specs/issue-63/), [decision-032](../decisions/decision-032.md) |
| issue-50 | Added the structured JSONL event log and `the-loop events` | [spec](../specs/issue-50/), [decision-025](../decisions/decision-025.md) |
