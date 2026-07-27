---
type: execution-log
workItem: issue-109
phase: design                 # not-started | brainstorming | requirements-definition | design | tasks-breakdown | implementation | needs-review | complete
status: in-progress           # in-progress | complete
---

# Execution Log: making the-loop deterministic (issue #109)

> Append-only log of progress for the user's visibility. The-loop keeps the work item's
> phase label in the ticketing system in sync with the `phase` front-matter above.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| brainstorming | 2026-07-26 | @MadaraUchiha-314 (PR #110, 2026-07-27) | Phase 0 entered: the ticket is explicitly exploratory, so the loop started at the root artifact. Two review rounds (Cursor hook correction; graph architecture). **Locked** on *"let's go ahead with the requirements and design"*. |
| requirements-definition | 2026-07-27 | *(pending — this PR)* | `requirements.md` derived from the locked brainstorm. 10 requirements in EARS, threat-model-lite, risk tier **4** (touches `**/*schema*` → `human-approves-pr` + named security sign-off). Seven brainstorm open questions resolved as **stated assumptions** so review can override them. |
| design | 2026-07-27 | *(pending — this PR)* | `design.md` derived from the requirements. Five-layer architecture, closed gate/edge vocabularies, `graph-state.json` data model, security design per boundary, testing strategy. Decision recorded as `decision-041`. |
| tasks-breakdown |  |  | Not started — the owner asked for requirements and design only. |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#110](https://github.com/MadaraUchiha-314/the-loop/pull/110) | Phase 0 — `brainstorm.md` + this log | open |

## Progress entries

### 2026-07-26 — Phase 0 brainstorm drafted

- **Phase:** brainstorming
- **Did:**
  - Read the operating model (`CLAUDE.md`, `.the-loop/harness-config.yaml`,
    `skills/the-loop/SKILL.md`, `reference/workflow.md`, `reference/automation.md`) and the
    CLI's session machinery (`webhook/dispatcher.py`, `harness/base.py`,
    `harness/claude_code.py`, `runner.py`) to answer the ticket's mechanical questions
    from the code rather than from memory.
  - Measured the non-determinism the ticket describes against this repo's own checked-in
    specs (34 spec folders): 24/34 carry `tasks.md`, 25/34 carry `execution-log.md`,
    15/28 `requirements.md` and 16/33 `design.md` are still `status: draft` despite the
    work having shipped, and **0 of 25** execution logs reach `phase: complete` while 22
    sit at `needs-review` — against 15 issues labelled `loop:complete`. The two mirrors of
    the phase state machine disagree on 22 work items, unnoticed.
  - Confirmed the completion-signal question from the harnesses' documented behaviour:
    Claude Code's `Stop` hook and `Notification` matchers (`agent_needs_input`,
    `permission_prompt`, `idle_prompt` vs `agent_completed`) already distinguish
    "waiting for a human" from "turn finished"; headless `-p --output-format json` makes
    the question moot by exiting with a terminal result object.
  - Wrote `docs/specs/issue-109/brainstorm.md`: problem + evidence, constraints, the
    ticket's mechanical questions answered, seven options (A–G) with the rejected
    alternatives and *why*, two mermaid sketches, seven open questions, and a
    verify-first-orchestrate-second working hypothesis.
- **Checkpoint/tests:** documentation-only change — no code touched. Markdown lint is the
  applicable gate (`tooling.lint.markdown`): `npx markdownlint-cli2@0.18.1
  "docs/specs/issue-109/*.md"` → 0 errors. CI (`checks`) green on PR #110. No
  unit/integration surface exists for this phase.
- **Next:** owner feedback on the seven open questions (scope, gate hardness, Claude-first
  enforcement, verification-vs-orchestration, resident-vs-per-step sessions, strictness of
  "no extra steps", retrofit policy). When answered, set `status: approved` + `approvedBy`
  on `brainstorm.md`, advance the label to `loop:requirements-definition`, and derive
  `requirements.md` from the locked brainstorm.
- **Context:** no reset — single-phase, single-window work.
- **Blockers:** the brainstorm cannot be locked without the owner's answers; raised as a
  ticket comment (paper trail).

### 2026-07-26 — Cursor hook coverage corrected (owner review finding)

- **Phase:** brainstorming
- **Did:** @MadaraUchiha-314 challenged the claim that in-session enforcement would be
  Claude-first, pointing at Cursor's documented `stop` hook. Re-checked against Cursor's
  hook documentation: the finding is right, and the correction is stronger than a fix —
  **Option C is cross-harness.** Cursor's `stop` fires at the end of *each agent turn*, and
  while it cannot block completion the way Claude Code's `Stop` can (exit 2 /
  `decision: "block"`), it returns a `followup_message` that Cursor **auto-submits as the
  next user turn** — closing exactly the same enforcement loop by a different mechanism.
  Corrected the completion-signal matrix, added a **continuation matrix**, rewrote Option
  C's pro/con, the cross-harness constraint, the mermaid edge (`Cursor degrades to D` →
  both harnesses enforce in-session), open question 3, the hand-off, and the references.
  One consequence worth flagging: the runaway-protection asymmetry runs the *other* way —
  Cursor caps auto-followups natively (configurable `loop_limit`, hard max 5) while Claude
  Code caps nothing, so the attempt cap is required on the **Claude** path.
