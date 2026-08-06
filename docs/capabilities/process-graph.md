# Capability: process-graph

> the-loop's PDLC as an executable **graph**: nodes are the steps, hooks are the checks and
> side effects that run at their boundaries, and declared edges route on hook outcomes.
> Prose describes the process; the graph *is* the process.

## What it is

The runtime under `cli/the_loop/graph/` plus the shipped graph definition
(`cli/the_loop/graph/pdlc.yaml`), surfaced as `the-loop check` and `the-loop graph`.
It exists because before it, the PDLC was enforced only by prompts: there was no event
anywhere in the-loop meaning *"this node of the process completed"*, so there was nowhere
to hang a gate, a notification, or an advance (issue-109, [decision-041](../decisions/decision-041.md)).

There are exactly **two** runtime concepts and **one** contract between them.

## Current behaviour

### The graph

- The PDLC SHALL be declared as data — nodes and edges in
  `cli/the_loop/graph/pdlc.yaml`, versioned and validated against its schema — and the
  runtime SHALL execute that declaration rather than re-deriving the process from prose.
- The graph SHALL be **internal to the-loop**: it ships as package data inside the CLI —
  the thing that executes it, and where every hook it names is registered — and a consuming
  repository does not define or override it. A repo-local `.the-loop/graph.yaml` SHALL be
  ignored with a warning, so that user-authored graphs can be enabled later as a deliberate
  feature rather than arriving as an accidental one (R1.5).
- A **node** SHALL be one step of the process, with an ordered `entry` hook chain and an
  ordered `exit` hook chain. A node is **complete** when its exit chain all passes,
  **waiting** when a hook returns `wait`, and **blocked** when a hook returns `block`.
  No prose is parsed to decide this.
- A node MAY be declared `optional` (skipped when its artifact is absent — brainstorming)
  or `required` (never skippable, even by an optional-looking gate — security review,
  human approval).
- An **edge** SHALL route on a hook **outcome** only (`on: pass`, `on: changes-requested`,
  …). There is no expression language: the LLM produces facts, declared edges route on
  them. That split is what makes judgement and determinism coexist.

### What a node `produces`

- A `produces` entry SHALL name an **artifact**, not a filename. It MAY accept several
  names separated by `|` — `produces: ["requirements.md|bugfix.md"]` — because one artifact
  can legitimately go by more than one name: a bug's phase-1 spec is called `bugfix.md`
  ([decision-045](../decisions/decision-045.md)).
- **Exactly one** accepted name may be present. None SHALL block with a message naming
  *every* accepted name, so an agent knows what it is allowed to write; more than one
  SHALL block as **ambiguous**, because two artifacts filling one slot have no defined
  source of truth and a gate that quietly picks one can approve the stale one.
- An artifact found under an alternative name SHALL be held to the **identical** standard —
  `locked`, `frontMatter`, `sections`, `checkmarks`. The name is what is flexible; the bar
  is not.
- An entry with an empty alternative (`a||b`, `|a`, `a|`) SHALL fail at **graph-compile
  time**, naming the node and the entry — every structural failure is a startup failure.
- The entry SHALL be reported verbatim by `the-loop graph show`, unsplit, so the output
  states what the graph declares rather than claiming two artifacts where it means one.
- `enforces-boundaries-from`'s `upstream` SHALL resolve the same way; when several accepted
  names are present their bodies are joined rather than one being chosen, so a boundary
  raised in either still has to be answered downstream.
- The names the graph gates, the names `.the-loop/manifest.yaml` tracks and the templates
  under `skills/the-loop/templates/` SHALL agree, enforced in both directions by
  `cli/tests/test_graph_parity.py` — including that a bundled template offers every section
  the node it is authored for requires.

### What a node `validates` (issue-167)

`produces` means *this node authored it*. A node that gates an artifact it did **not**
author — the six review-chain nodes each own one section of the shared
`execution-log.md` — declares it on the hook entry instead
([decision-063](../decisions/decision-063.md)):

```yaml
exit:
  - {hook: validate-artifacts, with: {validates: execution-log.md, sections: ["Security review (gate)"]}}
```

- `validates` SHALL be a **hook parameter**, not a node field: it describes one assertion,
  not the node's ownership, and only `validate-artifacts` reads it.
- It SHALL resolve through the **same** resolver as `produces`, so alternation, the
  absent-artifact block and the two-files-one-slot ambiguity block are identical for both
  and cannot drift apart. Every declared check (`locked`, `frontMatter`, `sections`,
  `checkmarks`) applies to a validated artifact exactly as to a produced one.
