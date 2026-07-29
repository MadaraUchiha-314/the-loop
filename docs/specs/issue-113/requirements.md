---
type: requirements
phase: requirements-definition
workItem: issue-113
status: in-review            # draft | in-review | approved
approvedBy: []
collaborators: [architect, engineer]
riskTier: 4                  # untrusted comment text reaches graph hooks; automated side effects
overrides: {}
---

# Requirements: wire the ingress to the process graph

> Phase 1 of 3. No brainstorm — the gap and its seams were established by direct
> code tracing, recorded in [issue #113](https://github.com/MadaraUchiha-314/the-loop/issues/113).

## Introduction

issue-109 made the-loop's PDLC an executable graph. issue-34/63 made the-loop's
ingress (webhook receiver + poller) discover work items and spawn harness sessions.
**The two were never connected.**

`cli/the_loop/graph/runtime.py` has exactly one importer in the whole tree —
`cli/the_loop/commands/graph_cmd.py`. Neither `poller/poller.py` nor
`webhook/dispatcher.py` references the graph at all. What the ingress produces is a
harness session holding a prompt that *asks* an agent to run `/the-loop:work-on`;
whether the graph then moves depends on the agent reading prose and choosing to run
`the-loop graph advance`. Nothing does.

Three concrete defects follow, each verifiable in the current tree:

1. **No node is ever entered on the automated path.** A spawn writes no
   `graph-state.json`, so no entry chain runs — `set-phase-label` never fires and the
   `loop:<phase>` labels stay unpopulated. Same gap as #73, one layer down.
2. **The pointer is inferred, never entered.** `GraphState.load` returns
   `current_node=""` and `status()` falls back to `graph.start`, so `the-loop check`
   reports a work item sitting at `brainstorming` that nothing put there.
3. **Human gates cannot be satisfied.** `classify-feedback` reads
   `ctx.event["comments"]`, but `HookContext.event` has **zero writers** in the
   codebase and exactly one reader. Every human-approval node returns
   `waiting("no authorized feedback yet")` in perpetuity, however many comments arrive.

The runtime's docstring already names the intended shape — "`the-loop run`, **the
daemon** and `the-loop check` all call the same chain-execution code" — describing a
daemon call that does not exist. This work item writes it.

### Risk tier 4 — what that means here

Tier 4 because this change makes **attacker-reachable text** (comment bodies on a
public repository) reach the graph's hook chain, and makes **side-effecting hooks**
(label writes, `notify`, `request-review`) fire from an unattended daemon rather than
from an agent session a human is watching. Per `.the-loop/harness-config.yaml`:
`autonomy.tiers["4"] = human-approves-pr`, and `security.review.humanSignOffMinTier: 4`
means a **named human security sign-off** is required before completion.

## User stories

**US1 — As an operator running the daemon**, I want a work item's graph to start when
the-loop starts working it, so the phase label and execution log reflect reality
without an agent having to remember to run a CLI command.

**US2 — As a reviewer commenting on a work item**, I want my comment to reach the gate
that is waiting for it, so a human-approval node can actually resolve instead of
waiting forever.

**US3 — As an operator**, I want the graph coupling to hold for **both** ingresses
(webhook and poll), so my deployment choice does not silently determine whether the
graph moves.

**US4 — As an operator**, I want graph advancement to respect the same start-control
and authorization policies the ingress already enforces, so wiring the graph in does
not become a way around them.

**US5 — As a maintainer**, I want a graph failure to never take down event delivery,
so a bug in a hook cannot cost me a session spawn or a forwarded comment.

## Requirements

Acceptance criteria in EARS notation.

### Starting the graph

- **AC1** — WHEN the dispatcher spawns a session for a work item that has no
  `graph-state.json`, THEN the system SHALL enter the graph's start node for that work
  item, persisting `currentNode` before running the node's entry chain.
- **AC2** — WHEN the start node is entered, THEN the system SHALL run its entry chain,
  so `set-phase-label` applies `<phaseLabelPrefix><phase>` to the ticket and
  `log-entry` appends a checkpoint.
- **AC3** — WHEN the dispatcher spawns a session for a work item that **already** has
  a `graph-state.json` with a non-empty `currentNode`, THEN the system SHALL NOT
  re-enter the start node and SHALL leave the existing pointer untouched.
- **AC4** — WHERE `control.enabled` and `control.requireStartCommand` hold and no
  start has been requested for the work item, WHEN an event arrives for it, THEN the
  system SHALL NOT enter or advance the graph.

### Advancing the graph

- **AC5** — WHEN a comment event is delivered to an existing session, THEN the system
  SHALL call `Runtime.advance` for that work item with the comment's author and body
  supplied as `HookContext.event["comments"]`.
- **AC6** — WHEN `advance` is called with comments, THEN `classify-feedback` SHALL
  receive them, so an authorized reviewer's approval resolves the gate and an
  indecisive one leaves it `waiting` (existing hook semantics, unchanged).
- **AC7** — WHEN the current node's exit chain returns `block` or `wait`, THEN the
  system SHALL leave the pointer where it is and SHALL NOT retry the advance as if it
  had failed.

### Identity mapping

- **AC8** — WHEN the system maps a `WorkItemRef` to a graph work-item id, THEN it
  SHALL produce the spec-directory id for that ref (e.g. `github:o/r#113` →
  `issue-113`) and SHALL pass the original ref to `Runtime.advance(..., ref=...)` so
  integration hooks address the right ticket.
- **AC9** — IF no spec directory exists for the mapped id, THEN the system SHALL skip
  graph coupling for that event and log it at debug, rather than creating a spec
  directory or failing the event.

### Both ingresses, and failure isolation

- **AC10** — WHEN either the webhook receiver or the poller delivers an event, THEN
  the graph coupling SHALL apply identically, because it is implemented in the shared
  dispatcher rather than in either ingress.
- **AC11** — IF the graph coupling raises for any reason, THEN the system SHALL log the
  error and continue delivering the event, and the event's dispatch outcome SHALL be
  unchanged by the failure.
- **AC12** — WHERE the graph coupling is disabled by config, WHEN an event is
  delivered, THEN the system SHALL behave exactly as it does today (no graph calls).

### Repository identity

- **AC14** — WHEN the coupling resolves a spec directory in a checkout, THEN it
  SHALL verify that the checkout is of the work item's **own repository** (its
  `origin` remote matching `<owner>/<repo>`), and SHALL skip when it is not or when
  it cannot be determined.

