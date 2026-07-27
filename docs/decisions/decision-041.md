# Decision 041: model the-loop's process as an explicit graph with its own node-lifecycle hooks — implemented, not imported

- **Status:** proposed
- **Date:** 2026-07-27
- **Deciders:** @MadaraUchiha-314 (issue #109, PR #110)
- **Work item:** issue-109
- **Spec:** `docs/specs/issue-109/`
- **Supersedes in practice:** the "open design question" left dangling at the end of
  `skills/the-loop/reference/workflow.md` § *Predictability & guarantees* ("candidate
  mechanisms: harness hooks, custom code — evaluate and record a decision as it firms up").
  This is that decision.
- **Builds on:** [decision-004](decision-004.md) (the Kiro 3-phase spec — the graph
  formalizes the artifact chain it defines), [decision-027](decision-027.md) (checkpoint-
  then-reset — graph state is the checkpoint made explicit), [decision-005](decision-005.md)
  / [decision-038](decision-038.md) (dependency posture).

## Context

Issue #109: *"The current workflow of the-loop is only enforced through documentation and
prompts written in SKILL.md… how do we make these top level workflow more programmatic?"*

The PDLC is described in prose and enforced by nothing. Measured against this repository's
own checked-in specs at the time of writing: of 26 execution logs, **23 sit at
`phase: needs-review`** and **none reaches `complete`**, while 15 issues carry the
`loop:complete` label — the two mirrors of the same state machine disagreeing on 22 work
items, unnoticed. 15 of 28 `requirements.md` and 16 of 33 `design.md` files are still
`status: draft` despite having shipped, so downstream artifacts were demonstrably derived
from unlocked upstream ones.

The owner's diagnosis on PR #110 located the defect more precisely than "the workflow is
unenforced":

> *"There's no clear definition and hooks around logical 'node' boundaries… The hooks
> provided by the agent harnesses are too fine grained and lack the appropriate details to
> figure out which phase of the-loop we are in."*

That is correct, and it is a category distinction that the first draft of the brainstorm
missed. Two event spaces were conflated:

| | Harness lifecycle | the-loop lifecycle |
|---|---|---|
| Events | turn ended, tool called, session started | node entered / exited / gate failed / awaiting human |
| Granularity | many per node | one per node, possibly spanning days |
| Carries the phase? | no | by definition |
| Exists today? | yes, both harnesses | **no** |

**There is no "this node completed" event anywhere in the-loop.** A phase label cannot be
one either: a label is a state, not a transition, and nothing emits on change. So there was
nowhere to hang the gate, the notification, or the advance.

The drift confirms the diagnosis rather than merely coexisting with it: `needs-review` is a
single label covering at least six distinct pieces of work (self-review, critic-review,
security review, evidence, capability-doc fold-in, reviewer briefing). The state machine
has no vocabulary past that point, and that is exactly where 23 of 26 logs stop. **The
drift concentrates where node granularity runs out.**

## Decision

1. **Declare the process as a graph.** `workflow.graph` in the per-repo harness config
   declares **nodes** (each with one `produces` artifact, plus `requires`, `gate`, `actor`,
   `stage`, `label`, `command`, `notify`, `maxAttempts`) and **edges** (`from`, `to`,
   `when`). Cycles are first-class — review→fix→review is a transition set, not a modelling
   error. A transition the graph does not declare cannot be taken, which is what makes
   *"no extra steps"* decidable at last.
2. **Give the-loop its own node-lifecycle hooks** — `onEnter`, `onExit`, `onGateFail`,
   `onAwaitHuman`, `onEscalate` — fired by a small runtime at node boundaries. `onAwaitHuman`
   is the emitter that finally fires `notifications.events`, which has been declared but
   inert since it was written.
3. **Harness hooks are a clock, not a state machine.** A stop hook supplies *when* to look;
   the graph supplies *what we are looking at*. The hook calls `the-loop check`, which
   resolves the current node from graph state — so the hook never needs to know the phase,
   which is precisely the objection that motivated this decision.
4. **Graph state is a cache; the artifacts are the authority.** `graph-state.json` is
   checked in per work item, but `the-loop check --recompute` derives completion from the
   artifacts alone, and the repository-boundary gate always uses it. The agent can write the
   state file; it cannot thereby pass a gate.
5. **Gate evaluation is a pure function** over the repository (`the-loop check`): no
   network, no subprocess, no mutation — so the same code runs on every turn, in CI, and
   inside the orchestrator.
6. **Enforcement is advisory in-session and hard at the repository boundary.** In-session
   hooks report and re-prompt (bounded by `maxAttempts`); pre-push and CI block.
7. **`command` is a closed enum, never argv.** Nodes name one of the-loop's own granular
   commands; the runtime constructs the invocation itself. Configuration never becomes a
   command line.
8. **Implement the model; do not import a framework.** Adopt graph engineering's vocabulary
   and shape, write the runtime as thin stdlib Python over the existing
   registry/ControlStore/event log, and take **no new dependency**.
9. **Agent-selected (dynamic) edges are deferred.** The schema reserves the field; the
   runtime rejects it. Routing stays fully static in the first increment.

## Consequences

**Positive.**

- The two halves of issue #109 become decidable rather than exhortative: a skipped step is
  an unmet gate, and an invented step is an undeclared transition.
- The six nodes hiding inside `needs-review` become addressable — gateable, notifiable, and
  visible in graph state — which is where the measured drift lives.
- `notifications.events` and `collaborators.yaml` stop being inert configuration.
- Per-node model routing (`tokenEconomy.modelRouting.stages`) becomes enforceable rather
  than advisory, because a node is an invocation and an invocation carries a model.
- Resumability gets an explicit representation instead of being re-derived by reading prose.

**Negative / accepted costs.**

- A new configuration surface and a new checked-in state file per work item — more to
  validate, version and migrate.
- A component that spawns harness processes from declared configuration; this is real new
  attack surface, mitigated by the closed command enum (7) and enumerated in
  `docs/specs/issue-109/requirements.md` § Security considerations. Risk tier **4**, so
  completion requires a named human security sign-off.
- Operators cannot define custom node commands in the first increment (the price of 7);
  recorded as an open question rather than solved with a general escape hatch.
- In-session enforcement differs mechanically per harness (Claude Code blocks the stop;
  Cursor auto-submits a `followup_message`), so a thin per-harness wrapper is unavoidable
  even though the checker is shared. Cursor caps auto-followups natively while Claude Code
  caps nothing, so the attempt cap is mandatory on the Claude path.

## Alternatives considered

- **Stricter prompts.** This is the status quo, and the drift table is what it produces.
- **Harness hooks as the enforcement mechanism** (the brainstorm's first draft). Rejected on
  the owner's diagnosis: they are too fine-grained and phase-blind to *be* node boundaries.
  Retained as a transport.
- **Importing LangGraph or a similar runtime.** Rejected: it assumes in-process callables
  and serialized checkpoints, where the-loop has CLI subprocesses and checked-in files, and
  it would add a dependency to model something it models poorly. the-loop's checked-in
  checkpoints survive a machine change, a session change and a multi-day human review, and
  are reviewable in a PR diff — a property worth keeping.
- **Parsing the agent's prose for "step complete".** Rejected outright: it reintroduces the
  non-determinism the issue exists to remove. Only structured signals count — exit codes,
  terminal result JSON, hook events, file predicates.
- **Blocking in-session gates by default.** Rejected as the default: a blocking hook without
  a bound can wedge an unattended run. Blocking lives at the repository boundary, where
  failure is visible and recoverable.

## References

- `docs/specs/issue-109/brainstorm.md` — the locked root artifact, the evidence table, and
  the five-layer architecture.
- `docs/specs/issue-109/requirements.md`, `docs/specs/issue-109/design.md`.
- Graph engineering: [LangChain, *3 Years of Graph Engineering with
  LangGraph*](https://www.langchain.com/blog/3-years-of-graph-engineering-with-langgraph);
  [*Graph-Based Agent Workflow Orchestration in Production: the 2026
  Landscape*](https://zylos.ai/research/2026-04-14-graph-based-agent-workflow-orchestration-production/).
  Flow engineering: [AlphaCodium](https://arxiv.org/abs/2401.08500).
