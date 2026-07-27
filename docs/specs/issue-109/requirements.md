---
type: requirements
phase: requirements-definition
workItem: issue-109
status: draft                # draft | in-review | approved
approvedBy: []               # handles/roles who approved this phase (paper trail)
collaborators: [architect, engineer, product-manager]
riskTier: 4                  # touches autonomy.sensitivePaths (**/*schema*) → human-approves-pr
overrides: {}
---

# Requirements: the process graph — deterministic node boundaries for the-loop

> Phase 1 of 3 (requirements → design → tasks). Derived from the **locked**
> [`brainstorm.md`](brainstorm.md) (approved by @MadaraUchiha-314 on PR #110). This phase
> MUST be reviewed and approved before moving to design.

## Introduction

[Issue #109](https://github.com/MadaraUchiha-314/the-loop/issues/109) asks how to stop the
harness skipping steps of the-loop's PDLC or inventing new ones. The locked brainstorm
established that the workflow exists only as prose, that the resulting drift is measurable
in this repository, and — per the owner's direction on PR #110 — that the root defect is
**the absence of logical node boundaries**: the-loop has no event, anywhere, that means
"this node of the process completed". Harness hooks fire on *harness* lifecycle (many
times per node, carrying no phase), and a phase *label* is a state rather than a
transition, so nothing emits on change.

This work item makes the-loop's process an **explicit, declared graph** with its own node
lifecycle: nodes that each produce one durable artifact, edges that are evaluated rather
than remembered, checked-in graph state, and node-boundary hooks that gate, notify and
advance. Harness hooks are retained as a *trigger transport* — a clock — never as the
state machine.

**Risk tier 4.** The change adds a schema surface
(`.the-loop/harness-config.schema.json`, matched by `autonomy.sensitivePaths: **/*schema*`)
and introduces a component that invokes harness CLIs from declared configuration. Per
`autonomy.tiers`, tier 4 is `human-approves-pr`; per
`security.review.humanSignOffMinTier: 4`, it also requires a **named human security
sign-off** before completion.

### Assumptions carried from the brainstorm's open questions

The owner approved proceeding without answering every open question individually. Each is
resolved below with the brainstorm's recommended default, **stated so it can be overridden
in this phase's review** (paper trail; `reference/workflow.md` "keep moving; log conflicts").

| # | Question | Assumption taken | Where it binds |
|---|---|---|---|
| Q1 | Scope: epic or one PR? | **Epic-shaped, delivered as a task DAG in one work item.** Layers 1–4 are in scope; Layer 5 (agent-selected edges) is explicitly out of scope. | Out of scope, below |
| Q2 | Gate hardness | **Advisory in-session, hard at the repository boundary.** In-session hooks report and re-prompt; pre-push/CI blocks. | R7, R8 |
| Q7 | Retrofit of the 34 existing spec folders | **Baseline, do not mass-fix.** `check` reports drift; a recorded baseline exempts pre-existing items so the gate only binds new work. | R3.5, R7.4 |
| Q8 | Node granularity | **Split where a distinct artifact or a distinct human decision exists**, and no further. New nodes do **not** each get a `loop:` label; labels stay coarse and graph state carries the detail. | R1.2, R9.2 |
| Q9 | Where graph state lives | **A separate checked-in file** per work item, not `execution-log.md` front-matter — the log is prose a human edits, and a parser that must survive that is a liability. | R2.1 |
| Q10 | Graph vs `workflow.phases` | **The graph is authoritative; the phase list is derived from it.** Each node declares the label it maps to, so existing tickets and labels keep working. | R9 |
| Q11 | Dynamic edges | **Out of scope for this work item.** Declared as a forward-compatible field in the schema, not implemented. | Out of scope |

## Requirements

### Requirement 1 — The process graph is declared data

**User story:** As a the-loop operator, I want the PDLC's nodes and transitions declared as
validated configuration, so that the process is a single source both the prompt and the
code read, and a step that is not declared cannot be taken.

#### Acceptance criteria (EARS)

1. WHEN `.the-loop/harness-config.yaml` contains a `workflow.graph` mapping THEN the system
   SHALL parse it into a typed graph of nodes and edges and validate it against
   `.the-loop/harness-config.schema.json`.
2. WHEN a node is declared THEN the system SHALL require an `id` and a `produces` artifact,
   and SHALL accept `requires`, `gate`, `actor` (`agent | human | code`), `stage`,
   `notify`, `label` and `maxAttempts`.
3. WHEN an edge is declared THEN the system SHALL require `from`, `to` and `when`, where
   `when` is drawn from a **closed vocabulary** of state predicates.
4. WHEN the graph declares a cycle THEN the system SHALL accept it — review→fix→review is a
   valid transition set, not a validation error.
5. IF the graph names an edge endpoint that is not a declared node THEN the system SHALL
   reject the configuration with the offending id and SHALL NOT run.
6. IF `workflow.graph` is absent THEN the system SHALL fall back to a built-in default
   graph equivalent to today's `workflow.phases`, so an un-migrated repository keeps
   working.

### Requirement 2 — Graph state is durable, checked in, and resumable

**User story:** As the harness resuming a work item days later on a different machine, I
want to know exactly which node it is in, so that resumption is a lookup rather than an
inference.

#### Acceptance criteria (EARS)

1. WHEN a work item enters its first node THEN the system SHALL create
   `docs/specs/<id>/graph-state.json` recording `currentNode`, per-node `attempts`,
   entered/exited timestamps and the parked reason when applicable.
2. WHEN a transition is taken THEN the system SHALL update graph state **before** any
   side effect that depends on it, so a crash mid-transition leaves a re-evaluable state
   rather than a lost one.
3. WHEN graph state is missing for a work item that has artifacts on disk THEN the system
   SHALL reconstruct the current node by evaluating the gates in graph order — the
   artifacts, not the state file, are the ground truth.
4. IF `graph-state.json` is unparseable THEN the system SHALL treat it as missing and
   reconstruct per 2.3, emitting a warning, and SHALL NOT delete the file.

### Requirement 3 — Gate evaluation is a pure, testable predicate

**User story:** As an engineer, I want "is this node actually complete?" answered by code
over the checked-in artifacts, so the answer never depends on a model's opinion of its own
work.

#### Acceptance criteria (EARS)

1. WHEN `the-loop check <work-item>` runs THEN the system SHALL evaluate every declared
   node's gate against the repository and report each as `satisfied` or
   `unmet(<predicate>)`, naming the **specific** failing predicate.
2. WHEN `--format json` is passed THEN the system SHALL emit machine-readable output
   suitable for consumption by a hook or CI step.
3. WHEN a gate predicate cannot be evaluated (a missing file, an unreadable front-matter
   block) THEN the system SHALL report it as **unmet**, never as satisfied.
4. WHEN `the-loop check` runs THEN it SHALL perform no network I/O, spawn no harness, and
   mutate no file.
5. WHEN `--all` is passed THEN the system SHALL evaluate every spec folder under
   `workflow.specDir` and emit a drift report, so the existing corpus can be baselined.
6. WHEN `--recompute` is passed THEN the system SHALL ignore `graph-state.json` entirely
   and derive node completion from the artifacts alone.

### Requirement 4 — Node-lifecycle hooks fire at boundaries, and notify

**User story:** As a collaborator, I want to be told when the work item needs me, so that a
node waiting on a human is an event rather than a silence.

#### Acceptance criteria (EARS)

1. WHEN a node is entered THEN the system SHALL run `onEnter`: set the node's mapped phase
   label, append an execution-log entry, and record the node's `stage` for model routing.
2. WHEN a node claims completion THEN the system SHALL run `onExit`: evaluate the gate and
   take the satisfied or failed edge accordingly.
3. WHEN a gate is unmet THEN the system SHALL run `onGateFail`: increment the node's
   attempt count and surface the unmet predicate as the agent's next input.
4. WHEN a node's `actor` is `human`, or its gate requires an approval that is absent, THEN
   the system SHALL run `onAwaitHuman`: park the work item and **notify the roles declared
   in `notifications.events`, resolved through `.the-loop/collaborators.yaml`**.
5. WHEN a node's attempts reach `maxAttempts`, or the same gate predicate fails twice
   consecutively, THEN the system SHALL run `onEscalate`: record the conflict in
   `docs/decisions/conflicts.md`, notify, and stop advancing that work item.
6. WHEN any lifecycle hook is executed THEN the system SHALL emit a corresponding record to
   the JSONL event log.

### Requirement 5 — Orchestrated transport: one node, one harness invocation

**User story:** As an operator, I want `the-loop run` to drive a work item node by node, so
that ordering is Python control flow rather than a model's recollection.

#### Acceptance criteria (EARS)

1. WHEN `the-loop run <work-item>` is invoked THEN the system SHALL, for the current node,
   render its prompt, invoke the configured harness **headless** with the node's `stage`
   model tier, and treat process exit plus the terminal result JSON as the node boundary.
2. WHEN a node's invocation exits non-zero THEN the system SHALL retry that node up to
   `maxAttempts`, appending the error text to the prompt, before escalating per R4.5.
3. WHEN a node completes and its gate is satisfied THEN the system SHALL take the matching
   edge and continue without human input, subject to R4.4.
4. WHEN a node declares `humanReview: true` and the work item's risk tier requires approval
   per `autonomy.tiers` THEN the system SHALL park rather than advance.
5. WHEN `the-loop run` is re-invoked after any interruption THEN the system SHALL resume at
   the current node without repeating completed ones.
6. WHILE a work item is paused or stopped through the existing `ControlStore` the system
   SHALL NOT advance it.

### Requirement 6 — Transports for resident and event-driven sessions

**User story:** As an operator running the resident tmux fleet, I want the same gates to
apply, so enforcement is not a property of which runner I chose.

#### Acceptance criteria (EARS)

1. WHEN a harness turn ends in a resident session THEN the harness's stop hook SHALL invoke
   `the-loop check` for the work item, resolving the current node from **graph state** and
   not from the hook payload.
2. WHEN that check reports an unmet gate THEN the system SHALL return the unmet predicate to
   the harness through that harness's own continuation mechanism — Claude Code's blocking
   `Stop` decision, or Cursor's `followup_message`.
3. WHEN the continuation mechanism has no built-in bound THEN the system SHALL enforce
   `maxAttempts` itself, so a blocking hook cannot loop indefinitely.
4. WHEN a webhook or poller event arrives for a work item THEN the system SHALL treat it as
   an edge input evaluated against the current node, not as an unconditional resume.

### Requirement 7 — The repository boundary is the hard gate

**User story:** As a reviewer, I want an unskippable check at merge time, so enforcement
does not depend on the harness cooperating.

#### Acceptance criteria (EARS)

1. WHEN `the-loop check` runs in a pre-push hook or CI THEN it SHALL exit non-zero if any
   node up to and including the work item's current node has an unmet gate.
2. WHEN CI evaluates a work item THEN it SHALL use `--recompute`, deriving completion from
   the artifacts rather than trusting the checked-in graph state.
3. WHEN a change is exempt (a work item below the configured tier, or a change touching no
   spec) THEN the system SHALL pass rather than demand a spec.
4. WHEN a work item is listed in the recorded baseline THEN the system SHALL report its
   drift without failing.

### Requirement 8 — Failure modes are recoverable, and bounded

**User story:** As an operator of an unattended run, I want failures to converge, so the
loop neither wedges nor burns tokens forever.

#### Acceptance criteria (EARS)

1. WHEN a node fails its gate THEN the recovery SHALL be deterministic in decision and
   agentic in repair: code names the unmet predicate, the agent decides how to satisfy it.
2. WHEN the same predicate fails on two consecutive attempts THEN the system SHALL escalate
   rather than retry a third time.
3. IF the graph cannot be loaded THEN the system SHALL refuse to advance any work item and
   SHALL report why, rather than falling back to unchecked behaviour.
4. WHEN a harness session dies mid-node THEN the system SHALL reuse the existing
   respawn-and-resume path and re-enter the same node, not the next one.

### Requirement 9 — Backwards compatibility and migration

**User story:** As an operator of an existing the-loop project, I want my labels and specs
to keep working, so adopting the graph is not a migration cliff.

#### Acceptance criteria (EARS)

1. WHEN a repository has no `workflow.graph` THEN the system SHALL behave equivalently to
   today (R1.6) and SHALL NOT require any file to be added.
2. WHEN a node declares a `label` THEN the system SHALL keep that ticket label in sync as
   today; nodes without a label SHALL NOT create new labels, their state living in graph
   state only.
3. WHEN `workflow.phases` and `workflow.graph` are both present THEN the graph SHALL be
   authoritative and the system SHALL warn that `phases` is derived.

### Requirement 10 — Observability

**User story:** As an operator, I want node transitions visible in the same event log as
everything else, so a stalled work item is diagnosable.

#### Acceptance criteria (EARS)

1. WHEN any node is entered, exited, failed, parked or escalated THEN the system SHALL emit
   a JSONL event-log record naming the work item, node, outcome and attempt count.
2. WHEN a node is executed through `the-loop run` THEN the system SHALL record its token
   usage against that node, extending the existing per-dispatch telemetry.

## Non-functional requirements

- **No new runtime dependency.** The graph runtime is stdlib Python plus the existing
  PyYAML (decision-038); no agent SDK, no graph library (see `design.md` § trade-offs).
- **Both harnesses.** Every requirement above is satisfied for Claude Code and Cursor, or
  degrades to the repository-boundary gate (R7) with the difference documented.
- **`the-loop check` is fast.** It runs on every resident-session turn, so it SHALL be
  I/O-bound on the spec folder only and SHALL NOT walk the whole repository by default.
- **Observability identical dev/runtime** (`observability` config), as for every other CLI
  component.

## Security considerations

> Threat-model-lite (`security.threatModel.required`). This work item **does** add attack
> surface — it introduces a component that reads configuration and invokes harness CLIs —
> so it is enumerated rather than waved away.

- **Actors & trust:**
  - *Trusted:* the operator running the CLI; the repository's committed configuration in a
    repository the operator controls.
  - *Untrusted:* the **agent itself** as a writer of graph state and artifacts; webhook and
    poller payloads (already treated as untrusted); any repository configuration in a
    checkout the operator does not control (a fork, a contributed PR branch).
- **Trust boundaries & data:**
  1. **Config → process execution.** Nodes declare what runs. If a node could carry
     free-form argv, a malicious `workflow.graph` in an untrusted checkout would be
     arbitrary command execution under the operator's credentials. This is the primary new
     boundary.
  2. **Agent → graph state.** The agent can write `graph-state.json`, which is the file
     that says which gates have been passed. The subject of the gate can edit the gate's
     bookkeeping.
  3. **Gate result → harness input.** The unmet-predicate text is fed back into the agent's
     next turn; it must be the-loop's own text, never payload-derived.
  4. **Node events → external channels.** `onAwaitHuman` sends notifications, moving work
     item content outward.
- **Abuse cases (EARS):**
  1. WHEN `workflow.graph` declares a node whose command is not a member of the-loop's
     closed command vocabulary THEN the system SHALL reject the configuration and SHALL NOT
     execute anything.
  2. WHEN `graph-state.json` claims a node is complete but that node's gate is unmet
     against the artifacts THEN the repository-boundary check (R7.2, `--recompute`) SHALL
     fail, so tampering cannot survive review.
  3. WHEN a gate failure message would include text derived from a webhook payload THEN the
     system SHALL emit only the-loop's own predicate description.
  4. WHEN a notification recipient would be derived from anything other than
     `collaborators.yaml` THEN the system SHALL refuse to send it.
  5. WHEN an edge's `when` is not a member of the closed predicate vocabulary THEN the
     system SHALL reject the graph rather than attempt to interpret it.
  6. WHEN `graph-state.json` names a node id absent from the graph THEN the system SHALL
     treat the state as untrusted and reconstruct from artifacts (R2.3).
- **Fail closed:** an unparseable graph, an unknown node id, an unevaluable predicate, a
  missing `collaborators.yaml` entry, or an ambiguous current node each SHALL stop
  advancement and report — never silently advance, and never fall back to "unchecked".

## Out of scope

- **Layer 5, agent-selected edges (Q11).** The schema reserves the field; nothing evaluates
  it in this work item. Routing stays fully static.
- **Importing a graph framework.** Rejected in the brainstorm and in `design.md`; the-loop's
  nodes are CLI subprocesses and its checkpoints are checked-in files.
- **Mass-retrofitting the 34 existing spec folders (Q7).** Reported and baselined, not
  fixed here.
- **Changing the PDLC itself.** The graph *describes* the process the skill already defines;
  any change to what the process should be is a separate work item.
- **New `loop:` labels per fine-grained node (Q8).** Labels stay coarse.

## Open questions

Raised on [issue #109](https://github.com/MadaraUchiha-314/the-loop/issues/109) and
PR #110; each currently carries an assumption from the table above, so none blocks design.

1. Is the **closed command vocabulary** (security boundary 1) acceptable, or do operators
   need custom node commands? If the latter, an allowlist mechanism must be designed here
   rather than added later.
2. Is `graph-state.json` the right file (Q9), given the alternative of extending
   `execution-log.md` front-matter?
3. Does the risk-tier-4 reading hold — and who is the **named human security sign-off**
   (`security.review.humanSignOffMinTier: 4`)?
