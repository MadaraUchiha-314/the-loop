# `graph`

Inspect and drive the-loop's [process graph](/capabilities/process-graph) — the PDLC as an
executable graph of nodes with entry and exit hooks, rather than a set of labels somebody
remembers to move.

```bash
# --spec-dir DIR (before the action) names where the specs live; default
# routing.graph.specDir from the CLI config, else docs/specs (issue-352)
the-loop graph [--repo DIR] show   [--format text|json]
the-loop graph [--repo DIR] hooks  [--format text|json]
the-loop graph [--repo DIR] status <work-item>
the-loop graph [--repo DIR] advance <work-item> [--ref REF]
the-loop graph [--repo DIR] complete <work-item> [--node NODE] [--actor WHO] [--ref REF] [--pr N] [--pr-repo OWNER/REPO]
the-loop graph [--repo DIR] run    <work-item> [--ref REF] [--max-nodes 20] [--dry-run]
the-loop graph [--repo DIR] skip   <work-item> --node TOKEN [--node TOKEN…] --reason TEXT [--actor WHO] [--ref REF]
the-loop graph [--repo DIR] force  <work-item> --to NODE --reason TEXT [--actor WHO] [--ref REF]
```

`--repo` precedes the action; unset, it is the current directory (for `status`, see
below). `<work-item>` is the spec-directory id (`issue-194`) or the work item's ref
(`github:OWNER/REPO#194`) — every verb translates a ref to the directory the daemon
writes, `issue-<n>`
([issue #396](https://github.com/MadaraUchiha-314/the-loop/issues/396)).

## Resolving the work-item ref

Graph hooks post comments and set labels on the ticket, so they need a **work-item ref**:
`github:OWNER/REPO#N`. Every verb that runs hooks takes `--ref`, and none of them requires
it — the ref is resolved in three tiers
([issue-194](https://github.com/MadaraUchiha-314/the-loop/issues/194)):

1. **`--ref`, when you pass one.** It always wins, even against a repository that declares
   something else.
2. **Derived** from the checkout's `origin` remote plus the work-item id: `issue-194` in
   a checkout whose remote is `github.com/octo/repo` becomes `github:octo/repo#194`
   (the daemon passes the work item's own repository instead). This is what makes
   `the-loop graph advance issue-194` work with no flags. Until issue-352 this tier read
   `ticketing.github` from the harness config, which the CLI no longer opens.
3. **The bare work-item id**, when neither of the above applies — a project that is not
   GitHub-ticketed, or an id that is not `issue-<n>`. Nothing is guessed: an owner or
   repository name that is not a shape GitHub accepts derives *nothing* rather than
   pointing a comment at the wrong repository.

In case 3 the outbound calls fail, and **they say so**. Outbound hooks are best-effort by
design — a GitHub outage must not wedge a work item at a node — but best-effort never
means silent: a hook that could not do its job adds a warning line to the command's
output and records a `graph.hook_degraded` event for anyone reading
[`the-loop events`](/cli/commands/events) instead of a terminal.

```text
issue-194: phase-selection → wait
  · waiting for an authorized user to choose the phases and reply `the-loop execute`
  · warning: post-phase-selection did not complete: malformed work item ref:
    'issue-194' — expected '[<provider>:]<owner>/<repo>#<number>'. Pass --ref, or run
    from a checkout whose `origin` remote names the repository so the-loop can derive it.
```

The node's status, the edge taken and the exit code are unaffected — the warning reports a
degraded side effect, not a failed verb.

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
selection, into `work-item-state.json` and the portable record; there is deliberately no
config key for it, in either config file. A pull request's own inner loop is never
configurable.

**The row is absent on a contribution** (issue-199). `pdlc-contribution-loop` joins a work
item somebody else is already running: it authors one artifact on that thread and owns no
outer loop whose surface could be placed, so the question is not asked, a
`outer-loop-on-pull-request` row typed into the reply anyway is inert, and the frozen
record carries no surface at all — which reads back as *never asked*, not as *the default
was kept*. The checklist says where the conversation happens instead of offering a box.

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

## `hooks`

Report the **shipped** hooks and the hooks **your CLI config** brings to the graph
([issue-248](https://github.com/MadaraUchiha-314/the-loop/issues/248)) — the declarations
under [`routing.graph.hooks`](/config/cli/routing-options#graph-hooks). Until issue-352 a
repository declared these in its harness config; the CLI reads that file no more.

This action imports nothing. That is its purpose: the hook modules run inside the-loop's
own process, so an operator gets to read what would run **before** running it. `the-loop
check` is what loads them, and a declaration that cannot load fails there rather than
being skipped.

```text
$ the-loop graph --repo /srv/checkouts/app hooks
shipped hooks (21): await-inner-loops, classify-adhoc-reply, classify-feedback, …

this repository declares 1 module(s) and 1 attachment(s) — nothing here has been imported:
  module  .the-loop/hooks/house_rules.py
  attach  x-licence-header → implementation (exit)

`the-loop check <work item>` is what loads them; a declaration that cannot load fails there
rather than being skipped.
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--format` | `text` | `text`, or `json` (`shipped`, `modules`, `attach`) for scripting. |

Writing one of these is [adding a hook](/cli/extending#adding-a-hook). A hook runs only
when the operator's own CLI config declares it under
[`routing.graph.hooks`](/config/cli/routing-options#graph-hooks) — a checkout cannot opt its
own modules in (issue-352).

## `loops`

List every loop this machine can walk — the five shipped loops and any graphs **of your
own** declared under [`routing.graph.graphs`](/config/cli/routing-options#graph-graphs)
([issue-343](https://github.com/MadaraUchiha-314/the-loop/issues/343)) — with the keywords
that arm each (as configured; a disabled one is omitted). The CLI config is read
**strictly**, and every declared graph is **compiled** and checked: the compiler's rules,
the phase vocabulary, every hook attachment that applies to it naming a node it declares,
and its `x-` hooks having a declared module. No hook module is imported, so whether a
module really registers a name is settled when a work item loads the graph.

```text
$ the-loop graph loops
pdlc-work-item-loop  (shipped)
  armed by: the-loop start
pdlc-pr-loop  (shipped, inner loop, one per pull request)
  armed by: —
pdlc-contribution-loop  (shipped, guest)
  armed by: the-loop contribute
pdlc-adhoc-loop  (shipped)
  armed by: —
pdlc-review-loop  (shipped, guest)
  armed by: the-loop review
acme-quick-loop  (declared)
  armed by: the-loop do, the-loop triage
  file:     /home/me/.the-loop/graphs/quick.yaml
  compiles: ok
```

A shipped command you bound elsewhere is listed under your graph, not under the shipped
loop (`the-loop do` above).

| Flag | Default | Meaning |
|------|---------|---------|
| `--format` | `text` | `text`, or `json` (`loops[]` with `name`, `kind`, `commands`, `guest`, `inner`, `status`, and for a declared graph `path` and `extensionHooks` or `error`; plus a top-level `error`) for scripting. |

Exits **1** when a declared graph fails a check, or when the CLI config, the
`routing.graph.graphs` list or a keyword it derives cannot be read. See [bringing your own graph](/cli/graphs).

## `status`

Where a work item is, with each reached node's verdict and messages. Nodes beyond the
pointer are summarised as "not reached yet" rather than reported as failures.

```text
$ the-loop --config ~/.the-loop/cli-config.yaml graph status github:octo/repo#1
issue-1: at requirements-approval
  repo: /srv/the-loop/workspaces/octo-repo-1 (from the session registry)
  state: /srv/the-loop/workspaces/octo-repo-1/docs/specs/issue-1/work-item-state.json
  ok     phase-selection
  ok     brainstorming
  …
```

Two lines say **where the answer came from**
([issue #396](https://github.com/MadaraUchiha-314/the-loop/issues/396)), because a
daemon-run work item's state lives in the **session's checkout** — a worktree under
`routing.workspace` — and not wherever you happen to stand:

- `repo:` appears when `--repo` was not given and the current directory does not hold
  the work item: a **ref** is then looked up in the [session registry](/cli/state) and
  the checkout the daemon recorded for its session is reported on. A bare id cannot be
  looked up (the registry is keyed by ref), and `--repo` always wins.
- `state:` names the `work-item-state.json` the report was read from — always. When
  none exists the line says `not found`, and when the state directory is not there
  either, it says so and asks whether this is the work item's checkout: the node printed
  above it is then the graph's start node by default, not a recorded position. Until issue-396 that fallback
  was silent, and `graph status github:…#1` from the daemon's config directory reported
  `phase-selection` for an item three nodes further on.

Only the read verbs (`status`, and [`check`](/cli/commands/check)) resolve a checkout
this way. A mutating verb writes into the checkout it is pointed at, and that stays
your choice: `--repo`, or the directory you run it from.

Exit `0` when satisfied, `1` when not.

## `advance`

Evaluate the current node and take the matching edge — **one** boundary.

| Flag | Default | Meaning |
|------|---------|---------|
| `--ref` | derived | Work-item ref for integrations, e.g. `github:OWNER/REPO#N`, so hooks that post or label know where. Omit it and it is [derived](#resolving-the-work-item-ref) from `ticketing.github`. |

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
| `--ref` | derived | Work-item ref for integrations. [Derived](#resolving-the-work-item-ref) when omitted. |

Output is **one JSON envelope** — `{node, status, outcome, moved, currentNode,
messages, reason}` — and the exit code is `0` whether or not the pointer moved: a
refusal or a block is a result the caller acts on, not a CLI error. The prompt every
driven session receives names this verb, so an agent finishing a phase reports it here
rather than only narrating it.

## `run`

Advance repeatedly until the work item waits, escalates, blocks, or reaches a terminal node.

| Flag | Default | Meaning |
|------|---------|---------|
| `--ref` | derived | As above. |
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
| `--ref` | no | Work-item ref for integrations — where the audit comment is posted. [Derived](#resolving-the-work-item-ref) when omitted; if the comment still cannot be posted, the declaration stands and a `WARNING:` line says so. |

Tokens outside the vocabulary, and nodes the pointer has already entered or passed, are
**rejected** and printed as such — a skip is a plan, not an amnesty. Valid declarations
are recorded in work-item state with provenance, announced on the ticket with the self-marker,
and honoured when the pointer reaches each node: it routes along the node's declared
`on: skipped` edge, runs none of its hooks, and `check` reports the node as
*skipped by declaration* — never as a pass. In the outer loop the vocabulary is **every
phase the work item walks** ([issue-179](https://github.com/MadaraUchiha-314/the-loop/issues/179),
[decision-068](/decisions/decision-068)); the one token it will always reject is
`phase-selection`, the gate that does the selecting — which is what keeps every omission
attributable to the human who declared it.

Exit `0` when at least one declaration landed, `1` when every token was rejected, `2`
when the verb could not run (e.g. an empty `--reason`).

## `repos`

Declare the repositories a work item raises pull requests in
([issue-183](https://github.com/MadaraUchiha-314/the-loop/issues/183),
[decision-127](/decisions/decision-127)). **This is the agent's verb**, not the operator's:
which repositories a change spans follows from `design.md` and `tasks.md`, so it is stated
once those exist — at `tasks-breakdown` or early in `implementation` — and not guessed at
the work item's first gate, where nothing yet says what the change touches.

```bash
the-loop graph repos issue-183 --repository octo/app --repository octo/infra
the-loop graph repos issue-183            # read the current declaration back
the-loop graph repos issue-183 --clear    # declare none
```

| Flag | Required | Meaning |
|------|----------|---------|
| `--repository` | no (repeatable) | A `<owner>/<repo>` this work item contributes code to. **The flags are the full set, not an append**, so re-running corrects a declaration rather than growing it. Omit them all to print what is declared. |
| `--clear` | no | Declare none — the default, and what a single-repository work item wants. |
| `--ref` | no | Work-item ref for integrations. [Derived](#resolving-the-work-item-ref) when omitted. |

The declaration is the **plan**: `await-inner-loops` holds `implementation` until each
declared repository has an inner loop *and* every started loop has finished, which is what
makes a contribution that was planned and never opened distinguishable from one that was
never needed. A session record keyed by repository is the *evidence*, and only exists once
a pull request has been opened — so the two are complements, and neither is derived from
the other.

Bounded twice, both in the shrinking direction:

- **Shape.** Every value goes through the same boundary a repository path crosses anywhere
  in the-loop — at least `<owner>/<repo>`, each segment `[A-Za-z0-9._-]+`, never `.` or
  `..`. The value becomes a directory name under `pr-loops/`, so it is **refused** rather
  than sanitized.
- **The instance's own declaration.** When the CLI config declares `repositories`
  ([issue-348](https://github.com/MadaraUchiha-314/the-loop/issues/348)), a repository
  outside that list is refused, naming the set. Nothing routes events for an undeclared
  repository, so its inner loop would never start and the gate would wait forever — better
  a message now than a hang at `implementation`.

**One bad entry declares nothing**: a partial declaration is a gate waiting on a set nobody
chose. Nothing is written, the refusals are printed, and any previous declaration stands.

Unlike [`skip`](#skip) and [`force`](#force) this posts no ticket comment: it takes nothing
away, and the declaration is a checked-in diff a reviewer reads in the pull request.

Exit `0` when the declaration landed (or was read back), `2` when any entry was refused.

## `force`

The authorized-operator escape hatch: move a work item's pointer to a node **regardless of
gates**.

| Flag | Required | Meaning |
|------|----------|---------|
| `--to` | yes | Target node id. |
| `--reason` | yes | Why. There is no unexplained force. |
| `--actor` | no | Who is forcing it. |
| `--ref` | no | Work-item ref for integrations. [Derived](#resolving-the-work-item-ref) when omitted; a force whose audit comment fails still moves the pointer, and says so as a `WARNING:`. |

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

A work item can also **declare** the repositories it contributes to — see
[`repos`](#repos) below. `await-inner-loops` then holds the outer `implementation` node until each declared
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