- A validated artifact that is **absent** SHALL block, naming the file. It is never a skip:
  the node asserted the file would be there.
- **A gate with nothing to read SHALL fail closed.** When a `validate-artifacts` entry
  declares any content check and resolves *no* artifact — neither `produces` nor
  `validates` — it SHALL `block`, and the block SHALL be **not retriable**: re-running a
  node cannot repair the graph that declared it, and a retriable block would burn
  `maxAttempts` before anyone was told.
- `cli/tests/test_graph_parity.py`'s **P5** SHALL enforce all three questions against the
  shipped graph: every content gate resolves a target (P5a), every validated name is
  tracked by the manifest (P5b), and every section it demands exists in that artifact's
  bundled template (P5c).
- What this proves SHALL be stated rather than implied: the section check is **structural**,
  so a heading holding placeholder text passes it. The gate proves the *record exists*; the
  reviewer judges whether the review was any good.

Before this, those six nodes declared `sections:` and no artifact at all — so their
`validate-artifacts` resolved nothing, returned *skipped*, and (a skip not being a
decision) the chain passed straight through every one of them, `security-review`
included, however empty the log was.

### The hook contract

- Every hook SHALL have one signature — `(HookContext) -> HookResult` — where
  `HookResult` carries `status` (`pass|block|wait|skip`), the hook's name, ordered
  `messages`, free-form `data`, and `retriable`.
- Hooks SHALL be discovered through a name registry (`@hook("validate-artifacts")`),
  mirroring the CLI's existing `Command`/`@register` pattern, so the shipped graph refers
  to hooks by name and never by import path.
- A chain SHALL **short-circuit** on the first result that is neither `pass` nor `skip`.
  Aggregation is therefore the *hook's* job: a validating hook reports every finding in
  one result rather than failing on the first and hiding the rest — a gate that reveals
  problems one at a time is a gate people learn to route around.
- **A `skip` SHALL NOT be a decision** (issue-163): a hook that declines to run has said
  nothing about the node, so the chain continues past it and, if nothing objects, the
  node passes on the outcome `pass`. Short-circuiting on `skip` hid the hooks behind a
  skipping one and routed a chain ending in a skip on the outcome `"skip"`, for which no
  edge is declared — which is why `implementation` (whose chain ends in a `verify-tests`
  that is a no-op unless a command is bound) parked at `no_edge` instead of advancing.
- A hook that raises SHALL become a `block` with `retriable=False`, never a silent pass.
- Hook results SHALL carry secret **handles**, never secret values (R2.7).

### Shipped hooks

`validate-artifacts` · `lint-artifacts` · `verify-tests` · `set-phase-label` ·
`log-entry` · `request-review` · `notify` · `classify-feedback` · `record-feedback` ·
`mcp-call`.

- `validate-artifacts` SHALL check front matter, required sections and the security
  boundary mapping (`enforces-boundaries-from`) — the design's Security design section
  must answer every abuse case the requirements raised.
- The `design` node's `validate-artifacts` SHALL require **Architecture**,
  **Module structure**, **Security design** and **Testing strategy**. `Module structure`
  (issue-164, [decision-064](../decisions/decision-064.md)) is where the delivered code will
  land — the tree of paths the work item creates, changes or removes. It is a gate condition
  rather than a template suggestion for the reason issue-124 and issue-148 both recorded: a
  rule the graph does not hold is a rule that goes missing. A work item that changes no code
  says so in one sentence, which is non-empty and passes.