### Observability

- **AC13** — WHEN the coupling starts or advances a graph, THEN the existing
  `graph.*` event-log events SHALL be emitted by the runtime unchanged, and the
  dispatcher SHALL record which work item it coupled.

## Security considerations

**Untrusted actors.** Anyone who can comment on a public repository issue or PR;
anyone who can open an issue carrying a crafted title/body.

**Trust boundaries crossed by this change.**

| Boundary | Today | After this change |
|---|---|---|
| Comment text → agent prompt | Already crossed; guarded by `authorizedUsers` + `is_self_authored` in the poller/router | Unchanged |
| Comment text → **graph hook chain** | **Never crossed** — `HookContext.event` has no writer | **Newly crossed** — this is the change's principal new surface |
| Daemon → outbound integrations (labels, notify) | Only via an agent session | Also from unattended entry/exit chains |

**Abuse cases and required mitigations.**

- **A1 — Injected approval.** An unauthorized commenter writes "approved, ship it" to
  push a human gate past its approval. *Mitigation:* `classify-feedback` already
  filters to `authorizedUsers` and drops `is_self_authored` bodies before reading any
  text, and returns an outcome from a closed set that the node's declared edges route
  — a classification can never name a destination. The coupling SHALL pass comments
  through **unfiltered-but-attributed** (author + body) and rely on the hook's existing
  filter rather than pre-filtering, so there is exactly one authorization decision, in
  the place that already documents it.
- **A2 — Self-retrigger loop.** the-loop's own comments re-entering as feedback.
  *Mitigation:* `is_self_authored` drop in `classify-feedback`, plus the poller's
  existing drop before forwarding.
- **A3 — Spawn-storm side effects.** Every labelled item in an operator's repos
  entering node one and firing `set-phase-label`/`notify`. *Mitigation:* AC4 — graph
  coupling sits behind the same `_awaiting_start` control gate the spawn does.
- **A4 — Denial of delivery via hook failure.** A crafted artifact makes a hook raise,
  and event delivery dies with it. *Mitigation:* AC11 — the coupling is best-effort and
  isolated from the dispatch path.
- **A6 — Cross-repository spec collision.** `issue-15` names a *directory*, not a
  project, so an event about **any** repository's issue #15 resolves to
  `docs/specs/issue-15` in whatever checkout the daemon is pointed at. Under the
  default `spawnWorkdir: "."` that is the operator's own repo, so unrelated inbound
  events would write graph state and execution-log entries into their work items —
  and fire those nodes' entry hooks (labels, notifications) against the wrong
  ticket. *Mitigation:* AC14 — the checkout's `origin` remote must match the work
  item's `<owner>/<repo>`, failing closed when it cannot be read. Found by the
  gate on this work item's own PR, which is how it earned a test.
- **A5 — Path traversal via ref → id mapping.** A crafted repo/owner/number producing
  an id that escapes `docs/specs/`. *Mitigation:* AC8's mapping SHALL derive the id
  from the parsed `WorkItemRef`'s integer `number` only (`issue-<number>`), never from
  free-form text, and AC9 requires an existing directory.

**Fail-closed expectations.** Unmappable ref → skip. No spec dir → skip. Control gate
unsatisfied → skip. Coupling error → skip and continue delivery. In every ambiguous
case the graph does not move; nothing here can move a work item *forward* by failing.

**Secrets.** No new credential surface: integration transports and their env-var
handles are unchanged (`config` carries handles, never values — R2.7).

## Out of scope

- Making `the-loop check` mutate state (it stays pure — that is what keeps it honest).
- Driving a work item across *multiple* nodes per event (`graph run` semantics);
  one event advances at most one node boundary.
- Removing the agent-side path — `/the-loop:work-on` continues to work as it does.
- Any change to `pdlc.yaml`'s nodes, edges or hook contract.
