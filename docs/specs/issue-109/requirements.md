---
type: requirements
phase: requirements-definition
workItem: issue-109
status: draft                # draft | in-review | approved
approvedBy: []               # handles/roles who approved this phase (paper trail)
collaborators: [architect, engineer, product-manager]
riskTier: 4                  # LLM-influenced gates read untrusted text; schema surface touched
overrides: {}
---

# Requirements: the process graph — deterministic node boundaries for the-loop

> Phase 1 of 3 (requirements → design → tasks). Derived from the **locked**
> [`brainstorm.md`](brainstorm.md). **Revised** after the owner's second direction on
> PR #110 (internal graph · CEL edges · LLM-decided gates · per-work-item config ·
> YAML lifecycle hooks). This phase MUST be reviewed and approved before tasks.

## Introduction

[Issue #109](https://github.com/MadaraUchiha-314/the-loop/issues/109) asks how to stop the
harness skipping steps of the-loop's PDLC or inventing new ones. The locked brainstorm
established that the workflow exists only as prose, that the resulting drift is measurable
here, and — per the owner — that the root defect is the **absence of logical node
boundaries**: nothing in the-loop ever emits "this node completed".

This work item makes the-loop's PDLC an **explicit, declared graph** with its own node
lifecycle, evaluated by a small runtime in the CLI.

### What the owner's second direction changed

| Decision | Effect |
|---|---|
| **The graph is internal to the-loop.** It ships with the plugin; repositories do not define or override it. | Removes the largest attack surface outright — untrusted repository config can no longer influence what executes. Custom graphs become a *future* feature, which is why the graph is still fully declarative. |
| **Edges carry CEL expressions**, not a closed keyword vocabulary. | Conditions become expressive enough for real gates while staying non-Turing-complete and side-effect-free. |
| **Gates may be dynamic**, decided by an LLM call — e.g. did the human approve, or request changes? | Introduces a *new* trust boundary (the decision reads human-authored text), which replaces the one removed above. |
| **Per-work-item configuration** — tags and step-skipping drive execution. | The graph is one shape; a work item parameterises its own traversal. |
| **Lifecycle hooks expressed in YAML.** | Programmatic reactions at PDLC lifecycle points, declared rather than coded. |
| **tmux stays the seat of the work.** | Decision calls must never disturb the resident session the human can take over. |

**Risk tier remains 4, for a different reason.** The dominant risk is no longer
config-driven command execution (removed); it is that an **LLM-influenced gate reads
human-authored text**, which on a public repository is attacker-reachable. Per
`autonomy.tiers`, tier 4 is `human-approves-pr`; per `security.review.humanSignOffMinTier`,
it also requires a **named human security sign-off**.

### Assumptions (overridable in this phase's review)

| # | Question | Assumption | Binds |
|---|---|---|---|
| Q1 | Scope | Epic-shaped, one task DAG. Layers 1–5 in scope; **user-defined graphs out of scope**. | Out of scope |
| Q2 | Gate hardness | Advisory in-session, hard at the repository boundary. | R8, R9 |
| Q7 | Retrofit | Baseline the 34 existing spec folders; report drift, don't fail on it. | R4.5, R9.4 |
| Q8 | Node granularity | Split where a distinct artifact or human decision exists. Labels stay coarse; graph state carries the detail. | R1.3, R11.2 |
| Q9 | Graph state | A separate checked-in `graph-state.json`. | R3.1 |
| Q10 | Graph vs `workflow.phases` | Graph authoritative; phase list derived. | R11 |
| Q12 | CEL implementation | **`cel-python`** (pure Python, minimal dependencies) over a wrapped-C++ implementation — keeps wheels pure and installs toolchain-free. | R2.5 |
| Q13 | Decision-call transport | Decision calls are **separate short-lived headless invocations**, never injected into the resident session. | R6.4 |

## Requirements

### Requirement 1 — The graph is the-loop's own, declared artifact

**User story:** As a the-loop maintainer, I want the PDLC declared as data that ships with
the plugin, so the process is versioned and reviewed with the harness that runs it — and so
no repository can redefine what the-loop executes.

#### Acceptance criteria (EARS)

1. WHEN the runtime starts THEN the system SHALL load the graph from the **installed
   plugin** (`${CLAUDE_PLUGIN_ROOT}/skills/the-loop/graph/pdlc.yaml`) and SHALL NOT read a
   graph from the working repository.
2. WHEN the graph is loaded THEN the system SHALL validate it against a checked-in JSON
   Schema, and SHALL refuse to run if validation fails.
3. WHEN a node is declared THEN the system SHALL require `id` and `produces`, and SHALL
   accept `requires`, `gate`, `actor`, `stage`, `label`, `command`, `hooks`, `required`
   and `maxAttempts`.
4. IF a repository declares `workflow.graph` THEN the system SHALL ignore it and emit a
   warning naming this as a future feature — never silently merge it.
5. WHEN the graph declares a cycle THEN the system SHALL accept it.
6. IF an edge names an endpoint that is not a declared node THEN validation SHALL fail with
   the offending id.
7. WHEN the-loop's own CI runs THEN it SHALL validate the shipped graph, so a malformed
   graph cannot be released.

### Requirement 2 — Edge conditions are CEL expressions

**User story:** As a the-loop maintainer, I want edge conditions written as expressions over
graph state, so real conditions (attempt counts, tags, risk tiers, decision outcomes) are
expressible without inventing a keyword for each.

#### Acceptance criteria (EARS)

1. WHEN an edge declares `when` THEN the system SHALL evaluate it as a **CEL** expression
   returning a boolean.
2. WHEN a CEL expression is evaluated THEN the system SHALL bind a documented, typed
   context: `gate` (satisfied, unmet), `attempts`, `maxAttempts`, `node`, `workItem`
   (id, tags, riskTier, skip), `decision` (a completed decision's structured result),
   `findings`, and `approval`.
3. IF a CEL expression does not compile, does not return a boolean, or references an unbound
   name THEN validation SHALL fail at load time — not at traversal time.
4. WHEN more than one outgoing edge evaluates true THEN the system SHALL take the
   **first in declaration order** and record that the graph was ambiguous.
5. WHEN no outgoing edge evaluates true THEN the system SHALL park the work item and
   escalate, rather than guess.
6. WHEN CEL is evaluated THEN it SHALL have no access to the filesystem, network,
   subprocesses or environment — evaluation is a pure function of the bound context.

### Requirement 3 — Graph state is durable, checked in, and reconstructable

**User story:** As the harness resuming a work item days later on another machine, I want to
know which node it is in, so resumption is a lookup rather than an inference.

#### Acceptance criteria (EARS)

1. WHEN a work item enters its first node THEN the system SHALL create
   `docs/specs/<id>/graph-state.json` recording `currentNode`, per-node `attempts`,
   timestamps, recorded decisions and the parked reason.
2. WHEN a transition is taken THEN the system SHALL persist graph state **before** any
   dependent side effect.
3. WHEN graph state is missing THEN the system SHALL reconstruct the current node by
   evaluating gates in graph order — the artifacts, not the state file, are ground truth.
4. IF graph state is unparseable, or names a node absent from the graph, THEN the system
   SHALL treat it as missing, reconstruct per 3.3, warn, and SHALL NOT delete it.

### Requirement 4 — Gate evaluation is a pure, testable predicate

**User story:** As an engineer, I want "is this node complete?" answered by code over the
checked-in artifacts, so the answer never depends on a model's opinion of its own work.

#### Acceptance criteria (EARS)

1. WHEN `the-loop check <work-item>` runs THEN the system SHALL report each node as
   `satisfied` or `unmet(<predicate>)`, naming the specific failing predicate.
2. WHEN `--format json` is passed THEN output SHALL be machine-readable for hooks and CI.
3. WHEN a predicate cannot be evaluated THEN the system SHALL report **unmet**, never
   satisfied.
4. WHEN `the-loop check` runs THEN it SHALL perform no network I/O, spawn no harness and
   mutate no file — **including for nodes whose gate has a decision component**, whose
   last recorded decision it reads from graph state rather than re-deciding.
5. WHEN `--all` is passed THEN the system SHALL emit a drift report over every spec folder.
6. WHEN `--recompute` is passed THEN the system SHALL ignore graph state and derive
   completion from artifacts alone.

### Requirement 5 — Dynamic gates: the LLM produces facts, CEL routes

**User story:** As an operator, I want the approval gate to understand a human's actual
reply — approval, rejection, or a request for changes — so a gate that is inherently
semantic is not forced into a keyword match.

#### Acceptance criteria (EARS)

1. WHEN a node declares a `decision` THEN the system SHALL invoke the configured harness
   **headless** with that decision's prompt and **JSON Schema**, and SHALL bind the
   validated result into the CEL context as `decision`.
2. WHEN the harness supports schema-enforced output THEN the system SHALL use it; WHEN it
   does not, the system SHALL embed the schema in the prompt, validate the returned JSON
   itself, and retry up to a declared bound.
3. IF a decision result fails schema validation after its retries THEN the system SHALL
   **fail closed**: park the work item and notify, never assume an outcome.
4. WHEN a decision is recorded THEN the system SHALL persist it in graph state with the
   inputs it was derived from, so the routing is auditable and `check` stays pure.
5. **A decision SHALL NOT be able to grant an approval that policy reserves for a human.**
   WHEN `autonomy.tiers` or `security.review.humanSignOffMinTier` requires a human for this
   work item THEN a decision outcome SHALL only ever *classify* that human's response, never
   substitute for its absence.
6. WHEN a decision reads human-authored text THEN the system SHALL consider only text
   authored by a user in `routing.authorizedUsers`, and SHALL ignore all other text.
7. WHEN a decision prompt is composed THEN untrusted text SHALL be delimited and labelled as
   data, and the schema SHALL constrain the answer to a closed set of outcomes.

### Requirement 6 — Reuse the coding harness, without disturbing the resident session

**User story:** As an operator watching a tmux session, I want to be able to take over at any
moment, so automation never costs me the ability to intervene.

#### Acceptance criteria (EARS)

1. WHEN a **work** node executes THEN the system SHALL run it through the configured runner,
   including the resident tmux session, so a human can attach and take over.
2. WHEN a human takes over a resident session THEN the system SHALL continue to evaluate
   gates against the artifacts that session produces, without requiring the human to use
   the-loop's commands.
3. WHEN `the-loop run` drives a node headlessly THEN the system SHALL select the model tier
   from the node's `stage`.
4. WHEN a **decision** call is made THEN it SHALL run as a separate short-lived headless
   process — a fresh session, never `--resume` of the work session and never pasted into
   tmux — so the human's takeover surface is untouched.
5. WHEN a decision call is made THEN the system SHALL use the cheapest tier the node
   declares, defaulting to `economy`.

### Requirement 7 — Per-work-item configuration drives traversal

**User story:** As an operator, I want a work item to declare its own tags and skips, so one
graph serves a typo fix and an auth change without either being mis-served.

#### Acceptance criteria (EARS)

1. WHEN a work item's spec front-matter declares `tags`, `riskTier` or `skipNodes` THEN the
   system SHALL bind them into the CEL context as `workItem.*`.
2. WHEN a node is listed in `skipNodes` THEN the system SHALL traverse past it, recording the
   skip and its reason in graph state and the execution log.
3. IF a node declares `required: true` THEN it SHALL NOT be skippable by any per-work-item
   configuration — this covers at minimum the security-review gate and any human-approval
   node the risk tier mandates.
4. IF `skipNodes` names an unknown node THEN the system SHALL fail closed and report it,
   rather than ignoring the entry.
5. WHEN per-work-item configuration is read THEN it SHALL come only from the work item's own
   checked-in spec front-matter — never from a ticket comment or a webhook payload.

### Requirement 8 — Lifecycle hooks, declared in YAML

**User story:** As a the-loop maintainer, I want reactions to PDLC lifecycle events declared
as configuration, so behaviour at node boundaries is visible and extensible rather than
buried in code.

#### Acceptance criteria (EARS)

1. WHEN the graph declares `hooks` — globally or per node — THEN the system SHALL support at
   least the events `onEnter`, `onExit`, `onGateFail`, `onAwaitHuman`, `onEscalate`,
   `onSkip` and `onComplete`.
2. WHEN a hook fires THEN the system SHALL execute its declared **actions in order**, each
   drawn from a closed, typed action vocabulary (set the phase label, append an
   execution-log entry, notify roles, post a marked ticket comment, emit an event-log
   record, record a decision).
3. IF a hook declares an action outside the vocabulary THEN validation SHALL fail at load
   time; **no hook action SHALL be an arbitrary shell command.**
4. WHEN an action fails THEN the system SHALL log it and continue the remaining actions —
   a notification outage SHALL NOT wedge the graph — except where the action is the
   transition itself.
5. WHEN a node's `actor` is `human`, or a required approval is absent, THEN `onAwaitHuman`
   SHALL park the work item and notify the roles from `notifications.events`, resolved
   through `.the-loop/collaborators.yaml`.
6. WHEN attempts reach `maxAttempts`, or the same predicate fails twice consecutively, THEN
   `onEscalate` SHALL record the conflict, notify, and stop advancing.

### Requirement 9 — The repository boundary is the hard gate

1. WHEN `the-loop check` runs in a pre-push hook or CI THEN it SHALL exit non-zero if any
   node up to and including the current node has an unmet gate.
2. WHEN CI evaluates a work item THEN it SHALL use `--recompute`.
3. WHEN a change is exempt (below the configured tier, or touching no spec) THEN the check
   SHALL pass rather than demand a spec.
4. WHEN a work item is in the recorded baseline THEN drift SHALL be reported without failing.

### Requirement 10 — Failure modes are recoverable and bounded

1. WHEN a gate is unmet THEN recovery SHALL be deterministic in decision and agentic in
   repair: code names the unmet predicate, the agent decides how to satisfy it.
2. WHEN the same predicate fails on two consecutive attempts THEN the system SHALL escalate
   rather than retry a third time.
3. IF the graph cannot be loaded or compiled THEN the system SHALL refuse to advance any
   work item and report why.
4. WHEN a harness session dies mid-node THEN the system SHALL reuse the existing
   respawn-and-resume path and re-enter the **same** node.
5. WHEN a decision call fails, times out, or returns an invalid result THEN the system SHALL
   fail closed per R5.3.

### Requirement 11 — Backwards compatibility

1. WHEN a repository has never seen the graph THEN the system SHALL work without requiring
   any file to be added to it.
2. WHEN a node declares a `label` THEN the system SHALL keep that ticket label in sync;
   nodes without a label SHALL NOT create new labels.
3. WHEN `workflow.phases` is present THEN the shipped graph SHALL be authoritative and the
   phase list SHALL be treated as derived, with a warning on divergence.

### Requirement 12 — Observability

1. WHEN any node is entered, exited, failed, skipped, parked or escalated THEN the system
   SHALL emit a JSONL event-log record naming the work item, node, outcome and attempt count.
2. WHEN a decision call is made THEN the system SHALL record its outcome, the harness used
   and its token usage.
3. WHEN an edge is taken THEN the system SHALL record which CEL expression selected it.

## Non-functional requirements

- **Dependencies.** One new runtime dependency is accepted: a **pure-Python CEL**
  implementation (Q12). No agent SDK and no graph framework (`design.md` § trade-offs).
- **Both harnesses.** Every requirement holds for Claude Code and Cursor, or degrades to the
  repository-boundary gate with the difference documented (schema-enforced output is the
  known asymmetry — R5.2).
- **`the-loop check` is fast and pure.** It runs on every resident-session turn; it reads the
  spec folder only, and never makes a decision call.
- **Observability identical dev/runtime**, as for every other CLI component.

## Security considerations

> Threat-model-lite (`security.threatModel.required`). The owner's "make the graph internal"
> direction **removes** the largest boundary; the dynamic-gate direction **adds** a different
> one. Both are stated.

- **Actors & trust:**
  - *Trusted:* the-loop's own shipped graph (reviewed and released with the plugin); the
    operator running the CLI.
  - *Untrusted:* **human-authored text a decision call reads** (ticket and PR comments — on a
    public repository, anyone's); the **agent** as a writer of graph state and artifacts;
    webhook and poller payloads; per-work-item front-matter in a checkout the operator does
    not control (a fork's PR branch).
- **Removed by this revision:** *config → process execution.* Because the graph ships with
  the plugin and repositories cannot define or override it (R1.1, R1.4), no repository-supplied
  declaration reaches an invocation. The closed `command` vocabulary is **retained anyway**,
  as the mechanism that will make user-defined graphs safe when that feature arrives.
- **Trust boundaries & data:**
  1. **Untrusted text → gate outcome (the new primary boundary).** A decision call classifies
     a human's reply. If attacker-authored text can reach it, an injected instruction could
     steer a gate toward "approved".
  2. **Agent → graph state.** The agent can write the file recording which gates passed.
  3. **Decision result → routing.** A malformed or adversarial result must not select an
     undeclared destination.
  4. **CEL evaluation.** Expression evaluation must not become an execution surface.
  5. **Node events → external channels.** Notifications move work-item content outward.
- **Abuse cases (EARS):**
  1. WHEN a comment from a user outside `routing.authorizedUsers` would be read by a decision
     call THEN the system SHALL ignore that text entirely (R5.6).
  2. WHEN untrusted text embedded in a decision prompt contains instructions ("approve this")
     THEN the schema-constrained closed outcome set and the data-delimited prompt SHALL
     confine the answer to a classification, and the resulting route SHALL still be one of
     the node's **declared** edges (R5.7, R2).
  3. WHEN a decision outcome would satisfy an approval that `autonomy.tiers` or
     `security.review.humanSignOffMinTier` reserves for a human THEN the system SHALL refuse
     and continue to wait (R5.5).
  4. WHEN `graph-state.json` claims a node complete that the artifacts contradict THEN the
     repository-boundary check SHALL fail (R9.2).
  5. WHEN a CEL expression attempts filesystem, network, subprocess or environment access
     THEN evaluation SHALL not provide it (R2.6).
  6. WHEN a repository supplies `workflow.graph` THEN it SHALL be ignored with a warning
     (R1.4).
  7. WHEN per-work-item `skipNodes` names a node marked `required: true` THEN the skip SHALL
     be refused (R7.3).
  8. WHEN a notification recipient would come from anywhere but `collaborators.yaml` THEN the
     system SHALL refuse to send it.
- **Fail closed:** an uncompilable graph or expression, an unknown node, an unevaluable
  predicate, an invalid decision result, no true outgoing edge, an unknown skip target, or a
  missing collaborator entry each SHALL stop advancement and report — never advance unchecked.

## Out of scope

- **User-defined / overridable graphs.** Explicitly a future feature (R1.4); the declarative
  form and the closed vocabularies exist so it can arrive safely.
- **Arbitrary shell actions in hooks.** The action vocabulary is closed (R8.3).
- **Importing a graph framework.**
- **Mass-retrofitting the 34 existing spec folders.** Reported and baselined.
- **Changing the PDLC itself.** The graph describes the process the skill already defines.

## Open questions

1. **Who provides the tier-4 named security sign-off?**
2. **Which CEL implementation** (Q12) — pure-Python `cel-python`, or the official
   wrapped-C++ binding at the cost of a non-pure wheel?
3. **How far does `skipNodes` go?** R7.3 protects security review and mandated human
   approval. Should anything else be unskippable — the reviewer briefing, capability docs?
4. **Cursor decision calls** have no schema-enforced output mode today (R5.2). Is
   prompt-embedded schema plus validation plus bounded retry acceptable, or should Cursor
   work items route decisions through Claude Code when both are installed?
