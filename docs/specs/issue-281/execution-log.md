---
type: execution-log
workItem: "issue-281"
phase: needs-review
status: in-progress
---

# Execution Log: lock artifacts at the approval gate

> Append-only log for [issue #281](https://github.com/MadaraUchiha-314/the-loop/issues/281).
> Worked in a single Claude Code cloud session (tier 3, `human-approves-pr`): the spec
> chain and the change ship in one PR, and the PR's human approval is the gate.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-08-25 | with the PR | `bugfix.md` — root cause confirmed from the graph + hooks source |
| design | 2026-08-25 | with the PR | lock-at-the-gate; `lock-artifacts` hook |
| test-planning | 2026-08-25 | with the PR | matrix: unit, graph integration, e2e |
| tasks-breakdown | 2026-08-25 | n/a — no gate | five tasks, all complete |
| implementation | 2026-08-25 | — | hook + both graphs + skills/commands |
| verification | 2026-08-25 | — | full suite, lint, types, markdown |
| needs-review | 2026-08-25 | pending | PR opened for human review |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| the-loop PR for `claude/github-issue-281-1nrn5o` (T1–T5) | whole work item | open |

## Progress entries

### 2026-08-25 — implemented lock-at-the-gate end to end

- **Phase:** implementation → verification
- **Did:** added the `lock-artifacts` hook (front-matter splice, fail-closed
  verification, approver recording); dropped `locked: true` from every producing node
  in `pdlc-work-item-loop` and `pdlc-contribution-loop`; wired the hook into
  `requirements-approval`, `design-approval` and `plan-approval`; removed
  session-owned approval steps from the skill, the workflow reference and six
  commands; re-based the e2e suite on draft fixtures so the gates' locking is what
  the happy path proves.
- **Checkpoint/tests:** `uv run pytest` (full suite) pass; `ruff check` + `ruff
  format --check` pass; `pyright` pass. See `evidence/test-run.md`.
- **Next:** PR review.
- **Blockers:** none.

## Verification results

> This work item has a `testing-plan.md`; results are recorded there
> (`docs/specs/issue-281/testing-plan.md` § Verification results). This section
> intentionally holds only that pointer.

## Design critic review

> Not selected for this work item (single-session cloud walk; the design is reviewed
> with the PR).

| Round | Critic (`<harness>/<model>`) | Outcome | Findings → disposition | Link |
|-------|-----------------------------|---------|------------------------|------|
| — | not selected | n/a | n/a | — |

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | session | new findings — two stale tests asserted the pre-fix contract (`test_graph_model`, `test_graph_verification_integration`); updated to the gate-owned lock | this PR |
| 2 | self | session | new findings — `create-testing-plan.md` step 1 demanded a locked design *before* its gate (self-contradiction predating this fix); reworded to "complete, still draft" | this PR |
| 3 | self | session | zero (converged) — full suite green, docs sweep found no remaining pre-gate approval language | this PR |

## Security review (gate)

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`, no
  security-review skill in this session)
- **Outcome:** pass — `lock-artifacts` consumes only the same-chain
  `classify-feedback` verdict (authorized, non-self-authored authors only), so who can
  approve is unchanged; the write is a local spec-directory splice, verified after
  writing and failing closed; handles are quote-stripped before being spliced into
  YAML so no handle can alter front-matter syntax. Removing `locked:` from producing
  nodes removes no human decision: every artifact that had a gate keeps it.
- **Human sign-off:** n/a (tier 3 < `security.review.humanSignOffMinTier: 4`)

## Final validation evidence

Acceptance criteria → proof, summarised from `testing-plan.md`:

- **AC 1.1** (producing nodes gate shape only): `test_graph_model` /
  `test_graph_verification_integration` assert `locked` absent and a draft plan
  passing; e2e fixtures are drafts and every producing node passes.
- **AC 1.2** (the gate locks and records the approver):
  `test_an_approval_locks_the_artifact_and_records_the_approver`, and the e2e
  happy path's `lockedBeforeImplementation` — draft fixtures reach
  `implementation` as `status: approved`.
- **AC 1.3** (`changes-requested` never locks):
  `test_changes_requested_leaves_the_artifact_unlocked`, plus the
  `review-rejection` scenario looping design back and converging.
- **AC 1.4** (absent artifact = planned absence):
  `test_an_absent_artifact_is_a_planned_absence_not_a_block`.
- **AC 1.5** (regression walk): the reworked `happy-path` scenario — unlocked
  fixtures, one approval per gate, locked at implementation — fails on the pre-fix
  graph (a draft artifact blocked its producing node) and passes now.
- **AC 2.1** (`tasks-breakdown` needs no human): happy path advances
  `tasks-breakdown → implementation` with no approval comment in between, and
  `tasks.md` is deliberately absent from `lockedBeforeImplementation`.
- **AC 2.2 / 2.3** (skills stop re-implementing approvals): `SKILL.md`,
  `reference/workflow.md`, and the `brainstorm`, `new-requirement`, `create-design`,
  `create-testing-plan`, `create-tasks-plan`, `work-on`, `contribute-to` commands no
  longer instruct a session to request or block on an approval, or to set
  `status: approved`.

Raw run output: `evidence/test-run.md`.

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| `docs/capabilities/process-graph.md` | `lock-artifacts` added to the shipped-hook vocabulary with its contract; test-planning/human-gate sections updated to the gate-owned lock | issue-281 row added |
| `docs/capabilities/spec-workflow.md` | The iterate-until-locked rule became the gate-owned lock; brainstorm/testing-plan bullets updated | issue-281 row added |

## Documentation

| Document | What changed |
|----------|--------------|
| `README.md` | Artifact-chain paragraph: the gate locks on the human's one approval; gate-less artifacts advance on shape |
| `docs/guide/what-is-the-loop.md` | Same rework of the chain description, the opt-in critic ("completed design"), and the designer loop |
| `skills/the-loop/SKILL.md` + `reference/workflow.md`, `reference/design-artifacts.md`, `reference/collaboration.md` | Approvals owned by approval nodes; sessions never lock or re-request |
| `commands/*` (brainstorm, new-requirement, create-design, create-testing-plan, create-tasks-plan, work-on, contribute-to) | Pre-gate approval steps removed; gate-less phases proceed on shape |
