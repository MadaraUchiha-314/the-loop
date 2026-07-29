---
type: execution-log
workItem: issue-113
phase: needs-review       # not-started | brainstorming | requirements-definition | design | tasks-breakdown | implementation | needs-review | complete
status: in-progress          # in-progress | complete
---

# Execution Log: wire the ingress to the process graph

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-07-29 | @MadaraUchiha-314 (PR #114: "approved") | No brainstorm — gap established by code tracing, recorded on the ticket |
| design | 2026-07-29 | @MadaraUchiha-314 (PR #114: "approved") | |
| tasks-breakdown | 2026-07-29 | @MadaraUchiha-314 (PR #114: "approved") | |
| implementation | 2026-07-29 | @MadaraUchiha-314 (PR #114: "approved") | T1–T10 |
| needs-review | 2026-07-29 | @MadaraUchiha-314 (PR #114: "approved") | Tier-4 gates cleared by that comment; completes when #114 merges |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#114](https://github.com/MadaraUchiha-314/the-loop/pull/114) | spec + T1–T9 | open |

## Progress entries

### 2026-07-29 — spec written (requirements → design → tasks)

- **Phase:** tasks-breakdown → implementation
- **Did:** Traced the gap in the tree (graph runtime has one importer; `HookContext.event`
  has zero writers; no node is ever entered on the automated path). Opened
  [#113](https://github.com/MadaraUchiha-314/the-loop/issues/113). Wrote
  `requirements.md` (13 EARS ACs + threat-model-lite, risk tier 4), `design.md`
  (`GraphLink` seam in the shared dispatcher + `Runtime.start()`), `tasks.md` (8-task DAG).
- **Checkpoint/tests:** none yet — no code written.
- **Next:** T1 — `Runtime.start()`, red first.
- **Blockers:** none. Tier 4 means `human-approves-pr` and a named human security
  sign-off before completion; both are requested on the PR.

### 2026-07-29 — implementation complete (T1–T9)

- **Phase:** implementation → needs-review
- **Did:** `Runtime.start()` + `graph.started`; `graphlink.py` (`spec_id_for`,
  `comments_from`, `GraphLink` with all five skip paths); `advance(..., event=)` so
  `HookContext.event` finally has a writer; `graph/bootstrap.build_runtime()` shared with
  `graph_cmd`; `routing.graph` config block (schema + template); two dispatcher call
  sites, rebuilt on hot reload.
- **Unplanned, in scope (T9):** the first integration test to advance a *real* approval
  node parked with `no edge ... on 'pass'`. `ChainOutcome.outcome` read the routing value
  only from a **blocking** result, so `classify-feedback`'s verdict — returned on a
  *passing* result — was discarded, and all three human-approval nodes in `pdlc.yaml`
  could never route. Pre-existing since issue-109, never caught because every existing
  test calls the hook directly rather than through `advance()`. Fixed; AC6 depends on it.
- **Checkpoint/tests:** `make test` → **749 passed, 1 skipped** (was 741 before this work
  item; +29 new). `ruff check` clean, `ruff format` clean, `pyright` 0 errors,
  `markdownlint` 0 errors, `validate_config.py` all VALID. Red→green recorded per task:
  T1 `AttributeError: no attribute 'start'` → pass; T2–T5 `ModuleNotFoundError` → pass;
  T6 `no attribute 'graphlink'` → pass; T9 `assert 'pass' == 'approved'` → pass.
- **Next:** human review of the PR (tier 4 gate) + named security sign-off.
- **Blockers:** the two tier-4 gates below, both awaiting a human.

### 2026-07-29 — CI found a cross-repo collision (T10)

- **Phase:** needs-review
- **Did:** The gate job reported **three** work items instead of one — running the
  suite had written `graph-state.json` into the real `docs/specs/issue-1` and
  `docs/specs/issue-15`, and appended an entry to issue-15's execution log. Not test
  noise: the dispatcher tests use `github:octo/repo#15` → `issue-15` with session
  `cwd` `.`, which is exactly the production shape under the default
  `spawnWorkdir: "."`. The link now requires the checkout's `origin` remote to name
  the work item's own `<owner>/<repo>`, failing closed when it cannot be read
  (AC14/A6). Reverted the three polluted files.
- **Checkpoint/tests:** four red tests first (mismatched origin, no origin, not a
  checkout, matching origin) → green. Full suite **758 passed, 1 skipped**; running
  it now leaves `git status` clean, which is the real regression check.
- **Next:** the two tier-4 human gates.
- **Blockers:** unchanged — human PR approval and named security sign-off.

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | CI gate (the-loop's own) | `the-loop gate` job | Found the cross-repo collision (A6) — fixed in T10 | [run](https://github.com/MadaraUchiha-314/the-loop/actions/runs/30428745582) |
| 2 | human (PR approval + security sign-off) | @MadaraUchiha-314 | approved | [comment](https://github.com/MadaraUchiha-314/the-loop/pull/114) |

## Security review (gate)

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`)
- **Outcome:** pass. Reviewed against the threat model in `requirements.md`. The new
  boundary (untrusted comment text → hook chain) is enforced by `classify-feedback`'s
  existing `authorizedUsers` + `is_self_authored` filter, which the link deliberately
  does not duplicate. A6 (cross-repository spec collision) was found by CI during
  review and closed by the origin-remote check in T10; every abuse case A1–A6 has a
  negative test. No new dependency, no new credential surface.
- **Human sign-off:** @MadaraUchiha-314 — PR #114, comment "approved" (2026-07-29).
  Required because riskTier 4 ≥ `security.review.humanSignOffMinTier: 4`. That comment
  replied to a PR body naming both open tier-4 gates (`human-approves-pr` and the
  security sign-off), and is recorded as clearing both.

## Final validation evidence

- **Test suite:** 758 passed, 1 skipped (741 before this work item; +32 tests).
- **CI on 7982db3:** `checks` green. `gate` red only on the then-unlocked artifacts.
- **The-loop's own gate, after locking:** `the-loop check issue-113 --recompute
  --fail-on block` → **exit 0**, work item at `requirements-approval` in `WAIT`
  ("no authorized feedback yet"), which is the correct state for an open PR.
- **AC coverage:** AC1–AC3 `test_graph_runtime.py::test_start_*`; AC4/AC9/AC11/AC12 +
  A6/AC14 `test_graphlink.py`; AC5/AC6/AC8 `test_graphlink.py::test_on_event_*`,
  `test_spec_id_for_*`; AC6/AC10 + A1 `test_graphlink_integration.py`; AC7 by
  `advance()`'s existing wait/block paths; AC13 `test_eventlog.py`'s catalog drift test.
- **Regression check for A6:** running the full suite leaves `git status` clean — the
  defect's signature was the suite writing into the repo's own `docs/specs`.

### The feature, demonstrated by this very comment

The owner's `approved` on PR #114 is exactly the input this work item makes reachable:
before it, `HookContext.event` had no writer, so `classify-feedback` returned
`waiting("no authorized feedback yet")` no matter what any reviewer wrote — the state
`--recompute` still shows here, because `check` is pure and passes no event. With a
running daemon, that same comment now arrives as an `issue_comment` event, the
dispatcher advances the graph with it attached, and the gate resolves.
