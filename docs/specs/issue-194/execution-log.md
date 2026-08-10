---
type: execution-log
workItem: issue-194
phase: needs-review
status: in-progress
---

# Execution Log: graph commands post nothing when `--ref` is omitted

> Append-only log for [#194](https://github.com/MadaraUchiha-314/the-loop/issues/194).

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-08-10 | pending — PR gate | Risk tier 3: graph runtime + integrations, no schema and no new config key |
| design | 2026-08-10 | pending — PR gate | One new pure module, one changed line in `work_item()`, one new reader of existing results |
| test-planning | 2026-08-10 | pending — PR gate | 13-row matrix; every test runs offline against a fake integration |
| tasks-breakdown | 2026-08-10 | pending — PR gate | 10 tasks; T1–T6 code, T7–T8 tests, T9 docs, T10 verification |
| implementation | 2026-08-10 | — | T1–T9 complete, plus two unplanned changes recorded in `tasks.md` |
| verification | 2026-08-10 | — | Every applicable row executed; see `testing-plan.md` § Verification results |
| needs-review | 2026-08-10 | pending | Self-review done (three rounds, one finding fixed); the human gate is the PR |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#196](https://github.com/MadaraUchiha-314/the-loop/pull/196) (this repository) | Tasks 1–10 — the whole work item | open |

## Progress entries

### 2026-08-10 — spec chain locked

- **Phase:** requirements-definition → tasks-breakdown
- **Did:** Read the ticket, then the code it names and the code around it:
  `commands/graph_cmd.py`, `graph/runtime.py`, `graph/chain.py`, `graph/contract.py`,
  `graph/hooks/selection.py`, `graph/hooks/sideeffects.py`,
  `graph/integrations/{base,github}.py`, `graph/bootstrap.py`, `core/graphs.py`,
  `harness_config.py`, `graphlink.py` and `sessions/registry.py`. Confirmed both halves of
  the root cause by reading, and confirmed the inverse translation
  (`graphlink.spec_id_for`) already exists — which is what makes derivation a reuse rather
  than an invention. Wrote and locked `bugfix.md` → `design.md` → `testing-plan.md` →
  `tasks.md`.
- **Checkpoint/tests:** baseline `make test` green — 1686 passed, 1 skipped.
- **Next:** implement T1–T6, then the tests.
- **Blockers:** none.

### 2026-08-10 — implementation

- **Phase:** implementation
- **Did:** T1–T9. New `the_loop.graph.refs` (`derive_ref` + the `ref_for` primitive it is
  built on), the three-tier resolution in `Runtime.work_item()`, `_degradations()` read by
  `advance` (both chains), `start` and `cleanup` with the new `graph.hook_degraded` event,
  `warnings` on the force and skip results and printed by `graph_cmd`, an actionable
  `_split_ref` message, and the documentation set.
- **Checkpoint/tests:** `make check` green.
- **Next:** self-review, then verification.
- **Blockers:** none.

### 2026-08-10 — self-review and verification

- **Phase:** implementation → verification → needs-review
- **Did:** Three self-review rounds over the diff. Round 1 found the finding that mattered
  and it is now R1.5: an **inner** loop (`--pr`) would have derived the *work item's* ref
  and posted a pull request's review comments to the ticket — a worse outcome than the
  silence being fixed. Fixed by having `build_runtime` compute the pull request's own ref
  (it is the only place that knows which pull request the runtime walks) and by making the
  inner branch refuse to fall through to the work item's, with two scenarios pinning both
  halves. Round 2 checked the purity of `the-loop check` (unaffected — `derive_ref` does no
  I/O and no exit hook makes an outbound call without an event) and the block/wait paths
  (the warnings do not reach `note_block`, so repeat-finding escalation is unchanged).
  Round 3 found nothing new, which is the stop condition. Then executed the testing plan
  and committed the evidence.
- **Checkpoint/tests:** `make check` green — 1731 passed, 1 skipped, 0 lint/format/pyright
  findings. Red→green confirmed: 8 of the 12 integration scenarios fail against the 9.5.0
  source.
- **Next:** the PR briefing, then human review.
- **Blockers:** none.

## Documentation

Three user-facing documents were wrong after this change, and all three ship with it:

- **`docs/cli/commands/graph.md`** — a new *Resolving the work-item ref* section (the three
  tiers, worked example of the warning line) plus the `--ref` row of all five verb tables,
  which said the default was `""` and now say it is derived. The page previously implied a
  ref had to be supplied for hooks to work, without saying what happened when it was not.
- **`docs/capabilities/process-graph.md`** — two new subsections under *Two call planes*:
  which ticket a control-plane call reaches, and the degradation-reporting contract.
- **`docs/capabilities/cli.md`** — the `graph` bullet now states the optional `--ref` and
  the warning-line/exit-code contract.

`README.md`, the skill and its `reference/` docs needed **no** change, and the reason is
the shape of the fix rather than an oversight: nothing about the operating model, the
phases, the artifacts or the commands moved. The skill tells an agent to run
`the-loop graph complete <id>`; that instruction was correct before and is correct now —
it simply works.

## Capability docs

- **[`process-graph`](../../capabilities/process-graph.md)** — the capability this change
  belongs to. New behaviour above, plus a history row.
- **[`cli`](../../capabilities/cli.md)** — the surface an operator meets it on. Amended
  bullet, plus a history row.

No other capability doc is affected: no schema, no config key, no state-file shape and no
API contract changed (`/api/v1/graph/skip` returns an open object, so its new `warnings`
key is additive).
