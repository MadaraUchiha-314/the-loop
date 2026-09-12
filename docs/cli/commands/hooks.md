# `hooks`

Report the **lifecycle hooks** the CLI config declares — the modules, the attachments,
and the catalogued events each pattern matches — **without importing any of it**.

```bash
the-loop hooks [--format text|json]
```

The modules a [`hooks`](/config/cli/hooks-options) block names run inside the-loop's own
process, with your credentials in scope. This command exists so you can read what would
run before anything runs it — the same shape as
[`the-loop graph hooks`](/cli/commands/graph#hooks) for the graph hooks and
[`the-loop critic list`](/cli/commands/critic#list) for the critics, the other two blocks
of executable configuration the CLI config carries.

```text
$ the-loop hooks
attach points: 147 event types (`the-loop events --types`; hooks.* excluded)
shipped lifecycle hooks (1): forward-event

the CLI config declares 1 module(s) and 2 attachment(s) — nothing here has been imported:
  module  hooks/telemetry.py  (resolved against /home/op/.the-loop)
  attach  x-otel-span → 27 event(s) [session.spawned, session.closed, graph.*]  with: {'service': 'the-loop'}
  attach  forward-event → 2 event(s) [work_item.*]  with: {'url': 'https://…', 'tokenEnv': 'ACME_TELEMETRY_TOKEN'}

a declaration that cannot load fails the entry point that loads it (`the-loop start`, the
receiver, the poller, and any command that records events) rather than being skipped.
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--format` | `text` | `text`, or `json` (`attachPoints`, `shipped`, `modules`, `attach[]` with each attachment's `on`, `events` and `with`) for scripting. |

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Reported (including "no lifecycle hooks declared"). |
| `2` | The block could not be parsed — a malformed entry, a hook that is neither `x-…` nor shipped, a pattern matching no event type, or bad `forward-event` parameters. The message names the entry. |

What this command **cannot** tell you is whether an `x-` hook actually exists: that needs
the module imported, which is exactly what this command refuses to do. The entry points
that load the block — `the-loop start`, the receiver, the poller, and every command that
records events — fail with a message naming the module when it is missing, raises,
registers nothing or registers the wrong name.

## See also

- [Hook options](/config/cli/hooks-options) — the block this reports.
- [Adding a hook](/cli/hooks) — writing one.
- [`events --types`](/cli/commands/events) — the attach points.
