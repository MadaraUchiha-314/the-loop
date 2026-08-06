---
type: execution-log
workItem: issue-167
phase: needs-review          # not-started | brainstorming | requirements-definition | design | test-planning | tasks-breakdown | implementation | verification | needs-review | complete
status: in-progress          # in-progress | complete
---

# Execution Log: six graph nodes gate on execution-log sections without declaring an artifact

> Append-only log of progress for the user's visibility. Checked in alongside the spec at
> `docs/specs/issue-167/execution-log.md`.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-08-06 | pending (PR) | filed as a bugfix; written as `requirements.md` because the fix adds vocabulary, not only a repair |
| design | 2026-08-06 | pending (PR) | option 2 (`validates:`) + option 3 (fail closed); option 1 rejected — decision-063 |
| test-planning | 2026-08-06 | pending (PR) | reviewed with the design, one gate for both (decision-060 D2) |
| tasks-breakdown | 2026-08-06 | pending (PR) | 7 tasks: T1/T2 → T3 → T4/T5 → T6 → T7 |
| implementation | 2026-08-06 | — | T1–T6 |
| verification | 2026-08-06 | — | T7; every activity ran |
| needs-review | 2026-08-06 | pending | 3 self-review rounds; critic rounds unavailable (none configured) |
| complete | — | — | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#170](https://github.com/MadaraUchiha-314/the-loop/pull/170) | the whole work item — T1–T7 | open |

## Progress entries

### 2026-08-06 — spec chain written and locked

- **Phase:** requirements-definition → tasks-breakdown
- **Did:** wrote `requirements.md`, `design.md`, `testing-plan.md`, `tasks.md`. Chose
  option 2 (`validates:`) with option 3 (fail closed) as its backstop, and rejected
  option 1 because `produces` means authorship and the manifest's deliberately phase-less
  `execution-log.md` entry is exactly what P1/P2 key on.
- **Checkpoint/tests:** none — no code yet.
- **Next:** T1, test-first.

### 2026-08-06 — implementation

- **Phase:** implementation
- **Did:** T1–T6. `validate-artifacts` resolves `validates:` through the shared
  `resolve_produces` and fails closed when content checks resolve no artifact; the six
  review nodes gate `execution-log.md`; the bundled template gained `## Capability docs`;
  P5a/P5b/P5c landed; a new `test_graph_review_chain_integration.py` drives all six
  shipped nodes; decision-063 and the capability doc written.
- **Checkpoint/tests:** `pytest -q` → 1380 passed, 1 skipped. `ruff`, `pyright` clean.
- **Next:** T7 — execute the testing plan, commit evidence.

### 2026-08-06 — verification

- **Phase:** verification
- **Did:** T7. Ran every activity, committed evidence under `evidence/`. Confirmed P5a
  fails against the pre-fix graph naming all six nodes, and P5c fails against the pre-fix
  template naming `Capability docs` — the checks check something. Ran the-loop's own gate
  against this work item (`the-loop check issue-167 --recompute --fail-on block`, exit 0).
- **Checkpoint/tests:** `testing-plan.md` § Verification results.
- **Next:** self-review, then the PR briefing.

## Review cycles

> Outcome is one of: new findings · zero (converged) · escalated · **unavailable** (the
> configured critic could not run — it does NOT count toward `reviews.criticReviewCount`).

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | the-loop (agent) | **new findings** — (a) P3 read a node's `sections:` without asking which file they were meant for, so a node carrying both `produces:` and `validates:` would have demanded the log's sections of its own template; `_required_sections` now ignores entries that name a `validates:` target. (b) The `optional:` early return judged entry on *all* slots, so an optional node validating the shared log would have been treated as entered — the log exists for every work item; it is now judged on what the node authored. | this PR |
| 2 | self | the-loop (agent) | **new findings** — the ticket's reproduction script does not go quiet after the fix: it tests for `sections:` without `produces:`, a question that predates the `validates:` vocabulary. Recorded as it happened in `evidence/reproduction.md`, with the corrected structural check and the behavioural check beside it, rather than quietly swapping the activity. | [`evidence/reproduction.md`](evidence/reproduction.md) |
| 3 | self | the-loop (agent) | **new finding, accepted not fixed** — a previously-completed work item re-checked with `--recompute` now blocks at `capability-docs`: issue-161, issue-163 and issue-165 all do, because the template never offered the section and their logs never carried it. That is the gate being honest about a missing record, and backfilling the section into merged logs would be fabricating one. CI is unaffected (`the-loop-gate.yml` gates only work items the PR touches). Flagged to the reviewer instead. | this PR |
| 4 | self | the-loop (agent) | zero (converged) | this PR |
| 5 | critic | — | **unavailable** — `reviews.critics: []`; no critic harness is configured in this repository, so no critic round could run. Does not count toward `criticReviewCount`; the human PR review is the backstop. | [`.the-loop/harness-config.yaml`](../../../.the-loop/harness-config.yaml) |

