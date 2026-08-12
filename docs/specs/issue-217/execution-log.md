---
type: execution-log
workItem: issue-217
phase: needs-review
status: in-progress
---

# Execution Log: end-to-end PDLC scenario tests

> Append-only log for issue-217. Ticket:
> [#217](https://github.com/MadaraUchiha-314/the-loop/issues/217).

## How this session ran the loop

One cloud session, one pass, no human at the other end — the same posture as
issue-208/209/211, with the same two consequences a reviewer should hold:

1. **`phase-selection` was not run as a gate.** The session was started by the
   ticket itself; there was nobody to tick the checklist. Phases assumed: the full
   spec chain, verification, self-review. `brainstorming` and the opt-in
   `design-critic-review` were not taken — the ticket already states the shape
   (scenario runner + fixture sets at existing seams), and no second model was
   available.
2. **The chain was authored before the code, but approved by nobody.** The
   artifacts are a proposal to ratify, not a locked chain; `status: draft` on all
   four says so.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-12 | — | Not run as a gate; see above |
| requirements-definition | 2026-08-12 | | [`requirements.md`](requirements.md) — 4 requirements, 4 NFRs, 3 abuse cases. Risk tier **3**: test-only change, but the traces it pins become the reference for how the process may behave |
| design | 2026-08-12 | | [`design.md`](design.md) — a data-driven scenario runner over the real runtime; closed step vocabulary; fakes at transport seams only; four deliberate absences |
| test-planning | 2026-08-12 | | [`testing-plan.md`](testing-plan.md) — 8 rows in scope, 7 `n/a` with reasons |
| tasks-breakdown | 2026-08-12 | | [`tasks.md`](tasks.md) — 7 tasks |
| implementation | 2026-08-12 | | Built. Tasks 1–6 complete |
| verification | 2026-08-12 | | Testing plan executed in full: 15 e2e/meta tests green in 0.5s; whole suite 1886 passed + 1 skipped (+15 over baseline, incl. the self-review addition); lint, format, types, markdown, config validation clean |
| needs-review | 2026-08-12 | | Handed to the PR |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| `claude/github-issue-217-tnm2ek` | the whole work item | open, awaiting human approval |

## Progress entries

### 2026-08-12 — orientation

Read the ticket, the harness config, the skill, and the issue-209 chain for
conventions; mapped the graph runtime and the existing integration-test fakes
before designing (two exploration passes over `cli/the_loop/graph/` and
`cli/tests/`). Baseline suite: 1873 tests collected.

### 2026-08-12 — the shape of the change

Three seam findings shaped the design:

- **Discovery is pinned, and the pin is a sensitive path.** `the-loop
  scenarios` reads `testing.integrationTestGlobs`, which this repo pins to the
  non-recursive `cli/tests/test_*_integration.py`. A test module inside
  `test_pdlc_e2e/` would be invisible to it, and widening the glob means
  editing `.the-loop/harness-config.yaml` — a declared sensitive path this
  work item has no reason to touch. So the test module lives beside the
  fixture directory (`test_pdlc_e2e_integration.py`), which the existing glob
  already matches.
- **The seams were already there.** `the_loop.graph.integrations.resolve` is
  the one patch point every graph test uses (and the source comments say so —
  hooks bind it at call time for exactly this reason); the ask/reply tests
  define the poster/TmuxRunner patch shape; the event log configures to any
  path. No new mocking layer was needed (R3.1), and no production code
  changed (NFR2).
- **`riskTier` does not gate anything in the runtime.** The tier lives in
  front matter and on the `WorkItem`, but no shipped hook reads it — tier
  scaling is declared at `phase-selection` by a human, not computed. The
  trivial-tier scenario therefore asserts the *declared-skip* mechanics
  (provenance, `onlyWhenSkipped` re-targeting), not a tier-driven branch that
  does not exist.

## Documentation

| Doc | Change |
|-----|--------|
| [`docs/capabilities/testing-and-contracts.md`](../../capabilities/testing-and-contracts.md) | Current behaviour: the e2e process-conformance suite (what is real, what is faked, what is asserted); issue-217 history row |
| [`cli/tests/test_pdlc_e2e/README.md`](../../../cli/tests/test_pdlc_e2e/README.md) | New — the fixture-set format, step vocabulary and expectation keys, written so adding a scenario requires reading nothing else (R4.3) |

`README.md`, the docs site and `SKILL.md` are untouched **with reason**: no
command, config key, workflow or user-facing behaviour changed — the
deliverable is an internal test suite, documented where tests are documented
(the capability doc and the suite's own README).

## Capability docs

[`testing-and-contracts.md`](../../capabilities/testing-and-contracts.md) —
updated in this PR (see the table above). No other capability's behaviour
changed; `process-graph.md` is untouched because the suite *tests* the graph's
documented behaviour without changing any of it.

## Verification results

In [`testing-plan.md`](testing-plan.md) § Verification results, with evidence
in [`evidence/verification.md`](evidence/verification.md).

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | the-loop (this session) | new finding — the module-level `Requirement:` in the test file's docstring shifted every scenario's requirement attribution by one row in `the-loop scenarios` (the extractor carries the last-seen `Requirement:` onto the next `Scenario:`). Moved each `Requirement:` above its `Scenario:`; attribution verified in the table output | [`test_pdlc_e2e_integration.py`](../../../cli/tests/test_pdlc_e2e_integration.py) |
| 2 | self | the-loop (this session) | new finding — R1.3's "the execution log mirrors the transitions" was asserted only as section presence, not as the walk's checkpoints. Added the `executionLogEntries` expectation (ordered `log-entry` markers) and re-ordered the happy path so the log exists before the phases that checkpoint into it | [`runner.py`](../../../cli/tests/test_pdlc_e2e/runner.py), [`happy-path/scenario.yaml`](../../../cli/tests/test_pdlc_e2e/scenarios/happy-path/scenario.yaml) |
| 3 | self | the-loop (this session) | new finding — the node-trace and label-trail divergence reporters were never exercised on a failing path, so a bug there would let a regression pass silently. Added a meta-test that forges a phase-skipping event log and asserts both reporters fire naming the divergence. A fourth pass (requirements trace R1–R4 → mechanism → test; docs-altitude sweep for stale "no e2e" claims) found nothing new — stopped per `reviews.stopOnNoNewFindings` | [`test_pdlc_e2e_integration.py`](../../../cli/tests/test_pdlc_e2e_integration.py) |
| 4 | critic | — | **not run.** `reviews.critics` is empty in this repo's harness config and no second harness was available to this session | |
| 5 | security | — | mechanism-level review against the requirements' 3 abuse cases: fixture playback is inert data behind a closed step vocabulary (refusal tested); fakes sit at transport seams while authorization/loop-prevention run production code (positively asserted by the `loop-prevention` scenario); hermeticity is a raising tripwire, not a convention (tested). Test-only change, no new attack surface, no production code touched. Risk tier 3 — no named human sign-off mandated; the PR approval gate stands | [`requirements.md`](requirements.md) § Security considerations |
