---
configBase: hooks
---

# Hook options

Options under the top-level `hooks` key — **lifecycle hooks**: code of your own that runs
when the-loop *records an event*
([issue-344](https://github.com/MadaraUchiha-314/the-loop/issues/344),
[decision-124](/decisions/decision-124)). Any of the event types
[`the-loop events --types`](/cli/commands/events) lists is an attach point — from
`session.spawned` (work start) to `work_item.ended` (work finish), and every dispatch,
control keyword, PR spawn and channel post in between.

This is the second of the-loop's two hook surfaces. The first,
[`routing.graph.hooks`](/config/cli/routing-options#graph-hooks), appends a **gate** to a
node of the process graph. This one attaches an **observer** to an event. Same
`@hook("x-…")` decorator, same load-or-fail rule; the differences are
[on one table](/cli/hooks#graph-hook-or-lifecycle-hook).

```yaml
hooks:
  modules:
    - path: hooks/telemetry.py              # relative to THIS FILE's directory, inside it
    - module: acme_loop_hooks.telemetry     # or an installed dotted name
  lifecycle:
    - hook: x-otel-span                     # registered by a module above
      on: [session.spawned, session.closed, graph.*]
      with: {service: the-loop}
    - hook: forward-event                   # shipped — no Python needed
      on: "work_item.*"
      with:
        url: https://telemetry.acme.example/the-loop
        tokenEnv: ACME_TELEMETRY_TOKEN      # a variable NAME; read when the hook runs
        headers: {X-Source: the-loop}
        timeoutSeconds: 5
```

::: danger This is executable config
A module named here is **imported into the-loop's own process**, with your environment and
your credentials in scope — the receiver, the poller, the service and every one-shot
command that records events. Review an entry the way you review code, exactly as
[`critics[]`](/config/cli/critics-options) and `routing.graph.hooks`. That is also why
the declaration lives here and not in any repository's file: a checkout carrying a hook
module nobody declared runs nothing ([decision-123](/decisions/decision-123)).
:::

A declaration that cannot be honoured — a malformed block, a missing or raising module,
a hook nothing registered, a pattern matching no event type, a bad `forward-event` URL
— **fails the entry point that loads it** with a message naming the entry. Nothing
degrades to "no hooks": a telemetry hook that silently stopped is the failure this
refuses. [`the-loop hooks`](/cli/commands/hooks) reports the block **without importing
it**, so you can read what would run before anything runs it.

## How a hook runs

A lifecycle hook **observes**. After a record is built it is written to the
[event log](/config/cli/observability-options) (when enabled) and queued for its hooks;
one worker thread runs them in emission order. The thread that emitted never waits, so a
webhook delivery or an API request costs nothing extra however slow your HTTP call is. A
hook that raises is recorded as `hooks.failed` and the next one runs. A hook cannot block
the event it observes, cannot answer a gate and cannot move the process graph — a veto is
a [graph hook](/cli/hooks).

Two guards keep a hook from feeding the system: the `hooks.*` events (`hooks.loaded`,
`hooks.failed`, `hooks.dropped`) are never attach points, and a record emitted *by* a hook
is written but never re-dispatched. The queue holds 1024 records; when it is full the
record is dropped **for hooks only** (never for the log) and one `hooks.dropped` is
recorded per overflow episode. A normal exit drains the queue for up to five seconds.

## `modules[]`

### `modules[].path`

- **Type:** `string`
- **Default:** none — exactly one of `path` or `module` per entry
- **Related:** [adding a hook](/cli/hooks)

A `.py` file **relative to this config file's directory, and inside it** — so a hook
declared in `~/.the-loop/cli-config.yaml` lives under `~/.the-loop/`. A lifecycle hook is
the instance's (it fires for `server.started`, which has no checkout), so its code lives
with the declaration; a graph hook's `path` resolves against each checkout instead. An
absolute path, a `..` escape or a symlink leaving the directory is refused at load.

### `modules[].module`

- **Type:** `string`
- **Default:** none — exactly one of `path` or `module` per entry

An importable dotted module name installed alongside the-loop's CLI — how a team ships
shared hooks as a package, and the one form that serves both hook surfaces from one
install. A module already imported is reloaded so its decorators run; a hook module must
therefore be safe to execute twice: define hooks, do nothing else.

## `lifecycle[]`

### `lifecycle[].hook`

- **Type:** `string`
- **Default:** none — required

The hook's registered name: `x-<something>` registered by one of `modules[]`, or a
**shipped** lifecycle hook. One ships:

| Shipped hook | What it does | `with` |
|---|---|---|
| `forward-event` | POSTs the record as JSON to `url`, one attempt, no retry | `url` (required; `http`/`https` only), `tokenEnv` (the **name** of the environment variable holding a bearer token, read when the hook runs; unset → nothing is sent), `headers` (string → string, sent verbatim), `timeoutSeconds` (default 5) |

A name that is neither fails the load. Shipped **lifecycle** hooks are yours to attach;
shipped **graph** hooks are not, because attaching `classify-feedback` elsewhere would
edit the process. An observer edits nothing.

### `lifecycle[].on`

- **Type:** `string` or `string[]`
- **Default:** none — required

The event type(s) to run on: an exact name (`session.spawned`), an `fnmatch` pattern
(`graph.*`, `session.spawn*`, `*`), or a list of them. Expanded against the catalog when
the config is loaded; a pattern that matches nothing fails the load, so a typo cannot
silently disarm a telemetry hook. `hooks.*` are never matched. A bare `on:` key parses as
the boolean `true` in YAML 1.1 — the-loop accepts that spelling too, so you need not
quote it.

### `lifecycle[].with`

- **Type:** `object`
- **Default:** `{}`

Parameters handed to the hook as `event.params`. For `forward-event`, the keys above;
for a hook of your own, whatever it reads. Never a secret: name an environment variable
and keep the value in [`env.file`](/config/cli/#env-file) or the ambient environment.

## See also

- [Adding a hook](/cli/hooks) — writing one, and the graph-hook / lifecycle-hook table.
- [`the-loop hooks`](/cli/commands/hooks) — what this block declares, without importing it.
- [lifecycle-hooks](/capabilities/lifecycle-hooks) — the capability, normatively.
- [Observability options](/config/cli/observability-options) — the event log the hooks
  observe.
