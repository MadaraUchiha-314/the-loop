---
type: execution-log
workItem: "issue-161"
phase: requirements-definition
status: in-progress
---

# Execution Log: control plane and API layer for the-loop

> Append-only log of progress for the user's visibility. Checked in alongside the spec
> at `docs/specs/issue-161/`.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-08-05 | _(pending — tier-4 program: this phase gate is human-reviewed on the spec PR)_ | Issue #161: re-architect into core / API layer / clients (CLI, MCP, UI). |
| design |  |  | Starts only after requirements lock (`status: approved`). |
| tasks-breakdown |  |  | Expected to decompose delivery into sub-issues (DAG across work items). |
| implementation |  |  |  |
| needs-review |  |  |  |
| complete |  |  |  |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| _(spec PR)_ `claude/github-issue-161-qto8z0` | Phase 1 requirements only | open |

## Progress entries

### 2026-08-05 — requirements drafted

- **Phase:** requirements-definition
- **Did:** read issue #161; surveyed the current CLI surface
  ([capability: cli](../../capabilities/cli.md), `cli/the_loop/` — ~18.5k lines,
  133 files) to ground the parity requirement (R2) in the real command list. Drafted
  `requirements.md`: three-layer architecture (R1), CLI feature parity with a
  preserved in-process mode (R2), durable contract-first API layer (R3), CLI-owned
  service/UI lifecycle (R4), MCP as an interface adapter (R5), statically-hostable
  control-plane UI (R6); threat-model-lite names the API-service-as-RCE boundary and
  binds loopback-by-default, fail-closed.
- **Judgement call — spec PR first, implementation in follow-ups:** this item
  re-layers the entire CLI and adds three new surfaces; `riskTier: 4` and
  `workflow.requireHumanReviewPerPhase: true` mean nothing downstream may be written
  against an unlocked requirements artifact. Unlike the recent bounded bugfixes
  (issue-154/156/159, where the whole loop fit one PR), drafting design/tasks or code
  now would bake in architecture decisions (API stack, CLI↔service relationship, UI
  toolchain, MCP transport) the owner hasn't weighed in on — those are recorded as
  open questions instead. Multi-PR delivery per work item is the sanctioned pattern
  (execution-log template: "a spec PR then an implementation PR").
- **Checkpoint/tests:** markdown lint on the new files (evidence on the PR).
- **Next:** owner reviews/locks `requirements.md` on the spec PR (answers to the five
  open questions welcome as review comments) → then `create-design` derives
  `design.md` from the locked requirements, including UI design artifacts under
  `design/`.
- **Blockers:** phase gate — human review of Phase 1 (tier 4).

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self (spec re-read against issue #161 + capability docs) | harness | zero (converged) | — |

## Security review (gate)

> Runs at ready-to-ship (implementation PRs). This spec PR carries no code; the
> threat model itself is in `requirements.md` § Security considerations. Tier 4 ⇒ a
> named human security sign-off will be required on the implementation.

- **Mechanism:** _(pending — implementation phase)_
- **Outcome:** _(pending)_
- **Human sign-off:** _(required at tier 4; pending)_

## Final validation evidence

Pending — recorded when implementation lands.
