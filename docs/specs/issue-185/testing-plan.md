---
type: testing-plan
phase: test-planning
workItem: issue-185
status: approved              # reviewed together with design.md — one gate approves both
approvedBy: []
collaborators: [engineer, approver]
riskTier: 4
overrides: {}
---

# Testing plan: the contribution loop

> Derived from [design.md](design.md) and reviewed with it (decision-060 D2).
> Authored at `test-planning`, completed at `verification`.

## Test matrix

| Type | In scope? | What it proves |
|---|---|---|
| Unit | yes | graph compiles/routes; goal parser accepts, refuses, fails closed; `contribute` keyword parses and arms; `GraphState.loop` round-trips; `build_runtime(loop=…)` loads the contribution graph; loop resolution is state-first |
| Integration | yes | a work item walks goal-definition → phase-selection with a stubbed GitHub integration: unauthorized goal ignored, authorized goal frozen + confirmed, checklist lists this graph's rows |
| Contract | n/a | no REST/GraphQL surface changes (`core/graphs.py` verbs keep their signatures) |
| E2E / UI / visual / snapshot | n/a | CLI + markdown only; no product UI |
| Performance | n/a | one extra JSON read per outer-loop build; no hot path |
| Security / abuse-case | yes | unit: self-authored goal dropped; unauthorized author dropped; unknown `loop` in state falls back to the default; both-keywords comment refused (existing test extended by the new vocabulary) |
| Accessibility | n/a | no UI |
| Migration | yes (unit) | a pre-issue-185 `graph-state.json` (no `loop` key) loads and resolves to the shipped default |
| Uninitialized repo (R6, PR #187 review) | yes | `build_runtime` on a checkout with no `.the-loop/` runs on defaults and records `repoInitialized: false`; the walk runs in a git repo that never adopted the-loop with the spec tree excluded (`check-ignore` proves it, `status --porcelain` stays empty); an adopted repo is left unexcluded; `publish-artifact` posts the plan only when unadopted, skips when adopted or when the plan was declared away |
| Manual | no | everything above is automatable in pytest |

## Verification environment

A single checkout of this repository; `uv run pytest` from `cli/`, plus `ruff`,
`pyright` and `markdownlint` — the configured tooling, nothing bespoke. No network:
GitHub integrations are stubbed at the `integrations.resolve` seam the existing
selection/feedback tests already patch.

## Evidence plan

`evidence/tests.md` — the red→green record for the new suite and the full-suite run,
plus lint/typecheck output, redacted of nothing because nothing sensitive is emitted.

## Verification results

Executed at the `verification` node — see [evidence/tests.md](evidence/tests.md).

- [x] Unit: `cli/tests/test_graph_contribution.py` — 40 tests covering the matrix rows
  above (graph shape, goal gate, keyword, arming, loop resolution, state migration,
  abuse cases, the uninitialized repository) — all passing.
- [x] Integration: goal-definition → phase-selection walk with stubbed integration
  (same file, `TestContributionWalk`, Gherkin-docstringed) — passing.
- [x] Security/abuse: unauthorized + self-authored goal ignored; unknown loop name
  falls back to default (state, bootstrap and GraphLink seams each) — passing.
- [x] Migration: state without `loop` resolves to the shipped default — passing.
- [x] Uninitialized repo (R6): defaults hold with no `.the-loop/`; the walk runs in a
  never-adopted git repo with the spec tree structurally excluded (Gherkin-docstringed
  walk, `git check-ignore` + clean `status --porcelain`); adopted repos untouched;
  `publish-artifact` posts only where the thread is the surface — passing.
- [x] Full suite: `uv run pytest` — 1565 passed, 1 skipped (the skip pre-exists this
  work item).
- [x] `ruff check` clean; `pyright` clean (0 errors, 0 warnings); `markdownlint`
  clean on all changed/added markdown files.
