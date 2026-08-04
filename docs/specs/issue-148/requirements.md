---
type: requirements
phase: requirements-definition
workItem: issue-148
status: draft                # draft | in-review | approved
approvedBy: []
collaborators: [engineer, approver]
riskTier: 5                  # redefines who controls event delivery and phase authority — the operating model itself
overrides: {}
---

# Requirements: the graph runs the PDLC

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (<https://kiro.dev/docs/specs/>). This phase MUST be reviewed and approved by the
> required collaborators before moving to design.

## Introduction

[Issue #148](https://github.com/MadaraUchiha-314/the-loop/issues/148): issue-113 wired
the ingress to the process graph, but only far enough for the graph to **watch**. Two
facts define the gap:

1. **The agent orchestrates the PDLC; the graph records one node of it.** The spawn
   prompt tells the session to run `/the-loop:work-on` and *"follow the-loop's normal
   flow"* — a flow walked from `SKILL.md` prose, not from `pdlc.yaml`. The graph's only
   automated moves are `on_spawn` → `Runtime.start()` (enter node one) and `on_event` →
   `Runtime.advance()` (at most one edge per inbound event). Transitions therefore track
   how many comments arrived, not how much of the PDLC got done: a session that takes an
   item requirements → implementation with no inbound event leaves the pointer — and the
   `loop:` label — on node one.
2. **An event reaches the harness before the graph has any say.** The prompt is rendered
   and delivered first; `graphlink.on_event` runs after, inside the `if ok:` branch. No
   prompt carries the current node, an unmet gate, or a parked reason — the agent reacts
   to a review comment without knowing which node it stands on, and `classify-feedback`
   classifies a comment the agent has already acted on.

The corroborating symptom: `Runtime.resolve_session()` — issue-109's `session: inherit`
contract (R7.3/R7.4) — has **zero callers**. The graph models which session a node runs
in; the registry decides. The model is not in the loop.

## Analysis

### The missing primitive is a node-completion signal

issue-113 built the inbound half: the ingress can tell the graph *an event arrived*. The
outbound half does not exist: the session has no way to tell the graph *this node's work
is done*. Without it, no re-ordering of the existing calls can make the graph drive the
phases — moving `advance` earlier only changes *when* the graph is consulted, not *what
advances it*. Every other requirement in this spec either depends on this signal (R2, R4)
or is about what the graph does with the authority the signal gives it (R3, R5).

The signal must be a **claim, never a proof**. The graph already owns verification — a
node's exit chain evaluates checked-in artifacts (`validate-artifacts`, `verify-tests`,
`classify-feedback`) — so a completion signal is only ever a *prompt to evaluate*, exactly
like an inbound comment is today. This is what preserves issue-113's injection-safety
asymmetry in its stronger, corrected form: **no input moves the pointer forward; only a
passing exit chain over checked-in artifacts does.**

### Pointer-as-authority vs. state-as-cache

`the-loop check --recompute` exists so graph state can never launder an unmet gate into a
met one. That property is about **verdicts**, not **position**, and the two must be
separated to make the pointer authoritative without breaking recompute:

- *Where an item is* (current node) — the pointer's to answer, and after this work item
  it is the **only** thing that answers it: the label and the execution-log phase are
  projections of the pointer, written by the graph's own entry hooks.
- *Whether what came before is met* — always recomputable from artifacts alone,
  unchanged. A force still moves the pointer without forging a verdict.

### Two orderings that are load-bearing today and must survive

- `_apply_control(START)` records the start **before** spawning, because
  `GraphLink._awaiting_start` reads the same store — recording after would make the graph
  skip itself.
- `on_spawn` runs only **after** a successful spawn, so a failed spawn never leaves a
  labelled ticket pointing at a node nobody is standing on.

### What "the graph decides delivery" may and may not mean

The graph gains a say in *what the harness is told* and *what a gate consumes first*. It
must not gain the ability to silently *lose* an event: a webhook delivery or polled
comment that is neither delivered to a session nor visibly recorded as consumed-by-a-gate
would be a regression against the poller's whole retry design (issue-80). Every event has
exactly one of two visible fates: delivered (with graph context), or consumed by a gate
with the consumption recorded.

## Requirements

### Requirement 1 — a node-completion signal exists

**User story:** As the operator of an autonomous work item, I want the working session to
be able to declare a node's work finished so that the graph — not the agent's private
reading of prose — evaluates the gate and advances the process.

#### Acceptance criteria (EARS)

1. WHEN a session working item `<id>` signals completion of the current node THEN the
   runtime SHALL evaluate that node's **exit chain** and SHALL advance along the matching
   edge only when the chain's outcome selects one — identical evaluation semantics to
   `Runtime.advance()` today.
2. WHEN a completion signal arrives THEN the signal itself SHALL carry no verdict and no
   artifact content: it SHALL be a prompt to evaluate, and the chain SHALL read only
   checked-in artifacts and `HookContext`.
3. WHEN the exit chain does not pass THEN the pointer SHALL NOT move, AND the outcome
   (`block`/`wait`, messages, escalation on repeat) SHALL be reported back to the
   signalling session in a machine-readable form, so the agent knows what the gate wants.
4. WHEN the same completion signal is delivered more than once (crash, retry, redelivery)
   THEN the pointer SHALL end in the same position as a single delivery (idempotent).
5. WHEN a completion signal names a node that is not the item's current node THEN it
   SHALL be refused with the current node named, and the pointer SHALL NOT move.
6. WHEN the signal transport is chosen (design decision) THEN it SHALL be available to a
   session on **both** ingresses and to a human at a terminal, and SHALL work under
   `routing.workspace` worktrees — the same seam regardless of who is driving.

### Requirement 2 — the pointer is the authority on phase

**User story:** As a human watching the board, I want the `loop:` label to state which
phase the work is actually in, so that the label answers #73's question instead of
mirroring the ingress's spawn activity.

#### Acceptance criteria (EARS)

1. WHEN a work item advances a node boundary (by completion signal or by event) THEN the
   `loop:<phase>` label and the execution-log `phase` front-matter SHALL be written by
   the graph's own entry hooks at that boundary — and by nothing else on the automated
   path.
2. WHEN a session runs an item through several phases without any inbound event THEN the
   pointer SHALL track each completed boundary via R1, so label and pointer never sit on
   node one while implementation is under way.
3. WHEN `the-loop check --recompute` runs THEN it SHALL, unchanged, derive every node's
   **verdict** from artifacts alone; position is the pointer's, verdicts are never the
   pointer's.
4. WHEN a forced transition (`the-loop graph force`) moves the pointer THEN all recording
   obligations of issue-109 SHALL hold unchanged (reason, four records, no forged
   verdict).

### Requirement 3 — graph state is resolved before anything is delivered

**User story:** As the agent receiving an event, I want to know which node the item
stands on, its status, and what the current gate is waiting for, so that I react from the
process's actual state rather than reconstructing it from prose.

#### Acceptance criteria (EARS)

1. WHEN the dispatcher prepares to deliver an event to a session THEN it SHALL resolve
   the item's graph context — current node, status (`in-progress | waiting | blocked |
   parked | complete | escalated`), parked/blocked reason, and the unmet messages of the
   current gate — **before** rendering the prompt, and the event prompt SHALL carry that
   context.
2. WHEN the dispatcher spawns a session THEN the spawn prompt SHALL be derived from the
   pointer: an item with no graph state is told to start the loop from the beginning; an
   item already mid-graph is told to **resume at its current node**, not to run the whole
   flow.
3. WHEN graph context cannot be resolved (hook failure, missing spec dir, graph disabled,
   foreign checkout) THEN the event SHALL still be delivered with the context marked
   unknown — resolution failure never costs a delivery (fail-open on delivery,
   issue-113's guarantee kept).
4. WHEN the item's graph is disabled or inapplicable (`routing.graph.enabled: false`,
   non-GitHub ref, no spec directory) THEN prompts SHALL degrade to today's exact
   templates — repositories outside the graph lose nothing.

### Requirement 4 — a waiting gate sees its input first

**User story:** As a reviewer whose comment answers a human gate, I want the gate to
classify my comment and take its transition before the agent acts on it, so that approval
and reaction cannot race or contradict each other.

#### Acceptance criteria (EARS)

1. WHEN an event arrives for an item whose current node is **parked waiting on a human
   gate** THEN `advance` (with the event's comments) SHALL run **before** the event is
   delivered to the session, and the delivered prompt SHALL carry the gate's verdict and
   any transition taken.
2. WHEN the gate's classification does not resolve (unauthorized author, indecisive text,
   hook failure) THEN the event SHALL still be delivered, with the gate still waiting —
   consult-first never becomes an event filter that can lose input (fail-open on
   delivery).
3. WHEN an event arrives for an item that is **not** parked at a gate THEN order SHALL
   be: resolve context (R3), deliver, then `advance` — today's post-delivery advance,
   kept for the non-gate case.
4. WHEN a gate consumes an event that is not also delivered (only if design introduces
   such a route, per-node and declared in `pdlc.yaml`) THEN the consumption SHALL be
   recorded in the event log with the delivery id, so no event ever silently vanishes.

### Requirement 5 — `session: inherit` is honoured

**User story:** As a reviewer at a gate, I want my questions to land in the session that
wrote the artifact, so that the context that produced the thing answers for it.

#### Acceptance criteria (EARS)

1. WHEN a gate node with `session: inherit` is entered on the automated path THEN the
   runtime SHALL bind it via `Runtime.resolve_session()` — the method gains its caller —
   preferring the live session that produced the artifacts.
2. WHEN that session is gone THEN the fallback SHALL be a fresh session seeded with the
   work item's checked-in artifacts, per issue-109 R7.4, and the fallback SHALL be
   recorded in the event log.
3. IF the registry and the graph disagree about the binding THEN the registry's live
   state SHALL win and the graph's binding SHALL be corrected — a model must not
   dispatch to a ghost.

### Requirement 6 — one source of truth for the process

**User story:** As a maintainer, I want exactly one artifact to define the PDLC's phases
and order, so that the skill's prose and the graph cannot drift into two processes.

#### Acceptance criteria (EARS)

1. WHEN the PDLC's node set, order, and phase labels are defined THEN `pdlc.yaml` SHALL
   be the single definition; `SKILL.md` / `reference/workflow.md` SHALL describe and
   reference it rather than independently declaring the sequence.
2. WHEN `workflow.phases` (harness config) and the graph's `phase:` values are compared
   THEN a parity test SHALL enforce agreement, in both directions — the same mechanism as
   `test_graph_parity.py` uses for artifacts.
3. WHEN the spawn/event prompt templates instruct the session THEN the instruction SHALL
   be generated from graph state (R3.2), not from a hard-coded restatement of the flow.

### Requirement 7 — the safety invariants survive the inversion

**User story:** As the operator, I want the graph's promotion from observer to authority
to add no new way for untrusted input to drive execution, so that handing the process to
the graph never means handing it to a commenter.

#### Acceptance criteria (EARS)

1. WHEN any input arrives — comment text, completion signal, webhook payload — THEN
   nothing in it SHALL move the pointer forward except through an exit chain evaluating
   checked-in artifacts, or `classify-feedback` over an **authorized** author's text.
2. WHEN the start ordering runs THEN both load-bearing orderings SHALL hold: the start
   is recorded before the spawn, and no pointer exists for an item whose spawn failed.
3. WHEN graph consultation fails at any point on the delivery path THEN the failure mode
   SHALL be: deliver anyway, mark context unknown, record `graph.link_failed` — enumerated
   and tested per call site, never assumed.
4. WHEN an item is outside the graph (skip conditions of issue-113/123) THEN every skip
   SHALL remain observable (`graph.skipped`) and behaviour SHALL equal today's.

## Non-functional requirements

- **Incremental adoptability.** Each requirement lands testably on its own; R1+R2 are the
  core inversion, R3–R5 build on them. No flag day for consuming repositories.
- **The delivery path stays fast and non-blocking.** Pre-delivery consultation is a local
  read of `graph-state.json` plus (for R4.1) one chain run; no outbound network call may
  gate a delivery.
- **`runtime.py`'s modesty holds.** Still no scheduler, no queue, no async, no database.
  The inversion is about *who asks*, not about adding an engine.

## Security considerations

> Threat-model-lite (`security.threatModel.required`). This work item moves a control
> point: what the harness is told, and what a gate consumes, becomes graph-driven.

- **Actors & trust.** Unchanged actors: untrusted GitHub payloads and comment bodies;
  trusted operator config and checked-in artifacts (trusted because only committers write
  them, and `_checkout_belongs_to` proves whose repo the checkout is before any of it is
  read). The completion signal (R1) is a **new input**: its issuer is the spawned session
  itself — an agent processing untrusted text — so the signal is treated as untrusted: a
  claim that triggers evaluation, never a verdict (R1.2).
- **Trust boundaries.**
  1. *Event text → pointer:* crossing forbidden, unchanged (R7.1). The corrected
     asymmetry: untrusted input may cause evaluation, only artifacts and authorized
     feedback may cause advancement.
  2. *Session → graph:* new boundary. The session may say "evaluate me", may not say
     "pass me". A compromised/prompt-injected session can at worst trigger exit chains
     early — each of which fails on the artifacts it would fail on anyway — or spam
     signals, bounded by R1.4/R1.5 (idempotent, current-node-only).
  3. *Graph → prompt:* graph context enters prompts (R3.1). Its sources are the item's
     own repo artifacts and hook messages — same trust class as the payload excerpt
     already carried, and rendered under the same "context, never instructions" framing.
- **Abuse cases (EARS).**
  1. WHEN an unauthorized commenter's text arrives at a waiting gate THEN the gate SHALL
     not resolve and the pointer SHALL not move (existing negative test, re-asserted on
     the new consult-first path).
  2. WHEN a session signals completion for a node whose artifacts do not satisfy the exit
     chain THEN the pointer SHALL NOT move and the refusal SHALL be recorded — a
     prompt-injected "declare everything done" achieves nothing.
  3. WHEN completion signals are replayed or flooded THEN pointer position SHALL be
     unaffected beyond a single evaluation's effect (R1.4), and repeated blocks SHALL
     escalate rather than loop (existing `max_attempts` semantics).
- **Fail-closed vs fail-open, stated per surface.** Advancement fails **closed** (no
  evaluation → no move). Delivery fails **open** (no consultation → deliver with context
  unknown) — losing operator events to a graph fault would be the worse failure, and is
  the property issue-113 already promised.
- **Risk tier: 5.** This redefines the execution model's control points (what gates
  consume, what sessions are told, what advances state). `human-approves-spec-and-pr`:
  each spec phase needs explicit approval, plus a named human security sign-off on the PR
  (`security.review.humanSignOffMinTier: 4`).

## Out of scope

- **User-authored graphs.** `pdlc.yaml` stays internal to the CLI (issue-109 R1.5);
  repo-local graphs remain a deliberate future feature.
- **Multi-item scheduling, queues, async.** The runtime's "no engine" stance holds.
- **Changing any hook's verification logic.** `validate-artifacts`, `classify-feedback`
  et al. are consumed as-is; this work item changes who calls them and when.
- **The webhook receiver's HTTP surface and the poller's discovery loop.** Both ingresses
  feed the same dispatcher; the change lands at the dispatcher/graph seam only.
- **Retiring the granular skill commands.** `/the-loop:work-on` and friends remain; R6
  re-roots what they assert about phase on the graph rather than deleting them.

## Open questions

1. **Completion-signal transport** — a CLI verb the session runs (`the-loop graph
   advance`-shaped), a file the runtime watches, or a dispatcher endpoint? Design phase
   decides; R1.6 constrains whatever is chosen. Leaning CLI verb: it exists
   (`graph_cmd.py`), is auditable, and works identically for humans.
2. **Does a gate ever consume an event *instead of* delivering it?** R4.4 permits design
   to introduce it per-node; default assumption is consult-then-deliver-always.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109).