- `classify-feedback` SHALL turn a human's free-text review into one of the decisive
  outcomes via a schema-constrained harness call, and SHALL only accept feedback from
  **authorized authors**; anything indecisive keeps the gate `wait`ing rather than
  guessing (negative test: an unauthorized author's "lgtm" does not advance the node).
- `record-feedback` SHALL append approve-with-comments feedback to the artifact's own
  `## Review comments` section, append-only and attributed. An approval never silently
  discards a reviewer's suggestions, and the feedback travels with the document it
  concerns instead of living in a side-channel tracker.

### Testing is planned and verified as nodes (issue-163)

- **`test-planning`** SHALL sit between `design` and `design-approval` and produce
  `testing-plan.md`, gating on the artifact being locked and carrying non-empty
  **Test matrix**, **Verification environment**, **Evidence plan** and **Verification
  results** sections. Placing it *before* the human gate means **one approval covers
  `design.md` and the plan derived from it** — the plan gets human review without a stop
  of its own, and is still locked before the `tasks.md` that references its rows.
  `design-approval` SHALL record feedback into **both** artifacts, because a reviewer's
  note about the test matrix belongs in the plan rather than filed under the design, and
  `changes-requested` SHALL return to `design`, which re-derives the plan. The results heading is gated at *planning* time deliberately:
  `validate-artifacts` treats an empty required section as a finding, so the heading is
  authored up front holding "not yet executed" and the verification node fills a section
  rather than inventing one.
- **`verification`** SHALL sit between `implementation` and `self-review` and re-declare
  the **same** artifact, gating on `checkmarks: complete` plus a non-empty **Verification
  results** section — the produce-then-re-gate shape `implementation` already uses for
  `tasks.md`. Re-declaring `produces` is what makes the gate run at all: a node that
  declares no artifacts gets a *skipped* `validate-artifacts`, which is a gate reporting
  success without running.
- Both nodes SHALL carry their own `phase`, so a work item's ticket label says
  `loop:test-planning` / `loop:verification` rather than hiding the state inside a
  neighbouring phase.
- The plan's content rules — which testing types are candidates, `n/a` **with a reason**,
  the declared-not-managed verification environment, committed and redacted evidence —
  live in [`reference/testing.md`](../../skills/the-loop/reference/testing.md) and the
  bundled template, not in the graph. The graph gates the *shape*; the reviewer judges the
  content.

### The human gate

- A human review/approval step SHALL be a **node**, not a hook. It lasts days rather than
  milliseconds, receives events while it waits, runs an internal iterate-until-locked
  loop, and produces artifacts — none of which a hook's request/response shape can carry.
- A gate node SHALL default to `session: inherit`: it reuses the harness session of the
  node that produced the artifact, so the reviewer's questions land in the context that
  wrote the thing. WHEN that session is gone THEN the gate SHALL fall back to a fresh
  session seeded with the checked-in artifacts — which is exactly the property
  [decision-027](decision-027.md) already relies on.

### Two call planes

- **Control plane** — the-loop's *own* calls to external services (labels, comments,
  notifications) SHALL go through declared integrations whose **transport is
  configurable** (`integrations.<provider>.transport: auto|api|cli|sdk`), so an operator
  picks what suits their environment rather than inheriting the-loop's taste.
- **Work plane** — calls the *agent* makes while doing the work SHALL be unconstrained:
  CLI, MCP or API, whatever the task needs. Constraining the work plane would be
  constraining the engineer.
- Integrations SHALL declare their capabilities and SHALL fail closed at load time when a
  configured transport cannot serve a required operation, rather than at the moment a
  gate needs it.
- WHEN a service is reachable only over MCP THEN the-loop SHALL reach it **by delegation
  to the harness** (`mcp-call`), because MCP is an agent protocol, not a daemon protocol
  ([decision-042](../decisions/decision-042.md)).

### What drives the graph (issue-113, issue-148)

- The graph SHALL be driven by the **ingress**, not only by a human at a terminal: the
  shared dispatcher — which both the webhook receiver and the poller feed — SHALL enter a
  work item's start node when a session is spawned for it (**every spawn enters** —
  issue-148 closed the gap where tmux-hosted spawns never entered), and SHALL advance
  it at most one node boundary when an event is delivered to an existing session.
- **The session drives it too** (issue-148): `the-loop graph complete <id>` is the
  node-completion claim. WHEN a claim arrives THEN the runtime SHALL evaluate the
  current node's exit chain and advance only when it passes; the claim SHALL carry no
  verdict and no event text. Claims name their node: a replay of a claim for a node the
  pointer has left SHALL be a recorded no-op, a claim for a node that is neither current
  nor past SHALL be refused naming the current node, and a claim on an item that never
  entered the graph SHALL be refused. Output is one JSON envelope; a refusal or block is
  a result, not a CLI error. Claims are recorded in the state's `completions` ledger.
- **Graph state is resolved before anything is delivered** (issue-148): the dispatcher
  SHALL resolve a read-only context — current node, phase, status, parked/blocked
  reason, gate messages, the node's `command` — before rendering any prompt, and SHALL
  render it into the `$graph_context` placeholder. A spawn prompt for a mid-graph item
  SHALL say *resume at the current node*; entering the graph (`on_spawn`, the write)
  SHALL still happen only after a successful spawn. Reads before the spawn, writes
  after it.
