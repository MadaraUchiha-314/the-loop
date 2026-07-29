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

### The hook contract

- Every hook SHALL have one signature — `(HookContext) -> HookResult` — where
  `HookResult` carries `status` (`pass|block|wait|skip`), the hook's name, ordered
  `messages`, free-form `data`, and `retriable`.
- Hooks SHALL be discovered through a name registry (`@hook("validate-artifacts")`),
  mirroring the CLI's existing `Command`/`@register` pattern, so the shipped graph refers
  to hooks by name and never by import path.
- A chain SHALL **short-circuit** on the first non-`pass` result. Aggregation is therefore
  the *hook's* job: a validating hook reports every finding in one result rather than
  failing on the first and hiding the rest — a gate that reveals problems one at a time
  is a gate people learn to route around.
- A hook that raises SHALL become a `block` with `retriable=False`, never a silent pass.
- Hook results SHALL carry secret **handles**, never secret values (R2.7).

### Shipped hooks

`validate-artifacts` · `lint-artifacts` · `verify-tests` · `set-phase-label` ·
`log-entry` · `request-review` · `notify` · `classify-feedback` · `record-feedback` ·
`mcp-call`.

- `validate-artifacts` SHALL check front matter, required sections and the security
  boundary mapping (`enforces-boundaries-from`) — the design's Security design section
  must answer every abuse case the requirements raised.
- `classify-feedback` SHALL turn a human's free-text review into one of the decisive
  outcomes via a schema-constrained harness call, and SHALL only accept feedback from
  **authorized authors**; anything indecisive keeps the gate `wait`ing rather than
  guessing (negative test: an unauthorized author's "lgtm" does not advance the node).
- `record-feedback` SHALL append approve-with-comments feedback to the artifact's own
  `## Review comments` section, append-only and attributed. An approval never silently
  discards a reviewer's suggestions, and the feedback travels with the document it
  concerns instead of living in a side-channel tracker.

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

### What drives the graph (issue-113)

- The graph SHALL be driven by the **ingress**, not only by a human at a terminal: the
  shared dispatcher — which both the webhook receiver and the poller feed — SHALL enter a
  work item's start node when a session is spawned for it, and SHALL advance it at most
  one node boundary when an event is delivered to an existing session.
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
| issue-113 | Wired the ingress to the graph: `Runtime.start()`, the `GraphLink` seam in the shared dispatcher, `HookContext.event` finally written, the `routing.graph` config block, and the chain-outcome fix that lets a passing gate's verdict reach its edges | [spec](../specs/issue-113/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/113) |
| issue-109 | Established the capability: the two-concept graph (node + hook), the `HookResult` contract, the shipped PDLC graph, ten hooks, configurable integration transports, `the-loop check`/`graph`, and the forced-transition escape hatch | [spec](../specs/issue-109/), [decision-041](../decisions/decision-041.md), [decision-042](../decisions/decision-042.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/109) |
