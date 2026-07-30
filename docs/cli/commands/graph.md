# `graph`

Inspect and drive the-loop's [process graph](/capabilities/process-graph) — the PDLC as an
executable graph of nodes with entry and exit hooks, rather than a set of labels somebody
remembers to move.

```bash
the-loop graph [--repo .] show   [--format text|json]
the-loop graph [--repo .] status <work-item>
the-loop graph [--repo .] advance <work-item> [--ref REF]
the-loop graph [--repo .] run    <work-item> [--ref REF] [--max-nodes 20] [--dry-run]
the-loop graph [--repo .] force  <work-item> --to NODE --reason TEXT [--actor WHO] [--ref REF]
```

`--repo` (default `.`) precedes the action.

::: tip You usually will not need this
With [`routing.graph.enabled`](/config/cli/routing-options#graph-enabled) — on by default —
the ingress drives the graph for you: a spawn enters the start node, and a delivered event
advances at most one node boundary. `graph` is for looking, for CI, and for the times the
automation needs overriding.
:::

## `show`

Print the shipped graph: every node with its flags (`required`, `human`, `terminal`) and the
edges leading out of it.

```text
$ the-loop graph show
graph v1, start: brainstorming
  brainstorming
      --pass--> requirements-definition
  requirements-definition
      --pass--> requirements-approval
  requirements-approval  [human]
      --approved--> design
      --approved-with-comments--> design
      --changes-requested--> requirements-definition
  design
      --pass--> design-approval
  …
```

Note the human-gate shape: `approved-with-comments` takes the **same** edge as `approved`,
so a reviewer's suggestions never block the phase — they are recorded and carried forward.

| Flag | Default | Meaning |
|------|---------|---------|
| `--format` | `text` | `text`, or `json` for the full node/edge model. |

## `status`

Where a work item is, with each reached node's verdict and messages. Nodes beyond the
pointer are summarised as "not reached yet" rather than reported as failures.

Exit `0` when satisfied, `1` when not.

## `advance`

Evaluate the current node and take the matching edge — **one** boundary.

| Flag | Default | Meaning |
|------|---------|---------|
| `--ref` | `""` | Work-item ref for integrations, e.g. `github:OWNER/REPO#N`, so hooks that post or label know where. |

Prints `<work-item>: <node> → <status>` plus any messages. Exit `0` for `pass` or `wait`,
`1` otherwise.

## `run`

Advance repeatedly until the work item waits, escalates, blocks, or reaches a terminal node.

| Flag | Default | Meaning |
|------|---------|---------|
| `--ref` | `""` | As above. |
| `--max-nodes` | `20` | Safety bound on advances. |
| `--dry-run` | off | Report what would happen, writing no state. |

::: warning Why the bound exists
A runaway loop is the one failure mode a deterministic driver can still have, so it gets an
explicit ceiling rather than trust. `run` also detects revisiting the same node more than
twice and stops, saying so.
:::

Exit `0` when it stops at a `wait` or completes; `1` when it stops at `block` or `escalated`.

## `force`

The authorized-operator escape hatch: move a work item's pointer to a node **regardless of
gates**.

| Flag | Required | Meaning |
|------|----------|---------|
| `--to` | yes | Target node id. |
| `--reason` | yes | Why. There is no unexplained force. |
| `--actor` | no | Who is forcing it. |
| `--ref` | no | Work-item ref for integrations. |

::: danger It moves the pointer; it does not forge a verdict
`force` never writes a passing verdict for the gate it bypassed. The command says so on
every run:

```text
note: this moved the pointer only — the bypassed gate keeps its real verdict,
so `the-loop check --recompute` will still report it.
```

So a forced work item cannot quietly launder an unmet requirement into a satisfied one. The
force is recorded, and [`check --recompute`](/cli/commands/check#recompute) still tells the
truth.
:::

A refused force — an unknown node, a missing reason — exits `2` with `refused: <why>`, and
nothing moves.

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Satisfied, waiting, or completed |
| `1` | Unmet, blocked, or escalated |
| `2` | Could not run, or the force was refused |

## See also

- [`check`](/cli/commands/check) — the read-only, pure evaluation of the same runtime.
- [Routing options → `graph`](/config/cli/routing-options#graph-enabled) — coupling the
  ingress to the graph.
- [process-graph](/capabilities/process-graph) — the capability doc.
