---
configBase: ""
---

# Lifecycle hooks

Options under the top-level `hooks` key — **lifecycle hooks** of your own
([issue-344](https://github.com/MadaraUchiha-314/the-loop/issues/344),
[decision-137](/decisions/decision-137)): code the-loop asks at the moments a work item's
delivery turns, **before** it acts. Not [graph hooks](/config/cli/routing-options#graph-hooks),
which are checks at a node boundary, and not the [event log](/config/cli/observability-options),
which records what already happened. [Hooking the lifecycle](/cli/lifecycle-hooks) is the
guide; this page is the reference.

```yaml
hooks:
  - name: house-policy
    path: hooks/policy.py                  # a LifecycleHooks subclass, beside this file
    on: [work_item_start, session_spawn]   # optional: default = the methods it overrides
    required: true                         # its failure at a `proceed` point refuses
  - name: telemetry
    module: acme_loop_hooks.telemetry      # or an installed dotted module
    with: {team: platform}
  - name: compliance
    url: https://hooks.acme.example/the-loop
    tokenEnv: ACME_HOOKS_TOKEN             # the variable's NAME, never its value
    timeoutSeconds: 10
```

::: danger This is executable config
A `module` or `path` entry is imported into the-loop's own process, with your credentials
in scope; a `url` entry receives the facts of every work item you deliver and may change
what the-loop decides about it. Review an entry the way you would review code, and never
put a token in this file — name the variable that holds it under `tokenEnv`. A daemon
**refuses to start** on a declaration it cannot load.
:::

## The declaration

### hooks

- **Type:** `object[]` — one entry per executor, run in this order
- **Default:** `[]` — no lifecycle hooks
- **Related:** [hooking the lifecycle](/cli/lifecycle-hooks) · [`the-loop hooks`](/cli/commands/hooks) · [lifecycle-hooks capability](/capabilities/lifecycle-hooks)

Each entry names exactly one of `module`, `path` or `url`. Executors run in declaration
order at every point they handle; each sees the decisions the earlier ones made, and what
the last one leaves is what the-loop applies. `the-loop hooks` prints the list without
importing or contacting any of it.

### `hooks[].name`

- **Type:** `string`, matching `^[a-z][a-z0-9-]*$`
- **Default:** none — required, unique in the list

What the event log (`hooks.decided`, `hooks.failed`, `hooks.refused`) and `the-loop hooks`
call this executor.

### `hooks[].module`

- **Type:** `string` — an importable dotted name
- **Default:** none — exactly one of `module`, `path` or `url` per entry

An installed module defining exactly one `LifecycleHooks` subclass (or several, with
`executor` (below) naming one) — how a team ships shared hooks as a package.

### `hooks[].path`

- **Type:** `string`
- **Default:** none — exactly one of `module`, `path` or `url` per entry

A `.py` file defining the executor: absolute, `~/…`, or relative to the directory of
**this config file**. It is never resolved against a work item's checkout, so a session
cannot plant a module where its own daemon will import it — the same rule
[`graphs[].path`](/config/cli/graphs-options#graphs-path) follows.

### `hooks[].url`

- **Type:** `string` — `https://…`, or `http://` to a loopback host
- **Default:** none — exactly one of `module`, `path` or `url` per entry

A remote executor. the-loop `POST`s one [JSON-RPC 2.0](/cli/lifecycle-hooks#the-wire-format)
request per point — `method` the point's name, `params` the context — and reads back
`result: null` (pass through) or an object of decisions. Plain `http://` to a non-loopback
host is refused when `tokenEnv` is set: a bearer token never travels in clear.

### `hooks[].executor`

- **Type:** `string` — an attribute name in the module
- **Default:** none — the module's one `LifecycleHooks` subclass

Local entries only. The attribute to use: a `LifecycleHooks` subclass (constructed with
`with`) or an instance of one. Required when the module defines several
subclasses; refused with `with` when it names an instance.

### `hooks[].with`

- **Type:** `object`
- **Default:** `{}`

Local entries only. Keyword arguments to the class's constructor.

### `hooks[].tokenEnv`

- **Type:** `string` — an environment variable **name**
- **Default:** none — no `Authorization` header

Remote entries only. The value of that variable is sent as `Authorization: Bearer <value>`
on every request, read at call time. It is never written here and never logged. Unset or
empty at call time, nothing is sent and the call is the hook's failure. Keep the value in
[`env.file`](/config/cli/#env-file) or the ambient environment.

### `hooks[].headers`

- **Type:** `object` — string to string
- **Default:** `{}`

Remote entries only. Non-secret request headers. An `Authorization` header here is refused
— name the variable under `tokenEnv` instead.

### `hooks[].timeoutSeconds`

- **Type:** `number`, greater than `0`
- **Default:** `10`

Remote entries only. How long one request may take. Past it the call is the hook's
failure: recorded, and the operation proceeds without it — or is refused, when the entry
is `required` and the point carries `proceed`. A local executor runs
in-process and is not bounded.

### `hooks[].on`

- **Type:** `string[]` — a subset of `work_item_start`, `session_spawn`, `session_spawned`, `waiting_for_input`, `phase_changed`, `work_item_complete`
- **Default:** none — a local executor handles the points its class overrides; a remote one handles every point

Listing narrows and never widens: a local method the class does not define is not run,
whatever `on` says. A name outside the six points fails the load — an event-log type is not
a hook point ([decision-137](/decisions/decision-137)). `the-loop hooks points` lists them.

Write the key bare, as above, or quoted (`"on":`) — both load. YAML 1.1 reads an unquoted
`on` as the boolean `true` (the trap GitHub Actions workflows share), and the loader undoes
that; writing both spellings on one entry is refused
([issue-433](https://github.com/MadaraUchiha-314/the-loop/issues/433)).

### `hooks[].required`

- **Type:** `boolean`
- **Default:** `false`

When this hook fails — raises, times out, answers badly, cannot be reached — at a point
that carries `proceed` (`work_item_start`, `session_spawn`), **refuse** the operation with
a reason naming the hook, instead of proceeding without it. At any other point a failure is
recorded (`hooks.failed`) and skipped either way. The default is what a telemetry hook
wants; `true` is what a compliance gate wants.

### `hooks[].enabled`

- **Type:** `boolean`
- **Default:** `true`

`false` keeps the entry in the file and loads nothing for it.
