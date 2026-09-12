# Adding a hook

A **hook** is the-loop's unit of work at a node boundary — and, since issue-344, at any
event it records ([lifecycle hooks](#lifecycle-hooks), below): one function, one signature, one
return type. Ten ship with the CLI ([process-graph](/capabilities/process-graph) § The hook
contract). Since [issue-248](https://github.com/MadaraUchiha-314/the-loop/issues/248) an operator
can bring their own — a licence-header check on `implementation`, an architecture
sign-off on `design`, a ping to your change-management system when a work item reaches
`needs-review`. Since [issue-352](https://github.com/MadaraUchiha-314/the-loop/issues/352)
the declaration is the **operator's CLI config**, not a repository's harness config: the
CLI reads no repository's configuration, so a hook runs only where the operator wrote it
down. The module can still live in the repository's tree.

The graph itself stays the-loop's: nobody declares nodes, edges or loops, and nobody
removes, reorders or replaces a shipped hook. What you can do is **append** one of your own
to a boundary the shipped graph already declares.

## Write it

```python
# .the-loop/hooks/house_rules.py
from the_loop.graph import HookContext, HookResult, Message, hook


@hook("x-licence-header")
def licence_header(ctx: HookContext) -> HookResult:
    missing = [p for p in (ctx.repo / "src").rglob("*.py") if "SPDX" not in p.read_text()]
    if missing:
        return HookResult.blocked(
            "x-licence-header",
            [Message(text="missing SPDX header", path=str(p)) for p in missing],
        )
    return HookResult.ok("x-licence-header")
```

Same decorator, same context and same result type a shipped hook uses — there is one hook
API, not two. `ctx` carries the work item, the node, the boundary, the repository root, the
compiled graph, the declared skips, and the `with:` parameters as `ctx.params`; it carries
credential **handles**, never values.

Every name must start with `x-`. The unprefixed namespace is the-loop's, so a repository hook
can never shadow `validate-artifacts` — and a chain printed anywhere says whose code is about
to run.

## Declare it

In your [CLI config](/config/cli/routing-options#graph-hooks):

```yaml
routing:
  graph:
    hooks:
      modules:
        - path: .the-loop/hooks/house_rules.py     # a .py file inside each checkout
        - module: acme_loop_hooks.compliance       # or an installed dotted name
      attach:
        - hook: x-licence-header
          node: implementation
          boundary: exit                           # entry | exit (default exit)
        - hook: x-arch-signoff
          node: design
          with: {board: platform}                  # reaches the hook as ctx.params
```

A `path` resolves against each checkout the loop walks, so one declaration serves every
repository this instance drives. `the-loop graph hooks` prints what is declared **without
importing any of it**; `the-loop check <work item>` is what loads it.

## What a hook of your own can and cannot do

| It can | It cannot |
|---|---|
| Block a node (`HookResult.blocked`) | Unblock one — it is appended *after* every shipped hook, and the chain short-circuits at the first that does not pass |
| Keep a node waiting (`waiting`) or decline to run (`skipped`) | Declare an `outcome` — the value is dropped with a warning, so it can neither approve a gate nor choose an edge |
| Read the repository, the work item and the node | Take a name outside `x-`, or replace/reorder/remove a shipped hook |
| Ship as a file in the checkout or an installed package | Be loaded from outside the checkout — an absolute path, a `..` escape or a symlink out is refused |

## Failures are load failures

A module that is missing, unreadable, raises on import, registers nothing, or registers the
wrong name **fails the graph load**, naming the declaration. So does an attachment pointing at
a node the loop does not declare, or a hook nothing registered. Nothing degrades to "no
hooks": a compliance gate that silently stopped running is the failure this design is built
against. At run time, a hook that raises is a `block` with `retriable=False`, exactly as a
shipped one is.

## Before you adopt one

Hook modules are **imported into the-loop's own process**, with its environment. Adopting
one is adopting its code — review a hook module the way you review anything else that runs
with your credentials in scope. That is why the declaration is yours and not a
repository's: a checkout that carries a hook module you never declared has nothing run
(issue-352), so there is no machine-wide refusal switch any more — the former
`routing.graph.repoHooks` is stripped by `the-loop migrate-config`.

Modules are imported **once per process**: a daemon picks up an edited hook module on its
next start.

## Lifecycle hooks

Since [issue-344](https://github.com/MadaraUchiha-314/the-loop/issues/344) there is a
second place to attach: not a node boundary but **an event the-loop records**. Every type
[`the-loop events --types`](/cli/commands/events) lists is an attach point — `session.spawned`
when work starts, `work_item.ended` when it finishes, and every dispatch, control keyword,
PR spawn and channel post between ([decision-124](/decisions/decision-124)). A lifecycle
hook **observes**: it runs off one worker thread after the record is written, can never
block what emitted it, and can never move the graph. A veto is a graph hook.

### Write it

```python
# ~/.the-loop/hooks/telemetry.py
from the_loop.graph import HookResult, hook
from the_loop.lifecycle_hooks import LifecycleEvent


@hook("x-otel-span")
def otel_span(event: LifecycleEvent) -> HookResult | None:
    span = {"name": event.event, "work_item": event.work_item, **event.params}
    span.update(event.fields)          # the record's per-type fields, e.g. session, node
    my_exporter.send(span)             # your code; a raise is recorded, never fatal
    return None                        # or HookResult.ok(...) — both are success
```

Same decorator, same result type, same `x-` rule. `event` carries the record's envelope
(`event`, `level`, `ts`, `source`, `pid`), its `fields`, the attachment's `with` as
`params`, and the instance name; `event.record()` is the whole line the log holds.

### Declare it

```yaml
hooks:                                        # top-level, beside `critics`
  modules:
    - path: hooks/telemetry.py                # relative to THIS FILE's directory
  lifecycle:
    - hook: x-otel-span
      on: [session.spawned, session.closed, graph.*]
      with: {service: the-loop}
    - hook: forward-event                     # shipped: POST the record, no Python
      on: "work_item.*"
      with: {url: https://telemetry.example/loop, tokenEnv: ACME_TELEMETRY_TOKEN}
```

`the-loop hooks` prints what is declared — and which events each pattern matches —
**without importing any of it**. The block is the operator's for the same reason the
graph block is; see [hook options](/config/cli/hooks-options).

### Graph hook or lifecycle hook?

| | Graph hook (`routing.graph.hooks`) | Lifecycle hook (`hooks`) |
|---|---|---|
| Attaches to | a node boundary (`entry` / `exit`) | an event type or pattern (`session.*`) |
| Receives | `HookContext` — the node, the artifacts, the graph | `LifecycleEvent` — the record, `params`, the instance |
| Runs | inside the chain, synchronously, before the pointer moves | off one worker thread, after the record is written |
| Can | block or park the node | observe; fail (`hooks.failed`) |
| Cannot | approve a gate, choose an edge | affect the event, the dispatch or the graph at all |
| `path` resolves against | each checkout the loop walks | the CLI config file's directory |
| Shipped hooks attachable | no — that would edit the process | yes (`forward-event`) |
| Shared | `@hook("x-…")`, `HookResult`, the loader, the `x-` rule, load-or-fail | |

## See also

- [`the-loop graph hooks`](/cli/commands/graph#hooks) — what your config declares for the
  graph; [`the-loop hooks`](/cli/commands/hooks) for the lifecycle.
- [hook options](/config/cli/hooks-options) and
  [lifecycle-hooks](/capabilities/lifecycle-hooks) — the lifecycle block and the capability.
- [process-graph](/capabilities/process-graph) — the hook contract and the shipped hooks.
- [routing options](/config/cli/routing-options#graph-hooks) — where `routing.graph.hooks`
  lives, and why it is the operator's.
- [decision-096](/decisions/decision-096) — the trade-offs behind the four rules.
