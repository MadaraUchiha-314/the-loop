# `events`

Query the structured event log — the end-to-end record of what the-loop's CLI processes
decided, and why.

```bash
the-loop events [--file .the-loop/logs/events.jsonl] [--type PATTERN ...] \
                [--work-item github:OWNER/REPO#N] [--delivery-id ID] \
                [--source gh-webhook|poll|sessions] [--level warning] \
                [--since 2h|2026-07-22T10:00:00Z] [--limit 50] \
                [--format table|json|jsonl] [--follow]
the-loop events --types      # the documented catalog of event types
```

## What is in the log

The receiver, the poller **and** the `sessions` command append **every decision they make**,
as one JSON object per line:

- webhook accepted or rejected, and why;
- event routed or dropped, with a machine-readable `reason` — `unauthorized-actor`,
  `duplicate-delivery`, `self-comment`;
- session spawned or resumed, naming the triggering event and delivery id;
- dispatch failed, with the error and whether a redelivery or the next poll cycle retries it;
- session closed or auto-closed.

Written to [`eventLog.path`](/config/cli/observability-options#eventlog-path) (default
`.the-loop/logs/events.jsonl`, git-ignored).

## Flags

| Flag | Default | Meaning |
|------|---------|---------|
| `--file` | [`eventLog.path`](/config/cli/observability-options#eventlog-path) | Log to read. |
| `--type PATTERN` | none | Filter by event type; **fnmatch** patterns, repeatable. |
| `--work-item` | none | One work item's full history. |
| `--delivery-id` | none | Follow a single GitHub delivery end to end. |
| `--source` | all | `gh-webhook`, `poll` or `sessions` — the emitting process. |
| `--level` | all | Minimum level, e.g. `warning` shows warning + error. |
| `--since` | none | ISO-8601 UTC, or relative: `30s`, `15m`, `2h`, `1d`. |
| `--limit` | `50` | Keep the last N matches. `0` = no limit. |
| `--format` | `table` | `table`, `json` or `jsonl`. |
| `--follow` | off | After printing, keep watching and print new matches. |
| `--types` | — | Print the documented event-type catalog and exit. |

## Recipes

```bash
# Why did nothing happen?
the-loop events --type 'event.dropped' --limit 20

# What failed?
the-loop events --type 'dispatch.*' --level error

# Which events triggered this session?
the-loop events --work-item github:octo/repo#42

# Follow one GitHub delivery end to end
the-loop events --delivery-id 3f9c1e20-…

# What did harness-trust actually write?
the-loop events --type 'workspace.trust*'

# Tail problems live
the-loop events --follow --level warning
```

## Record shape

Every record carries `ts`, `source`, `event`, `level` and `pid`, plus documented per-type
fields. The catalog (`the-loop events --types`) is enforced against the emitted types by a
unit test, so a new event type cannot ship undocumented.

`--format json|jsonl` is machine-readable, for agents and dashboards. The file itself is
plain JSONL, so `grep`, `jq` and `tail -f` work directly on it:

```bash
jq -r 'select(.event | startswith("session.")) | "\(.ts) \(.event)"' \
   .the-loop/logs/events.jsonl
```

## Guarantees

Writes are append-only and multi-process safe. A broken log never breaks ingress.
[`eventLog.enabled: false`](/config/cli/observability-options#eventlog-enabled) turns
emission off entirely.

Schema and agent guidance:
[observability reference](/operating-model/reference/observability). Why JSONL and not
SQLite: [decision-025](/decisions/decision-025).

## See also

- [Observability options](/config/cli/observability-options)
- [observability](/capabilities/observability) — the capability doc.
