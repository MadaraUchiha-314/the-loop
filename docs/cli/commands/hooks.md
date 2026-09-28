# `hooks`

What your CLI config declares under the top-level
[`hooks`](/config/cli/hooks-options) — the **lifecycle hooks**
([issue-344](https://github.com/MadaraUchiha-314/the-loop/issues/344)) — and the points
they can attach to. Importing nothing, contacting nothing.

```bash
the-loop hooks [list] [--format text|json]
the-loop hooks points [--format text|json]
```

## `list`

The declaration, read **strictly** — an unparseable config or a malformed entry is an
error here, not "nothing declared" — and reported without importing a module or sending a
request. That is its purpose: a `module`/`path` entry runs inside the-loop's process and a
`url` entry receives every work item's facts, so you get to read what would run **before**
a work item does. The daemons load the same declaration at start and refuse to start on
one they cannot load; this command finds the mistake first.

```text
$ the-loop hooks
lifecycle hooks (3 declared in /home/me/.the-loop/cli-config.yaml) — nothing here has been imported or contacted:
  house-policy  path hooks/policy.py   on: work_item_start, session_spawn   required
  telemetry     module acme_loop_hooks.telemetry   on: the points the class overrides
  compliance    url https://hooks.acme.example/the-loop   on: every point   timeout 10s   token $ACME_HOOKS_TOKEN

a daemon loads the declaration at start and refuses to start on one it cannot load; a
one-shot command loads it on first use and runs hookless, recording `hooks.load_failed`,
when it cannot.
```

| Exit | Meaning |
|------|---------|
| `0` | The declaration was read (possibly empty). |
| `1` | The config could not be read, or an entry is malformed — the error names it. |

`--format json` prints `{"config", "hooks": [{name, kind, target, on, required, enabled,
…}]}`, or `{"config", "hooks": [], "error"}`.

## `points`

The catalog: each point, when it fires, the **facts** a hook reads and the **decisions** it
may change.

```text
$ the-loop hooks points
lifecycle points (6):

  work_item_start  (WorkItemStart)
    fires:     once per arming, when a start is accepted and before the workspace is prepared or any session exists
    facts:     work_item, loop, command, actor, harness, instance, repository
    decisions: proceed, reason
  …
```

`--format json` prints `{"points": [{point, context, fires, facts, decisions, summary}]}`.

## See also

- [Hooking the lifecycle](/cli/lifecycle-hooks) — writing one, locally or as a service.
- [`hooks` options](/config/cli/hooks-options) — every key of an entry.
- [`the-loop graph hooks`](/cli/commands/graph#hooks) — the *other* hooks: checks on the
  process graph's node boundaries.