- **Checkpoint/tests:** `npx markdownlint-cli2@0.18.1 "docs/specs/issue-109/*.md"` →
  0 errors.
- **Next:** unchanged — the remaining six open questions still gate locking the brainstorm.
  Open question 3 is narrowed from "is Claude-first acceptable?" to a five-minute
  experiment: does `stop` fire in the `cursor-agent` **CLI** surface (what the-loop drives)
  or only in the IDE? Reports conflict; run it before requirements lock.
- **Blockers:** unchanged.

### 2026-07-26 — architecture redirected to a graph model (owner direction)

- **Phase:** brainstorming
- **Did:** @MadaraUchiha-314 named the real defect on PR #110: *"there's no clear
  definition and hooks around logical 'node' boundaries… the hooks provided by the agent
  harnesses are too fine grained and lack the appropriate details to figure out which phase
  of the-loop we are in"* — and asked for a **graph** of the-loop's nodes with an
  orchestration layer determining the edges (static now, dynamic later), plus an answer on
  whether this is the literature's "graph engineering".
  - **Accepted and designed.** Added § *Architecture: the-loop as a graph* — five layers:
    graph data (nodes/edges with `produces`/`requires`/`gate`/`actor`/`stage`/`notify` and
    `when` edges, cycles first-class), graph state (checked-in `currentNode` + attempts),
    **node-lifecycle hooks** (`onEnter`/`onExit`/`onGateFail`/`onAwaitHuman`/`onEscalate`),
    transports (orchestrated / resident-session tick / event-driven / CI backstop), and
    bounded dynamic edges (the agent *selects among declared* edges, never invents one).
  - **Confirmed the critique against this repo's own numbers.** 23 of 26 execution logs
    sit at `phase: needs-review`, and `needs-review` is a single label covering six
    distinct nodes (self-review, critic-review, security-review, evidence, capability-docs,
    reviewer-briefing). The drift is not uniform — **it concentrates exactly where node
    granularity runs out.** This is now the strongest single piece of evidence in the
    brainstorm, and it argues the owner's case rather than the earlier draft's.
  - **Corrected my own framing.** The earlier draft treated a harness `Stop` event as if it
    were a node boundary. It is not: it fires many times per node and carries no phase.
    New principle recorded — **harness hooks are a clock, not a state machine**; they say
    *when* to look, the graph says *what we are looking at*. This rescues the hook work as
    a transport rather than discarding it.
  - **Answered the literature question: yes, and the term is current.** The lineage is
    prompt engineering → **flow engineering** (AlphaCodium, 2024) → **graph engineering**
    (2026): explicit workflow graphs modelled as state machines, canonical representation
    being the stateful directed graph with typed nodes, conditional edges and persistent
    checkpoints, cycles treated as a feature. Recommended adopting the *model and
    vocabulary* while **implementing rather than importing** — the-loop's nodes are harness
    CLI subprocesses and its checkpoints are checked-in files, neither of which an
    in-process graph library serves.
  - Re-cast options A–G as layers of the architecture (nothing discarded), resolved open
    question 4 (orchestration, per the owner), and opened questions 8–11 (node granularity,
    where graph state lives, graph vs `workflow.phases`, bounding dynamic edges).
- **Checkpoint/tests:** `npx markdownlint-cli2@0.18.1 "docs/specs/issue-109/*.md"` →
  0 errors.
- **Next:** owner review of the architecture, then questions 1, 2, 7, 8, 9, 10 before the
  brainstorm can be locked. Question 4 is now closed.
- **Blockers:** unchanged — the brainstorm stays `status: draft`.

### 2026-07-27 — brainstorm locked; requirements and design derived