## Security review (gate)

> Required before ready-to-ship (`security.review.required`). See `reference/security.md`.

- **Mechanism:** the-loop checklist, cross-checked against `design.md` § Security design
  (`security.review.mechanism: auto`).
- **Outcome:** **pass.** The change adds no external input, no network reach and no new
  privilege. `validates:` is read from the **shipped** graph, which a repository cannot
  define or override (`_warn_on_repo_graph`), so a work item cannot point a gate at a path
  of its choosing; every target resolves through `resolve_produces` onto the work item's
  own spec directory, and the graph declares bare filenames. Every new branch **blocks** —
  `skip` is returned in strictly fewer situations after this change than before. Findings
  carry the-loop's own vocabulary plus repo-relative paths (R3.6), unchanged. The one
  accepted limit is written down rather than implied: the section check is structural, so
  placeholder text passes it — the gate proves the record exists, and the reviewer judges
  whether the review was any good.
- **Human sign-off:** n/a — risk tier 3, below `security.review.humanSignOffMinTier: 4`.

## Final validation evidence

Every acceptance criterion is proved by a committed artifact under
[`evidence/`](evidence/); the per-activity record is in
[`testing-plan.md`](testing-plan.md) § Verification results.

- **The gates fire** (R1, R2, R3) — all six review nodes now `block` where they used to
  `skip`, driven over the *shipped* graph:
  [`evidence/reproduction.md`](evidence/reproduction.md). 12 new hook unit tests and 24
  integration assertions: [`evidence/tests.md`](evidence/tests.md).
- **The assertions assert something** (R4) — P5a fails naming all six nodes against the
  pre-fix graph; P5c fails naming `Capability docs` against the pre-fix template:
  [`evidence/tests.md`](evidence/tests.md).
- **The template can clear its own gates** (R3.3) — the bundled execution log, unedited,
  passes all six nodes (`test_the_bundled_template_can_clear_every_gate_in_the_chain`).
- **Nothing else moved** — 1380 passed, 1 skipped (pre-existing, unrelated); `ruff`,
  `ruff format --check`, `pyright` and `markdownlint` clean:
  [`evidence/tests.md`](evidence/tests.md),
  [`evidence/lint-and-types.md`](evidence/lint-and-types.md).
- **the-loop's own gate passes on this work item** — `the-loop check issue-167
  --recompute --fail-on block` exits 0 (parked at `requirements-approval`, which is the
  human gate this PR *is*).

## Capability docs

> Which living capability docs this work item changed, and the history row that traces the
> behaviour back to it. Updated **in the same PR** as the change — a ready-to-ship gate
> item (`workflow.capabilitiesDir`).

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`docs/capabilities/process-graph.md`](../../capabilities/process-graph.md) | new section **What a node `validates`**: the parameter, the shared resolver, the absent-target block, the fail-closed rule with its not-retriable block, P5, and the explicit statement of what a structural section check does and does not prove | issue-167 · [decision-063](../../decisions/decision-063.md) |

No other capability doc changed: the fix is internal to the process graph's own gating,
and `spec-workflow.md` / `testing-and-contracts.md` describe artifacts whose shape is
untouched. `skills/the-loop/reference/workflow.md` gained one clause pointing the
capability-docs fold-in step at the log section that now gates it — a skill edit, not a
capability doc.
