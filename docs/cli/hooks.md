# Adding a hook

A **hook** is the-loop's unit of work at a node boundary: one function, one signature, one
return type. Ten ship with the CLI ([process-graph](/capabilities/process-graph) § The hook
contract). Since [issue-248](https://github.com/MadaraUchiha-314/the-loop/issues/248) a
repository can bring its own — a licence-header check on `implementation`, an architecture
sign-off on `design`, a ping to your change-management system when a work item reaches
`needs-review`.

The graph itself stays the-loop's: a repository cannot declare nodes, edges or loops, and
cannot remove, reorder or replace a shipped hook. What it can do is **append** one of its own
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

In the repository's [harness config](/config/harness-config):

```yaml
graph:
  hooks:
    modules:
      - path: .the-loop/hooks/house_rules.py     # a .py file inside this repository
      - module: acme_loop_hooks.compliance       # or an installed dotted name
    attach:
      - hook: x-licence-header
        node: implementation
        boundary: exit                           # entry | exit (default exit)
      - hook: x-arch-signoff
        node: design
        with: {board: platform}                  # reaches the hook as ctx.params
```

`the-loop graph hooks` prints what a repository declares **without importing any of it**;
`the-loop check <work item>` is what loads it.

## What a repository hook can and cannot do

| It can | It cannot |
|---|---|
| Block a node (`HookResult.blocked`) | Unblock one — it is appended *after* every shipped hook, and the chain short-circuits at the first that does not pass |
| Keep a node waiting (`waiting`) or decline to run (`skipped`) | Declare an `outcome` — the value is dropped with a warning, so it can neither approve a gate nor choose an edge |
| Read the repository, the work item and the node | Take a name outside `x-`, or replace/reorder/remove a shipped hook |
| Ship as a repo file or an installed package | Be loaded from outside the repository — an absolute path, a `..` escape or a symlink out is refused |

## Failures are load failures

A module that is missing, unreadable, raises on import, registers nothing, or registers the
wrong name **fails the graph load**, naming the declaration. So does an attachment pointing at
a node the loop does not declare, or a hook nothing registered. Nothing degrades to "no
hooks": a compliance gate that silently stopped running is the failure this design is built
against. At run time, a hook that raises is a `block` with `retriable=False`, exactly as a
shipped one is.

## Before you adopt one

A repository's hook modules are **imported into the-loop's own process**, with its
environment. Adopting them is adopting that repository's code — review a hook module the way
you review anything else that runs with your credentials in scope, and remember the
declaration lives in a repo-tracked file precisely so it is reviewable.

An operator refuses the whole mechanism machine-wide with
[`routing.graph.repoHooks: false`](/config/cli/routing-options#graphrepohooks). A repository
that declared hooks is then named in a warning rather than quietly losing its gates.

Modules are imported **once per process**: a daemon picks up an edited hook module on its
next start.

## See also

- [`the-loop graph hooks`](/cli/commands/graph#hooks) — what a repository declares.
- [process-graph](/capabilities/process-graph) — the hook contract and the shipped hooks.
- [harness config](/config/harness-config) — where `graph.hooks` lives, and why.
- [decision-096](/decisions/decision-096) — the trade-offs behind the four rules.
