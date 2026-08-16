# `check`

Evaluate a work item's [process-graph](/capabilities/process-graph) nodes against its
checked-in artifacts, and report what is unmet.

```bash
the-loop check <work-item> [--repo .] [--format table|json]
                           [--recompute] [--fail-on unmet|block]
the-loop check --all       [--repo .] [--format table|json]
```

```text
$ the-loop check issue-117
issue-117: ok (at brainstorming)
  ····   7 node(s) not reached yet
```

A work item that has not been driven through the graph sits at the start node with
everything ahead of it "not reached yet" — which is `ok`, not a failure. When something
at or before the pointer *is* unsatisfied, it is named with its status and its reasons:

```text
issue-42: UNMET (at design-approval)
  WAIT   design-approval
         · waiting on a human gate
  ····   4 node(s) not reached yet
```

## It is pure

No network. No subprocess. No mutation.

That is what lets the **same code** run on every harness turn *and* in CI — so the gate is
the runtime itself, rather than a reimplementation of it that drifts from it. It is also why
`check` is safe to run in a loop, on someone else's branch, or on a work item you know
nothing about.

## Flags

| Flag | Default | Meaning |
|------|---------|---------|
| *(positional)* | — | Work item id, e.g. `issue-117`. Give this or `--all`. |
| `--repo` | `.` | Repository root. |
| `--all` | off | Evaluate **every** work item under the spec root and report drift. |
| `--format` | `table` | `table` or `json`. |
| `--recompute` | off | Ignore stored graph state; derive the verdict from the artifacts alone. |
| `--fail-on` | `unmet` | What makes the process exit non-zero — see below. |

## `--fail-on`: asking versus gating

The two modes exist because "where does this stand?" and "should CI go red?" are different
questions.

### `unmet` (default)

Anything not satisfied, **a human-wait included**. What you want when you are *asking* where
a work item stands.

### `block`

Only a node an **agent can actually fix**. What an automated gate wants.

A work item parked at a human-approval node is the normal state of an open PR. Failing CI
for that would make the gate red by construction — and a gate that is always red is one
people learn to merge past.

```bash
the-loop check "issue-$(git branch --show-current | grep -oE '[0-9]+$')" --fail-on block
```

### A repository that is not there fails both modes

```console
$ the-loop check issue-1 --repo /typo --fail-on block
issue-1: UNREAD — /typo is not a directory
$ echo $?
1
```

Ahead of either rule above, because it is not a verdict about the work item: nothing was
evaluated. The control-plane API deliberately answers a `repo` that does not resolve with
`200` and no position — a checkout somebody cleaned up is expected state on that machine
([issue-238](https://github.com/MadaraUchiha-314/the-loop/issues/238)) — and a report with
no nodes has no *blocking* node either. Without this rule a mistyped `--repo` would take
`--fail-on block` straight to exit 0. **A gate that evaluated nothing has not passed.**

## `--recompute`

Normally `check` trusts the stored graph state where it has one. `--recompute` throws that
away and derives the verdict purely from what is on disk.

Use it to answer "is the recorded state still true?" — after a
[`graph force`](/cli/commands/graph#force), for instance, which moves the pointer **without**
forging the bypassed gate's verdict. A forced work item reads as satisfied under `graph
status` and still reports the real gate under `check --recompute`.

## Reading the output

Nodes are split at the pointer, deliberately:

- Nodes **at or before** the current node are findings — `ok`, `--` (skipped), `wait`
  (blocked on a human) or `BLOCK` (an agent can fix it).
- Nodes **beyond** it are summarised as "not reached yet". A node the work item has not got
  to is *expected* to be unmet; reporting it in the same voice as a genuine blocker is how a
  status view starts contradicting itself, printing `ok` above a wall of `BLOCK` lines.

`--all` prints one line per work item plus the first finding for each, and a
`n/m work items satisfied` summary.

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Nothing failing, per `--fail-on` |
| `1` | At least one work item fails, per `--fail-on` |
| `2` | Could not run — no work item given, or the runtime could not be assembled |

## See also

- [`graph`](/cli/commands/graph) — inspect and **drive** the same runtime.
- [process-graph](/capabilities/process-graph) — nodes, hooks, edges, the human gate.
- [Harness config](/config/harness-config) — the `workflow` settings `check` reads.
