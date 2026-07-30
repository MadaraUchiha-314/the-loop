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
issue-117: UNMET (at implementation)
  WAIT   design-approved
         · design.md status is 'in-review', not 'approved'
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