- **A waiting human gate sees its input first** (issue-148): WHEN an event arrives for
  an item parked at a human-actor node THEN the dispatcher SHALL run `advance` (with
  the event's comments) **before** delivering, and the delivered prompt SHALL carry the
  gate's verdict; the graph SHALL NOT be advanced a second time for the same event.
  There are **no consume-only routes**: every event is still delivered — a gate speaks
  first, never instead. WHEN the gate cannot classify (unauthorized author, indecisive
  text, fault) THEN the event SHALL still be delivered with the gate still waiting.
- **Advancement fails closed; delivery fails open** (issue-148). No input — comment
  text, completion claim, payload — moves the pointer except through an exit chain over
  checked-in artifacts or `classify-feedback` on an authorized author's text. Any
  consultation fault delivers with the context unknown and records `graph.link_failed`.
- Graph state has **two writers** (the daemon's link and the session's claim), so the
  load→mutate→save window SHALL run under an advisory lock (`graph-state.lock`,
  stdlib `fcntl`, no-op where unavailable); a busy lock reports `busy` rather than
  blocking, and a lost update on the no-op fallback costs a re-evaluation, never a
  wrong pointer.
- WHEN a human gate is entered THEN the runtime SHALL resolve its session per
  `session: inherit` — the binding `on_spawn` records (session id, runner — always
  `"tmux"` since issue-156 — alive),
  flipped dead on close, re-recorded on respawn — and SHALL record the resolution as
  `graph.gate_session` (`inherited` or `fresh-with-artifacts`). The registry remains
  the dispatch authority.
- Entering the start node SHALL run its **entry chain**, which is what writes the
  `loop:<phase>` label and the execution-log checkpoint. Before this, no node was ever
  entered on the automated path, so those side effects never fired and the phase labels
  stayed unpopulated.
- An inbound event's comments SHALL be passed to the exit chain as `HookContext.event`,
  so a human-approval node's `classify-feedback` classifies the reply that just arrived.
  The link SHALL always pass a comment's **author** alongside its body and SHALL NOT
  filter by `authorizedUsers` itself — that decision belongs to `classify-feedback`
  alone, so there is exactly one place where it can be got wrong.
- The coupling SHALL be **best-effort and non-blocking**: any failure is logged as
  `graph.link_failed` and the event is still delivered. A hook that raises, hangs on a
  subprocess or fails an outbound call SHALL never cost a session spawn or a forwarded
  comment.
- The coupling SHALL skip — leaving the graph exactly where it is — when it is disabled
  (`routing.graph.enabled: false`), when the ref has no known spec-id convention, when
  the work item has no spec directory, or when `control.requireStartCommand` holds and
  nobody has started the item. **No input can move a work item forward**; inputs can only
  cause a move not to happen.
- **Where the specs are is the work item's own repository's to declare** (issue-123,
  [decision-044](../decisions/decision-044.md)). On the ingress path the coupling SHALL
  resolve the spec directory from the checkout's `workflow.specDir` (default
  `docs/specs`), with `routing.graph.specDir` left as a deliberate override for a checkout
  that carries no harness config — not, as before, as a machine-scoped default that
  silently governed every watched repository. It SHALL resolve that directory **once** and
  use the same value for the skip decision and for the runtime it builds, so the directory
  gated on and the directory `graph-state.json` is written into cannot drift apart.
- That read SHALL happen only **after** `_checkout_belongs_to` has proved via the `origin`
  remote that the directory is the work item's own repository, and a declared value that
  is absolute or resolves outside the checkout SHALL be refused — a value read from a
  repository must not select a write target elsewhere on the operator's machine.
- A skip for want of a spec directory SHALL be recorded as `graph.skipped` in the event
  log (`work_item`, `action`, `reason`, `spec_dir`). A work item that is labelled, armed
  and spawned but whose graph never moves is a question `the-loop events` must be able to
  answer; at `logger.debug` it could not.
- A chain's routing outcome SHALL come from the last hook that declared one explicitly,
  whether or not that hook blocked. A gate that classifies a review returns `pass`
  *carrying* its verdict, so reading the outcome only from a blocking result discarded it
  and parked every human-approval node with `no_edge`.

### State, recovery and the escape hatch

- Graph state SHALL be a **cache, not an authority**. `the-loop check --recompute`
  SHALL ignore stored state and derive each node's verdict from the checked-in artifacts
  alone, which is what makes the CI gate meaningful and drift discoverable.
