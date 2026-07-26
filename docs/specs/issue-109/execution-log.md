---
type: execution-log
workItem: issue-109
phase: brainstorming          # not-started | brainstorming | requirements-definition | design | tasks-breakdown | implementation | needs-review | complete
status: in-progress           # in-progress | complete
---

# Execution Log: making the-loop deterministic (issue #109)

> Append-only log of progress for the user's visibility. The-loop keeps the work item's
> phase label in the ticketing system in sync with the `phase` front-matter above.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| brainstorming | 2026-07-26 | *(pending — owner)* | Phase 0 entered: the ticket is explicitly exploratory ("how do we make these top level workflow more programmatic?"), so the loop starts at the root artifact. `loop:brainstorming` applied to the issue. |
| requirements-definition |  |  | Blocked on `brainstorm.md` being locked (`status: approved`) — the iterate-until-locked rule. |

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

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | the-loop (Claude Code) | Trimmed speculation not grounded in the repo or the harnesses' documented behaviour; every claim in the evidence table re-derived from the checked-in specs. | this PR |
| 2 | human | @MadaraUchiha-314 | **Finding accepted and fixed** — the Cursor `stop` hook does exist; the "Cursor degrades to CI-only" framing was wrong. See the 2026-07-26 entry below. | [PR #110 review comment](https://github.com/MadaraUchiha-314/the-loop/pull/110) |

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