- **Phase:** brainstorming → requirements-definition → design
- **Did:**
  - **Locked `brainstorm.md`** (`status: approved`, `approvedBy: @MadaraUchiha-314`) on the
    owner's *"let's go ahead with the requirements and design"* (PR #110).
  - **`requirements.md`** — 10 requirements in EARS covering the declared graph (R1),
    durable graph state (R2), pure gate evaluation (R3), node-lifecycle hooks and
    notifications (R4), the orchestrated transport (R5), resident/event transports (R6),
    the repository-boundary hard gate (R7), bounded recovery (R8), backwards compatibility
    (R9) and observability (R10). Risk tier set to **4**: the change touches
    `autonomy.sensitivePaths` (`**/*schema*`), so `autonomy.tiers` gives `human-approves-pr`
    and `security.review.humanSignOffMinTier: 4` additionally requires a **named human
    security sign-off** before completion.
  - **Threat-model-lite written, not waved away.** This work item *does* add attack surface.
    Four boundaries enumerated with six abuse cases: config→process execution (a node
    carrying free-form argv would be arbitrary command execution), **agent→graph state**
    (the subject of the gate can write the gate's bookkeeping), gate-result→harness input
    (prompt-injection surface), and node-events→external channels.
  - **`design.md`** — the five layers as components (`the_loop/graph/{model,gates,state,
    runtime,notify}.py` plus two commands and per-harness hook wrappers), closed
    vocabularies for gate predicates and edge conditions, the `graph-state.json` schema, an
    error-handling table, a security design mapping every boundary to its mechanism and
    negative test, and a requirement→scenario testing matrix. UI/UX: N/A (CLI).
  - **Two design calls worth flagging to the reviewer.** (1) `command` is a **closed enum**,
    not a string to execute — the runtime builds the argv itself, which closes the largest
    new attack surface at the data model rather than with validation. (2) **Graph state is a
    cache, not an authority** — `--recompute` derives completion from artifacts alone and the
    CI gate always uses it, so an agent editing its own scorecard cannot pass a gate.
  - **`decision-041`** recorded and indexed: model the process as a graph with node-lifecycle
    hooks, harness hooks as a clock, implement rather than import. It also closes the "open
    design question" that has sat unanswered at the end of `reference/workflow.md`.
  - Seven brainstorm open questions resolved as **explicit assumptions** in a table at the
    top of `requirements.md`, each stated so this phase's review can override it — rather
    than silently absorbed (`reference/workflow.md`: keep moving, log the assumption).
- **Checkpoint/tests:** `npx markdownlint-cli2@0.18.1` over the changed markdown → 0 errors;
  `uv run python scripts/validate_config.py` → config still valid (no schema change yet —
  the schema lands with implementation).
- **Deviation, authorized:** the-loop's rule is that a downstream artifact is derived only
  from a *locked* upstream one. The owner directed requirements **and** design in one pass,
  so both are drafted together and reviewed in the same PR. Recorded here and in
  `design.md`'s header rather than passed over; if the requirements review changes anything
  material, the design is revised before tasks.
- **Next:** owner review of `requirements.md` and `design.md`. On approval, set both to
  `status: approved`, advance to `loop:tasks-breakdown` and derive `tasks.md`. Three open
  questions want answers first: the closed command vocabulary vs. operator-defined commands,
  `graph-state.json` vs. execution-log front-matter, and who provides the tier-4 security
  sign-off.
- **Blockers:** phase approval for requirements and design (`requireHumanReviewPerPhase`).

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | the-loop (Claude Code) | Trimmed speculation not grounded in the repo or the harnesses' documented behaviour; every claim in the evidence table re-derived from the checked-in specs. | this PR |
| 2 | human | @MadaraUchiha-314 | **Finding accepted and fixed** — the Cursor `stop` hook does exist; the "Cursor degrades to CI-only" framing was wrong. See the 2026-07-26 entry below. | [PR #110 review comment](https://github.com/MadaraUchiha-314/the-loop/pull/110) |
| 3 | human | @MadaraUchiha-314 | **Direction accepted** — model the process as a graph of nodes with an orchestration layer determining edges; harness hooks are too fine-grained and phase-blind to be node boundaries. Architecture added; options re-cast as its layers. | [PR #110 comment](https://github.com/MadaraUchiha-314/the-loop/pull/110) |
| 4 | human | @MadaraUchiha-314 | **Brainstorm locked** — *"let's go ahead with the requirements and design"*. Phase advanced; both artifacts derived. | [PR #110 comment](https://github.com/MadaraUchiha-314/the-loop/pull/110) |
| 5 | self | the-loop (Claude Code) | Checked the derived artifacts against the phase gates: EARS throughout, Security considerations non-empty and specific, every requirements-phase trust boundary enforced in `design.md` § Security design, testing strategy mapping every requirement to a named Gherkin scenario. Risk tier raised 3 → 4 on the `**/*schema*` sensitive-path rule rather than left at the default. | this PR |

## Security review (gate)

- **Mechanism:** n/a for this phase — the change is a checked-in markdown artifact; no
  code, no dependency, no configuration, no execution path. The security question belongs
  to `requirements.md`'s **Security considerations** section, where the options that
  actually carry a trust boundary (a `Stop` hook that can block a turn; a CI gate that can
  block a merge; an orchestrator that invokes a harness) will be threat-modelled.
- **Outcome:** deferred to the requirements phase (recorded, not skipped).
- **Human sign-off:** n/a — risk tier below `security.review.humanSignOffMinTier`.

## Capability docs

None affected. This work item has produced no behaviour change yet; the capability docs
(`docs/capabilities/spec-workflow.md`, `cli.md`) are updated in the PR that implements
whatever the locked requirements ask for.

## Final validation evidence

Not applicable at Phase 0. The deliverable is the brainstorm artifact itself; its
acceptance is the owner locking it (`status: approved` + `approvedBy`).