- `the-loop graph force --to <node> --reason <why>` SHALL move a work item past its gates,
  exercisable by the authorized user running the-loop's CLI. It SHALL require a reason,
  SHALL record the override in four places (graph state, execution log, event log, and a
  marked ticket comment), and SHALL warn about every gate it bypassed.
- **A force moves the pointer. It never forges a verdict.** A bypassed gate keeps its real
  result, so `the-loop check --recompute` still reports it unmet after the force. An
  escape hatch that could rewrite history would be a way to launder an unmet gate into a
  met one.
- Every transition, every non-`pass` hook and every edge taken SHALL be recorded in the
  structured event log (`graph.*` event types; see [observability](observability.md)).

## Design

[`docs/specs/issue-109/design.md`](../specs/issue-109/design.md) ·
[`decision-041`](../decisions/decision-041.md) ·
[`decision-042`](../decisions/decision-042.md) ·
[`reference/workflow.md`](../../skills/the-loop/reference/workflow.md) ·
[architecture](../architecture/architecture.md)

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-164 | The `design` gate gained a fourth required section, `Module structure` — the tree of paths the work item creates, changes or removes — so placement is a claim the graph holds rather than something a reviewer reconstructs from the diff | [spec](../specs/issue-164/), [decision-064](../decisions/decision-064.md), [spec-workflow](spec-workflow.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/164) |
| issue-167 | Six gates stopped reporting success without running: `validate-artifacts` gained `validates:` for an artifact a node asserts against but did not author, so the six review-chain nodes gate their sections of the shared `execution-log.md`; a content gate that resolves no artifact now blocks (not retriable) instead of skipping; the bundled execution-log template gained the `Capability docs` section `capability-docs` had always demanded; P5 asserts all three against the shipped graph | [spec](../specs/issue-167/), [decision-063](../decisions/decision-063.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/167) |
| issue-163 | Testing became two nodes: `test-planning` produces `testing-plan.md` before the task DAG that references it, `verification` re-gates the same artifact after implementation and before the review chain; a `skip` stopped short-circuiting a chain, which is what had left `implementation` parking at `no_edge` | [spec](../specs/issue-163/), [decision-060](../decisions/decision-060.md), [testing-and-contracts](testing-and-contracts.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/163) |
| issue-156 | Process runner removed; tmux is the only runner (2026-08-05): every spawn is tmux-hosted, so "every spawn enters the graph" no longer needs a per-runner qualifier, and the gate-session binding's `runner` is always `"tmux"` | [spec](../specs/issue-156/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/156) |
| issue-148 | The graph went from observer to authority: `the-loop graph complete` (the node-completion claim — idempotent, node-named, never a verdict), `GraphContext` resolved read-only before every delivery and spawn, the `$graph_context` prompt block, consult-first ordering at human gates (no consume-only routes), `resolve_session` gained its caller (`graph.gate_session`), tmux spawns finally enter the graph, two-writer state locking, and P4 phase parity — `pdlc.yaml` defines the sequence, the prose renders it | [spec](../specs/issue-148/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/148) |
| issue-124 | `produces` names an artifact rather than a filename: `\|`-separated alternatives, one resolver shared by every hook that reads them, ambiguity fails closed, malformed entries fail at compile; `enforces-boundaries-from` resolves `upstream` the same way, which turned a security gate that had been silently skipping for every bug work item into one that runs; graph ↔ manifest ↔ template parity is now a test | [spec](../specs/issue-124/), [decision-045](../decisions/decision-045.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/124) |
| issue-123 | The daemon stopped taking `specDir` from the operator's machine: `routing.graph.specDir` defaults to unset, so the work item's own `workflow.specDir` wins; the gate and the runtime resolve one value; the checkout's ownership is proved before its config is read; an escaping value is refused; and the skip is recorded as `graph.skipped` instead of a debug line | [spec](../specs/issue-123/), [decision-044](../decisions/decision-044.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/123) |
| issue-113 | Wired the ingress to the graph: `Runtime.start()`, the `GraphLink` seam in the shared dispatcher, `HookContext.event` finally written, the `routing.graph` config block, and the chain-outcome fix that lets a passing gate's verdict reach its edges | [spec](../specs/issue-113/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/113) |
| issue-109 | Established the capability: the two-concept graph (node + hook), the `HookResult` contract, the shipped PDLC graph, ten hooks, configurable integration transports, `the-loop check`/`graph`, and the forced-transition escape hatch | [spec](../specs/issue-109/), [decision-041](../decisions/decision-041.md), [decision-042](../decisions/decision-042.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/109) |
