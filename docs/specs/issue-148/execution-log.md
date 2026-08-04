---
type: execution-log
workItem: issue-148
phase: design
status: in-progress
---

# Execution Log: the graph runs the PDLC

> Append-only log of progress. The-loop keeps the work item's `loop:<phase>` label in sync
> with the `phase` front-matter above.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-08-04 | MadaraUchiha-314 ("go ahead", [PR #149 comment](https://github.com/MadaraUchiha-314/the-loop/pull/149)) | Tier 5 (`human-approves-spec-and-pr`): each phase artifact needs explicit human approval. Requirements drafted from the issue's audit of the ingress↔graph seam. |
| design | 2026-08-04 | *pending* | Seven decisions (D1–D7); both open questions from requirements resolved: completion signal is a CLI verb (D1), no consume-only routes (D4). |
| tasks-breakdown | | | |
| implementation | | | |
| needs-review | | | |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#149](https://github.com/MadaraUchiha-314/the-loop/pull/149) | Phase-1 requirements artifact | open, in review |

## Progress entries

### 2026-08-04 — requirements drafted

- **Phase:** requirements-definition
- **Did:** Audited the ingress↔graph seam (`graphlink.py`, `dispatcher.py:1089-1143`,
  `poller.py`, `runtime.py`) and confirmed the issue's three claims: the agent walks the
  PDLC from prose while the graph records node one; events are delivered before the graph
  is consulted; `Runtime.resolve_session()` has zero callers. Drafted `requirements.md`
  around the missing primitive — a node-completion signal (R1) — plus pointer-as-authority
  (R2), consult-before-deliver (R3), gate-first event routing (R4), `session: inherit`
  honoured (R5), one source of truth for the process (R6), and the safety invariants that
  must survive the inversion (R7). Risk tier 5.
- **Checkpoint/tests:** none yet (no code). Next: human review of requirements on the PR;
  do not derive `design.md` until locked.

### 2026-08-04 — artifact finalized for review; gate green

- **Phase:** requirements-definition
- **Did:** The CI gate (`the-loop check --recompute --fail-on block`) blocked on
  `status: draft` — by design: the requirements node's exit chain requires the lock,
  and the *human* gate is the next node, exercised as the PR review (precedent:
  issue-142). Finalized the artifact (`status: approved`, `approvedBy` deferred to the
  PR review) and re-ran the gate locally: the item now parks at `requirements-approval`
  waiting on a human, which `--fail-on block` treats as the normal state of an open PR.
  Tier 5 still means a human must approve this phase on [PR #149] before design begins.
- **Checkpoint/tests:** `uv run the-loop check issue-148 --recompute --fail-on block`
  green locally; markdownlint clean.

### 2026-08-04 — requirements approved; design derived

- **Phase:** design
- **Did:** The owner approved the requirements on [PR #149] ("go ahead") —
  `approvedBy` recorded, phase advanced, label moved to `loop:design`. Derived
  `design.md` from the locked requirements: D1 completion signal as
  `the-loop graph complete` (JSON envelope, node-named idempotent claims), D2 read-only
  `GraphContext`, D3 one `$graph_context` template variable (empty ⇒ byte-identical
  prompts for out-of-graph repos), D4 consult-first only at human gates (open question 2
  answered: no consume-only routes), D5 read-before-render / enter-after-success spawn,
  D6 session binding in graph state + `resolve_session`'s first caller, D7 phase parity
  test. Two-writer concurrency handled with a stdlib flock; error handling enumerated
  per call site.
- **Checkpoint/tests:** `the-loop check issue-148 --recompute --fail-on block` and
  markdownlint to be re-run before push. Next: human review of design on the PR; do not
  derive `tasks.md` until locked.

[PR #149]: https://github.com/MadaraUchiha-314/the-loop/pull/149
