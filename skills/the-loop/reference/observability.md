# Observability reference

Config: `observability` (`devLevel`/`runtimeLevel`/`browserLogging`) in
`.the-loop/harness-config.yaml` (the plugin config). The CLI event log below is configured
separately, in the independent CLI config (`eventLog`; decision-032).

## Core rule: dev-time == run-time

Logging and observability for debugging MUST be **EXACTLY the same** during development
and at runtime (when the system is actually running). The ONLY advantage at dev-time is
that you can set **breakpoints** and inspect variable values. Do not add log statements
or instrumentation that exist only in dev — that defeats the purpose.

## Configurable levels

There are different, configurable levels of observability:
- **Dev-time** (`observability.devLevel`, default `debug`): all `debug` logs and above
  are accessible.
- **Run-time** (`observability.runtimeLevel`, default `info`): all `info` logs and above
  are available.

Use the same logger and the same log lines in both; only the active level differs.

## CLI event log — the audit trail of the-loop's own actions

Config: `eventLog` in the **CLI config** (`cli-config.yaml`: `enabled`, default `true`;
`path`, default `.the-loop/logs/events.jsonl`, git-ignored) — independent of any repo's
plugin config, resolved via `--config`/env/cwd/home (see `cli/README.md`,
[decision-032](../../../docs/decisions/decision-032.md)). Decision:
[decision-025](../../../docs/decisions/decision-025.md) — JSONL, not SQLite.

the-loop's CLI processes (`the-loop gh-webhook`, `the-loop poll`, `the-loop sessions`)
append **every accept / reject / dispatch / spawn / retry / close decision** they make
as one JSON object per line to the event log. It is the durable, machine-queryable
answer to:

- **which events triggered a particular session?** — `session.spawned` /
  `dispatch.succeeded` records name the work item, harness, session id and the
  triggering GitHub event + delivery id;
- **which events were rejected / accepted, and why?** — `webhook.rejected`,
  `routing.dropped` and `dispatch.dropped` carry a machine-readable `reason`
  (e.g. `invalid-signature`, `unauthorized-actor`, `duplicate-delivery`,
  `spawn-policy`);
- **what failed, and will it retry?** — `dispatch.failed`, `session.spawn_failed`,
  `poll.provider_error` carry `error` and `will_retry` (whether GitHub redelivery /
  the next poll cycle heals it).

### Record shape

Envelope on every record: `ts` (UTC ISO-8601, ms), `source`
(`gh-webhook` | `poll` | `sessions`), `event` (dot-namespaced type), `level`
(`debug`|`info`|`warning`|`error`), `pid`. Common per-type fields: `work_item` /
`work_items` (`github:owner/repo#15`), `delivery_id` (joins one delivery's whole
trail), `gh_event` + `action`, `actor`, `harness`, `harness_session_id`, `reason`,
`error`, `will_retry`.

The **full catalog** of event types with descriptions is `the-loop events --types`
(source of truth: `EVENT_TYPES` in `cli/the_loop/eventlog.py`; a unit test keeps
emitted types and the catalog in sync).

### Querying it (humans and agents)

```bash
the-loop events                                    # last 50 events, table
the-loop events --work-item github:octo/repo#15    # one item's full history
the-loop events --delivery-id <uuid>               # one delivery, end to end
the-loop events --type 'dispatch.*' --level error  # what failed
the-loop events --since 2h --follow                # live tail
the-loop events --format json                      # machine-readable (agents)
the-loop events --types                            # documented event catalog
```

The file itself is plain JSONL — `grep`, `jq`, `tail -f` and any dashboard/DB
ingestion work directly on it (e.g.
`jq 'select(.event=="session.spawned")' .the-loop/logs/events.jsonl`). Agents asked to
"dig through the events" should start with `the-loop events --types`, then filter with
the flags above (or read the file directly when unavailable).

Writes are append-only and multi-process safe; a broken log never breaks ingress
(write failures are warned once and swallowed). There is no built-in rotation —
truncate/rotate externally; readers tolerate it.

## Observing services

- **Locally running services**: prefer **file-system based logging** that the agent
  harness can read directly (tail/grep the log files).
- **Browser-based logging**: surface browser console/network logs to the harness via
  `observability.browserLogging` (default `chrome-devtools-mcp` — the Chrome DevTools
  MCP server).
  - _Open question:_ confirm chrome-devtools MCP is the right mechanism for browser
    logging, and document the setup. Record a decision once validated.
