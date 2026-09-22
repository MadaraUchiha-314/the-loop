---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#409"
---

# Documentation: the bus keeps an outbox, and `status` reads it

> The organized view must not rot: every capability this change touches is updated in the
> same pull request.

| Page | What changed |
|---|---|
| [`docs/capabilities/channels.md`](../../../capabilities/channels.md) | Two behaviour bullets — what no channel took is queued, drained and counted (the file, the cap, the budget, the backoff, the drain's posts-never-records rule, the `status` line) and what the asking session is now told — plus the history row |
| [`docs/capabilities/observability.md`](../../../capabilities/observability.md) | History row for the three new `channel.*` event types and `channels_posted` on `session.awaiting_input`, with the ids-only rule restated |
| [`docs/cli/state.md`](../../../cli/state.md) | The new generated path: its classification-table row (**local**), its line in the state tree, and its own section — what an entry holds, how it drains, what deleting the file means |
| [`docs/cli/commands/status.md`](../../../cli/commands/status.md) | A *When channel deliveries are behind* section: the line, what it means, why it exists, the `--format json` field, and that it never moves the exit code |
| `cli/the_loop/eventlog.py` (`EVENT_TYPES`) | The in-product catalog `the-loop events --types` serves: `channel.undelivered`, `channel.delivered_late`, `channel.undelivered_dropped`, and the amended `session.awaiting_input` row |

**Not affected**, checked and recorded rather than assumed:

- `docs/capabilities/control-plane.md` — the status **document** gains a field; no route,
  no schema and no dashboard view reads it.
- `docs/api-specs/openapi` — nothing there describes the status document's fields.
- `docs/config/**` — no configuration key is added, removed or renamed. The cap, the
  budget, the interval and the backoff are constants, because an operator who needs to tune
  them has a different problem than this work item fixes.
- `docs/guide/slack.md` — the operator's Slack setup is unchanged; no scope, grant or
  manifest entry moves.
