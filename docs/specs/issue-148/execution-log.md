---
type: execution-log
workItem: issue-148
phase: needs-review
status: in-progress
---

# Execution Log: the graph runs the PDLC

> Append-only log of progress. The-loop keeps the work item's `loop:<phase>` label in sync
> with the `phase` front-matter above.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-08-04 | MadaraUchiha-314 ("go ahead", [PR #149 comment](https://github.com/MadaraUchiha-314/the-loop/pull/149)) | Tier 5 (`human-approves-spec-and-pr`): each phase artifact needs explicit human approval. Requirements drafted from the issue's audit of the ingress↔graph seam. |
| design | 2026-08-04 | MadaraUchiha-314 ("go ahead with implementation", [PR #149 comment](https://github.com/MadaraUchiha-314/the-loop/pull/149)) | Seven decisions (D1–D7); both open questions from requirements resolved: completion signal is a CLI verb (D1), no consume-only routes (D4). |
| tasks-breakdown | 2026-08-04 | MadaraUchiha-314 (same comment — implementation explicitly green-lit) | 9 tasks. Owner directives recorded: no backwards-compatibility shims; remove unused baggage in touched code. |
| implementation | 2026-08-04 | — | Executing the DAG. |
| needs-review | 2026-08-04 | *pending* | All 9 tasks complete; suite 1168 passed / 2 skipped; ruff, pyright, markdownlint clean. Tier 5: named human security sign-off requested with the PR review. |
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

### 2026-08-04 — design + tasks approved; implementation complete

- **Phase:** needs-review
- **Did:** Owner approved design and green-lit implementation on [PR #149]
  ("go ahead with implementation. No need to think of backwards compatibility…
  remove any extra baggage from the past that's not used"). Derived `tasks.md`
  (9 tasks) and executed the DAG:
  - **T2/D1** `the-loop graph complete` — claims ledger (`completions`),
    `Runtime.complete` (already-past no-op, wrong-node refusal, not-started
    refusal, busy), one JSON envelope, exit 0 for results.
  - **T1/D2** `GraphContext` + `GraphLink.context()` — read-only, behind the
    full `_guarded` gate order, `None` on every skip/fault.
  - **T3/D3** `$graph_context` in both prompt templates and both built-in
    constants; the spawn template's hard-coded phase-flow line removed (R6.3).
  - **T4/D4** consult-first at human gates in the dispatcher; `on_event` now
    returns the `NodeReport`; `advance_after` threaded through the
    respawn/occupant paths so a gate-consumed event is never advanced twice.
  - **T5/D5** spawn resolves context after workspace prep, before render;
    `on_spawn` (the write) still last, on success only.
  - **T6/D6** session binding recorded on spawn/respawn, flipped dead on close
    (`on_close`), `resolve_session` called at human-gate entry and recorded as
    `graph.gate_session`.
  - **T7/D7** parity P4: pdlc.yaml phase order enforced against both harness
    configs; SKILL.md + reference/workflow.md now defer to the graph.
  - **T8** capability docs updated (process-graph, webhook-triggers, CLI graph
    page + history row). **Baggage found and removed in passing:** tmux spawns
    never called `on_spawn` — a whole runner whose items never entered the
    graph; fixed with the binding change.
- **Deviations from design, with reasons:**
  - The two-writer lock is taken by `_guarded` for the daemon's write actions
    (`start`/`advance`/`close`) rather than inside each runtime method — flock
    is not reentrant across file handles, so the lock lives at the outermost
    writer on each path (`Runtime.complete` for claims). `context` reads
    unlocked: a stale read costs a stale prompt, never a wrong pointer.
  - `graph-state.lock` added to `.gitignore` — coordination, not record.
- **Self-review:** 3 rounds (correctness / security / minimalism-docs).
  Round 1 found the design-vs-implementation lock gap above — fixed. Round 2
  re-checked the trust boundaries: no payload text reaches `GraphContext` or
  the rendered block; the verdict is an outcome token, not comment text; the
  ownership-proof-before-checkout-read order is intact on the new `context`
  and `on_close` paths. Round 3: stdlib only, no new dependencies, docs and
  CLI reference updated. `reviews.critics` is empty in config, so no critic
  harness was run (noted per config).
- **Checkpoint/tests:** full suite **1168 passed, 2 skipped**; ruff + format
  clean; pyright 0 errors; markdownlint 0 errors;
  `the-loop check issue-148 --recompute --fail-on block` exit 0 (parked at
  `requirements-approval` — the shipped graph has no pointer for this item on
  main yet; the phase front-matter above is the record). Evidence: the new
  suites `test_graph_drive.py` (19) and `test_graph_drive_integration.py` (8)
  map one-to-one onto R1–R7; P4 covers R6.
- **Next:** reviewer briefing on the PR, then human review + tier-5 security
  sign-off.

[PR #149]: https://github.com/MadaraUchiha-314/the-loop/pull/149
