# `graph`

Inspect and drive the-loop's [process graph](/capabilities/process-graph) — the PDLC as an
executable graph of nodes with entry and exit hooks, rather than a set of labels somebody
remembers to move.

```bash
the-loop graph [--repo .] show   [--format text|json]
the-loop graph [--repo .] status <work-item>
the-loop graph [--repo .] advance <work-item> [--ref REF]
the-loop graph [--repo .] complete <work-item> [--node NODE] [--actor WHO] [--ref REF] [--pr N] [--pr-repo OWNER/REPO]
the-loop graph [--repo .] run    <work-item> [--ref REF] [--max-nodes 20] [--dry-run]
the-loop graph [--repo .] skip   <work-item> --node TOKEN [--node TOKEN…] --reason TEXT [--actor WHO] [--ref REF]
the-loop graph [--repo .] force  <work-item> --to NODE --reason TEXT [--actor WHO] [--ref REF]
```

`--repo` (default `.`) precedes the action.

::: tip You usually will not need this
With [`routing.graph.enabled`](/config/cli/routing-options#graph-enabled) — on by default —
the ingress drives the graph for you: a spawn enters the start node, and a delivered event
advances at most one node boundary. `graph` is for looking, for CI, and for the times the
automation needs overriding.
:::

## The first phase: `phase-selection`

Every work item now opens here (issue-177). the-loop posts a checklist of the selectable
phases on the ticket; an **authorized** user replies with the ones this item needs and
adds `the-loop execute`. Unticked selectable phases become declared skips; unticked
protected phases are refused and named in the confirmation; a reply with no list runs the
full process.

```text
- [x] brainstorming
- [ ] requirements-definition   ← unticked: this phase will be skipped
- [x] design
…
- [ ] design-critic-review        ← an OPT-IN phase: unticked (the default) = it
                                     does not run. Tick it to add it.

- [ ] outer-loop-on-pull-request  ← not a phase: where the OUTER loop happens.
                                     Unticked (the default) = on the work item.

the-loop execute
```

**Two defaults, in two sections** (issue-188). The rows above the optional block are
*opt-out*: ticked already, and unticking one removes work. An **opt-in** phase — one the
shipped graph marks `optIn` — is listed unticked under its own heading, and ticking it
*adds* work. Leaving it alone, or never naming it, means it does not run; `the-loop check`
then reports it as *not selected*, which is a different fact from *skipped by declaration*
and is never a pass. The outer loop ships one: `design-critic-review`, a different model
reading the locked `design.md` before the testing plan and task DAG derive from it.

**The reply is the signature.** Tick the boxes in place on the-loop's own comment if you
like — that is the natural way to answer — but the tick state is only a *proposal* until
an authorized user says the keyword over it, because GitHub reports that a comment was
edited and never by whom. A checklist inside the `the-loop execute` comment itself wins
over the boxes, for anyone who prefers to be explicit. Either way the gate exists to keep
the harness from choosing its own workload.

The last row is not a phase (issue-183): it says where the **outer** loop is collaborated
on. Leave it and the requirements, design, testing plan and task list are iterated on the
work item itself — the default, so a work item whose code lands in *other* repositories
never opens a pull request here just to hold a discussion. Tick it and they are iterated
on a pull request in this repository instead. The answer is frozen with the phase
selection, into `graph-state.json` and the portable record; there is deliberately no
config key for it, in either config file. A pull request's own inner loop is never
configurable.

## `show`

Print the shipped graph: every node with its flags (`required`, `skippable`, `opt-in`,
`human`, `terminal`) and the edges leading out of it. `opt-in` is printed instead of
`skippable` for a node that is off unless selected — the two share a mechanism, but only
one of them runs by default.

```text
$ the-loop graph show
graph v1, start: phase-selection
  phase-selection  [required, human]
      --selected--> brainstorming
  brainstorming  [skippable]
      --pass--> requirements-definition
      --skipped--> requirements-definition
  requirements-definition
      --pass--> requirements-approval
  requirements-approval  [human]
      --approved--> design
      --approved-with-comments--> design
      --changes-requested--> requirements-definition
  design
      --pass--> design-critic-review
  design-critic-review  [opt-in]
      --pass--> test-planning
      --skipped--> test-planning
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

## `complete`

The node-completion **claim** (issue-148): the working session — or you — says "this
node's work is done", and the graph decides. The current node's exit chain is evaluated
against the checked-in artifacts and the matching edge taken only when it passes. The
claim carries no verdict: claiming completion of unfinished work blocks on exactly what
it would block on anyway.

| Flag | Default | Meaning |
|------|---------|---------|
| `--node` | current | The node being claimed. A claim for a node the pointer already left is a recorded no-op (`already-past`); any other non-current node is refused naming the current one. |
| `--actor` | `cli` | Recorded in the state's `completions` ledger. |
| `--ref` | `""` | Work-item ref for integrations. |

Output is **one JSON envelope** — `{node, status, outcome, moved, currentNode,
messages, reason}` — and the exit code is `0` whether or not the pointer moved: a
refusal or a block is a result the caller acts on, not a CLI error. The prompt every
driven session receives names this verb, so an agent finishing a phase reports it here
rather than only narrating it.

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

## `skip`

Declare phases skipped for a work item ([issue-177](https://github.com/MadaraUchiha-314/the-loop/issues/177),
[decision-067](/decisions/decision-067)) — the operator's shell half of **declared
skips**. The usual half is the loop's own first phase: at `phase-selection` the-loop
posts a checklist on the ticket and an authorized user replies with the phases to keep
plus `the-loop execute`. Either way the *selection* is a human's; the graph fixes the
*vocabulary* (`skippable: true` nodes and shipped skip sets such as `spec-chain`), so
neither a repository nor a session can widen it.

| Flag | Required | Meaning |
|------|----------|---------|
| `--node` | yes (repeatable) | A skippable node id, or a skip-set name. `--node spec-chain` is the whole spec chain including the testing plan — the doc-fix case in one token; `--node review-chain` is the six review nodes. |
| `--reason` | yes | Why. There is no unexplained skip. |
| `--actor` | no | Who is declaring it. |
| `--ref` | no | Work-item ref for integrations — where the audit comment is posted. |

Tokens outside the vocabulary, and nodes the pointer has already entered or passed, are
**rejected** and printed as such — a skip is a plan, not an amnesty. Valid declarations
are recorded in graph state with provenance, announced on the ticket with the self-marker,
and honoured when the pointer reaches each node: it routes along the node's declared
`on: skipped` edge, runs none of its hooks, and `check` reports the node as
*skipped by declaration* — never as a pass. In the outer loop the vocabulary is **every
phase the work item walks** ([issue-179](https://github.com/MadaraUchiha-314/the-loop/issues/179),
[decision-068](/decisions/decision-068)); the one token it will always reject is
`phase-selection`, the gate that does the selecting — which is what keeps every omission
attributable to the human who declared it.

Exit `0` when at least one declaration landed, `1` when every token was rejected, `2`
when the verb could not run (e.g. an empty `--reason`).

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

## `--pr` — addressing a pull request's inner loop

Every verb above (except `run`) accepts `--pr <number>` (issue-172,
[decision-065](/decisions/decision-065)). It selects that pull request's **inner loop** —
`pdlc-pr-loop`, the component-scoped subset of the process, with its state under the work
item's `docs/specs/<id>/pr-loops/pr-<n>/` — instead of the work item's outer
`pdlc-work-item-loop`. A session working a PR claims its nodes with
`the-loop graph complete <work-item> --pr <n>`; omitted, every verb means the outer loop,
exactly as before issue-172. The outer `implementation` node waits (`await-inner-loops`)
until every started inner loop reaches `complete`, so `graph status <id>` shows a work
item held at implementation while its PRs are still in flight, and
`graph status <id> --pr <n>` shows where each PR is.

### `--pr-repo` — a pull request in another repository

A work item's contributions can span repositories (issue-183,
[decision-069](/decisions/decision-069)). The outer loop stays in the **origin**
repository — the one the ticket was created in — and each contributing repository gets one
pull request walking its own inner loop. Since a PR number is unique only within a
repository, an inner loop outside the origin repository is addressed by both:

```bash
the-loop graph complete issue-183 --pr 7 --pr-repo octo/infra
```

Its state lives at `docs/specs/<id>/pr-loops/octo__infra/pr-7/` — still under the **one**
spec chain, in the origin repository's checkout. Omit `--pr-repo` for a pull request in the
origin repository: that keeps the shipped `pr-loops/pr-<n>/` path, so nothing already in
flight moves. `--pr-repo` without `--pr` is refused (a repository does not identify a
loop), as is any value that is not `<owner>/<repo>` — the value becomes a directory name,
so it is validated rather than sanitized.

A work item can also **declare** the repositories it contributes to, in
`docs/specs/<id>/execution-log.md`'s front matter:

```yaml
repos:
  - octo/app
  - octo/infra
```

`await-inner-loops` then holds the outer `implementation` node until each declared
repository has an inner loop *and* every started loop has finished — so a pull request that
was planned and never opened shows up as a held gate naming the repository, rather than as
a pass. Declaring nothing keeps the pre-issue-183 behaviour: every started loop must
finish, and a work item with none passes vacuously.

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
