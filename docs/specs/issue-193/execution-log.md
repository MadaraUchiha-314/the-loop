---
type: execution-log
workItem: issue-193
phase: implementation
status: in-progress
---

# Execution Log: a default harness config for repositories that never adopted the-loop

> Append-only log for issue-193. Ticket:
> [#193](https://github.com/MadaraUchiha-314/the-loop/issues/193).

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-10 | @MadaraUchiha-314 (out of band) | The owner assigned this ticket directly to a cloud session rather than through the daemon, so no checklist was posted on the ticket and no `the-loop execute` reply exists. The full process was run — no phase was declared away, and the harness declared none. |
| requirements-definition | 2026-08-10 | | `requirements.md` locked — four requirements: the built-in default, the ingress adopting, the CLI's mutating verbs adopting, and the contribution loop never adopting its host. |
| design | 2026-08-10 | | `design.md` locked. One data file, one writer, two call sites, one carve-out; the load-bearing choice is adopting *after* the ownership proof and *before* the spec-directory gate, so the config is written even on the run whose graph is skipped. |
| test-planning | 2026-08-10 | | `testing-plan.md` locked — 13 rows, 6 `n/a` with reasons. |
| tasks-breakdown | 2026-08-10 | | `tasks.md` locked — 9 tasks, DAG drawn. |
| implementation | 2026-08-10 | | Tasks 1–8. |
| verification | 2026-08-10 | | Plan executed; results and evidence recorded. |
| needs-review | 2026-08-10 | | Self-review; awaiting the human gate on the PR. |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| MadaraUchiha-314/the-loop — `claude/github-issue-193-x96m3i` | the whole work item (tasks 1–9) | open |

## Progress entries

### 2026-08-10 — spec chain

- **Phase:** requirements-definition → design → test-planning → tasks-breakdown
- **Did:** Read the ticket, the harness-config read surface (issue-121/decision-044), the
  ingress→graph coupling and issue-185's uninitialized-repository rules, then wrote and
  locked the four spec artifacts. The design question that took the time: adopting a
  repository is exactly what PR #187 forbade for a *contribution*, so the two had to be
  told apart rather than reconciled — the carve-out is R4 and it is enforced at both call
  sites.
- **Checkpoint/tests:** none yet (no code).
- **Next:** implement tasks 1–8.

### 2026-08-10 — implementation

- **Phase:** implementation
- **Did:** Tasks 1–8. The packaged default (`cli/the_loop/harness-config.default.yaml`,
  a byte-for-byte copy of the `/the-loop:init` template); `defaults()`,
  `default_config_path()` and `scaffold()` in `harness_config.py` — the only writer, with
  the provenance header, the `ticketing.github` substitution and its allow-list; the
  `harness.config_scaffolded` event; `GraphLink._adopt` on the ingress path, with the
  outer-loop resolution hoisted so the contribution carve-out and the runtime build share
  one answer; `core.graphs._runtime(adopt=...)` passed by the four state-changing verbs
  and by no reader; the parity assertions (byte parity with the template, the schema via
  `scripts/validate_config.py`, the phase sequence via `test_graph_parity.py`'s
  parametrization, and the surviving per-key literals pinned to the packaged file); and
  the documentation, capability rows and decision-073.
- **Checkpoint/tests:** red→green on all 26 new tests (18 unit, 7 integration, 1 parity
  parametrization); `make test` — 1712 passed, 1 skipped. No existing test needed
  changing: adoption writes only where the ownership proof already passed, and the
  checkouts existing tests build either carry a config or are foreign.
- **Next:** verification (task 9).

### 2026-08-10 — verification

- **Phase:** verification
- **Did:** Executed `testing-plan.md` — every activity in the matrix, none replanned —
  and committed the evidence under `evidence/`.
- **Checkpoint/tests:** T1/T2/T7/T8/T10 targeted runs, `make test` (1712 passed, 1
  skipped), `make lint format-check typecheck validate` (ruff clean, 523 markdown files
  0 errors, pyright 0 errors, 7 configs VALID).
- **Next:** self-review, the security review gate, then the reviewer briefing on the PR.

## Verification results

> Only when this work item declared `test-planning` away. It did not: the results live in
> [`testing-plan.md`](testing-plan.md) § Verification results, against the matrix rows
> that planned them.

## Design critic review

> Not selected. `design-critic-review` is opt-in (issue-188) and this work item did not
> tick it.

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| | | | | |

## Security review (gate)

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`)
- **Outcome:** *pending*
- **Human sign-off:** n/a — risk tier 3, below `security.review.humanSignOffMinTier: 4`

## Final validation evidence

*Pending verification.*

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| | | |

## Documentation

| Document | What changed |
|----------|--------------|
| | |
