# Capability: spec-workflow

> The core loop: a work item is specified as a chain of artifacts — optional brainstorm,
> then a Kiro-style 3-phase spec — each iterated with human feedback until locked, then
> executed end-to-end with minimal intervention.

## What it is

The product-development-lifecycle workflow the-loop runs on every work item, exposed as
the `/the-loop:work-on` superset command and granular per-step commands
(`brainstorm`, `new-requirement`, `create-ticket`, `create-design`, `create-tasks-plan`,
`execute-tasks`, `finish-tasks`, `work-status`).

## Current behaviour

- Every work item SHALL have a ticket; nothing is worked without one.
- A work item's spec SHALL live in `docs/specs/<id>/` as the artifact chain
  `brainstorm.md (optional) → requirements.md|bugfix.md → design.md → tasks.md`, plus
  `execution-log.md`.
- `requirements.md` and `bugfix.md` SHALL be two accepted names for the **same** phase-1
  artifact, not two artifacts. Either clears the `requirements-definition` gate, held to
  the identical standard; **both present blocks**, because two phase-1 artifacts in one
  folder have no defined source of truth
  ([decision-045](../decisions/decision-045.md)). Both bundled templates carry the
  `## Requirements` and `## Security considerations` sections the gate requires, so the
  choice is about which shape fits the work — reproduction and root cause, or user stories
  — and never about which one will pass.
- Each artifact SHALL be iterated with feedback until **locked** (`status: approved`);
  no downstream artifact is written against an unlocked upstream one
  (`workflow.requireHumanReviewPerPhase`, default true).
- WHEN a work item starts as a fuzzy idea THEN the loop SHALL begin with a
  `brainstorm.md` root artifact (optional Phase 0) and convert it to requirements once
  locked.
- The work item's phase SHALL be tracked on the ticket via labels
  (`<workflow.phaseLabelPrefix><phase>`) through the state machine
  `not-started → brainstorming (optional) → requirements-definition → design →
  tasks-breakdown → implementation → needs-review → complete`, mirrored in the
  execution log.
- `tasks.md` SHALL be a DAG of small verifiable tasks referencing requirements;
  checkmarks are kept current during implementation.
- **Security SHALL be a gated concern of each phase** (`config.security`):
  requirements/bugfix carry a Security considerations threat-model-lite (untrusted
  actors, trust boundaries, abuse cases, fail-closed — "no new attack surface" is
  written and justified, never implied); design carries a Security design section
  enforcing every boundary; security-relevant tasks name the negative test proving the
  boundary holds.
- Completion SHALL be gated by the ready-to-ship gate (green checks, threads resolved,
  evidence, **a passed security review** — built-in security-review skill or the-loop's
  checklist per `security.review.mechanism` — PR briefing, capability docs folded in)
  and risk-tiered autonomy (`config.autonomy`); an effective risk tier ≥
  `security.review.humanSignOffMinTier` (default 4) SHALL wait for a named human
  security sign-off, and an unresolved security finding SHALL block completion at any
  tier.
- The loop SHALL read and honor the operator's **custom instruction docs**
  (`config.customInstructions`): every registered doc is read, in order, immediately
  after loading the config when work on an item starts (and re-read after a context
  clear). The structured config wins where both speak; no instruction doc can weaken
  the loop's gates (security, paper trail, reviews, autonomy) — such instructions are
  ignored and the conflict logged, fail-closed. A missing doc is handled per
  `customInstructions.onMissing` (default `warn`).
- The loop SHALL manage its context window by **checkpoint-then-reset**
  (`config.contextManagement`): a reset (clear or compact) is always preceded by a
  checkpoint — `tasks.md` checkmarks current, an execution-log entry with a concrete
  next step, the phase label in sync, WIP committed or noted.
- WHEN the phase advances across a locked artifact (most importantly
  tasks-breakdown → implementation) THEN the loop SHALL reset per
  `contextManagement.phaseBoundary` (default `clear`) and derive the next phase's work
  from the checked-in artifacts, not the conversation.
- WHEN a task in the DAG completes THEN the loop SHALL checkpoint and reset per
  `contextManagement.taskBoundary` (default `compact`); mid-task only compaction is
  permitted (`midTask`), never clearing. Headless sessions reset by ending at the
  boundary and resuming fresh via the execution log.
- **The phase state machine SHALL be executable, not only described.** Each phase above
  is a **node** in the shipped process graph, with entry/exit hook chains that decide
  when it is complete and declared edges that route on those decisions
  ([process-graph](process-graph.md), issue-109). The prose in `reference/workflow.md`
  and the graph in `cli/the_loop/graph/pdlc.yaml` describe the same loop; the graph is
  the one that runs. `the-loop check <id>` reports where a work item actually stands
  against its checked-in artifacts, and `--recompute` derives that verdict from the
  artifacts alone rather than trusting stored state.
- **A work item may be delivered by several PRs.** WHEN more than one PR delivers a
  work item (a spec PR then an implementation PR, a stacked series, a follow-up after
  review, one PR per repository) THEN the loop SHALL label **each** of them for routing
  and list **all** of them in the execution log's **Pull requests** table, and
  `finish-tasks` SHALL require every listed PR to be merged or closed before the work
  item is marked complete — one PR merging is not the work item ending (issue-101).

## Design

[`reference/workflow.md`](../../skills/the-loop/reference/workflow.md) ·
[`reference/context.md`](../../skills/the-loop/reference/context.md) ·
[`reference/instructions.md`](../../skills/the-loop/reference/instructions.md) ·
[`reference/security.md`](../../skills/the-loop/reference/security.md) ·
[`SKILL.md`](../../skills/the-loop/SKILL.md) ·
[architecture § the loop](../architecture/architecture.md)

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-124 | A bug's `bugfix.md` clears the phase-1 gate it always should have: the two documented names became alternatives for one artifact, both present blocks, and the bundled bugfix template gained the `## Requirements` heading the gate asks for | [spec](../specs/issue-124/), [decision-045](../decisions/decision-045.md), [process-graph](process-graph.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/124) |
| issue-109 | The phase state machine became executable: every phase is a node in the shipped process graph, with hook chains deciding completion and declared edges routing on the outcome | [spec](../specs/issue-109/), [process-graph](process-graph.md), [decision-041](../decisions/decision-041.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/109) |
| issue-101 | The execution log tracks a **list** of the PRs delivering a work item; each is labelled for routing and all must be merged/closed before `finish-tasks` completes the item | [spec](../specs/issue-101/), [decision-039](../decisions/decision-039.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/101) |
| issue-59 | Added per-installation custom instruction docs the loop reads and honors (`customInstructions` config, onboarding group, precedence rules) | [spec](../specs/issue-59/), [decision-029](../decisions/decision-029.md) |
| issue-48 | Added checkpoint-then-reset context-window management (clear at phase boundaries, compact at task boundaries, `contextManagement` config) | [spec](../specs/issue-48/), [decision-027](../decisions/decision-027.md) |
| issue-47 | Security became a gated concern of every phase: threat-model-lite in requirements, Security design section, security-review gate item, risk-tiered human sign-off (`config.security`) | [spec](../specs/issue-47/), [decision-026](../decisions/decision-026.md) |
| issue-25 | Added the capability-docs fold-in as a ready-to-ship gate item | [spec](../specs/issue-25/), [decision-020](../decisions/decision-020.md) |
| issue-18 | Design phase gained first-class UI/UX design artifacts | [spec](../specs/issue-18/), [decision-018](../decisions/decision-018.md) |
| issue-17 | Added the optional brainstorming phase and the iterate-until-locked rule as a first-class principle | [spec](../specs/issue-17/), [decision-017](../decisions/decision-017.md) |
| issue-1 | Established the 3-phase Kiro-style spec workflow, phase labels, granular commands and templates (v0) | [spec](../specs/issue-1/), [decision-004](../decisions/decision-004.md), [decision-011](../decisions/decision-011.md) |
