---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#238"
phase: test-planning         # not-started | brainstorming | requirements-definition | design | test-planning | tasks-breakdown | implementation | verification | needs-review | complete
status: in-progress          # in-progress | complete
# repos:                     # OPTIONAL (issue-183). The CONTRIBUTING repositories this
#   - <owner>/<repo>         #   work item raises pull requests in — one inner loop each,
#   - <owner>/<other>        #   state under pr-loops/<owner>__<repo>/pr-<n>/ here in the
                             #   ORIGIN repository (the one the ticket was created in).
                             #   `await-inner-loops` then holds `implementation` until each
                             #   declared repository has a loop AND every started loop has
                             #   finished. Omit for single-repository work: the gate then
                             #   behaves exactly as it did before the key existed.
---

# Execution Log: control-plane UI floods the console with 400s from `/graph/check` when a session's `cwd` checkout is gone

> Append-only log of progress for the user's visibility. Checked in alongside the spec
> at `docs/specs/<id>/execution-log.md`. The-loop keeps the work item's phase label in
> the ticketing system in sync with the `phase` front-matter above, and self-checks
> (runs tests at logical checkpoints) recording the outcome here. The log doubles as
> the **resume anchor for context resets** (`reference/context.md`): every reset (clear
> or compact) is preceded by a checkpoint entry here, and a fresh window re-enters by
> reading the latest entry's **Next:** first.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-16 | @MadaraUchiha-314 | Full process; `brainstorming` declared skipped; `design-critic-review` not selected. Outer loop iterates **on a pull request**. |
| requirements-definition | 2026-08-16 | @MadaraUchiha-314 (PR #241) | `bugfix.md` (a bug, so `bugfix.md` not `requirements.md`). Approved 2026-08-16. |
| design | 2026-08-16 |  | Settled the deferred question **server-side only**; recorded the rejected session-listing alternative. |
| test-planning | 2026-08-16 |  | 12 rows, 5 in scope. Two existing tests are rewritten, not deleted — called out explicitly. |
| tasks-breakdown |  |  |  |
| implementation |  |  |  |
| verification |  |  |  |
| needs-review |  |  |  |
| complete |  |  |  |

## Pull requests

> A work item may be delivered by **several** PRs (a spec PR then an implementation
> PR, a stacked series, a follow-up after review, or **one PR per contributing
> repository** — the multi-repo shape, where the outer loop stays in the repository the
> ticket was created in and each other repository gets its own PR and inner loop) — list
> every one of them here, not just the latest. Name the repository in the PR column when
> it is not this one. Each PR carries the auto-execute
> label so its activity routes back to this work item's session, and the work item
> is complete only once **all** of them are merged or closed (`finish-tasks`).

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#241](https://github.com/MadaraUchiha-314/the-loop/pull/241) | The whole work item — the spec chain (this item iterates its outer loop on a PR) and the fix. | open |

## Progress entries

### 2026-08-16 01:27 UTC — the graph had to be entered by hand

- **Phase:** phase-selection
- **Did:** found the work item parked at `phase-selection` with its checklist never posted.
  The daemon had skipped entering the graph at spawn — `graph.skipped action=start
  reason=no-spec-dir spec_dir=docs/specs` — because `docs/specs/issue-238/` does not exist
  until a session creates it, and `graphlink._guarded` (`cli/the_loop/graphlink.py:711`)
  requires it first. `the-loop graph run` does not rescue that: `run` → `advance`, and
  `advance` evaluates the *current* node's exit chain rather than running an entry chain
  (`cli/the_loop/graph/runtime.py:702-718` documents the distinction), so it parked with
  `currentNode: ""`. No `graph start` CLI verb or API route exists.
- **Checkpoint/tests:** entered the node by calling `Runtime.start()` through
  `core.graphs._runtime` — the same code path `graphlink.on_spawn` uses. The entry chain
  ran and posted the phase-selection checklist.
- **Next:** wait for an authorized user's `the-loop execute`.
- **Blockers:** none after the checklist went up. Two repository labels were missing and
  `set-phase-label` had warned about it — `loop:phase-selection` and `loop:cleanup` created.
  The spawn-time gap itself is a separate defect, not in this work item's scope.

### 2026-08-16 01:42 UTC — phases selected; requirements drafted

- **Phase:** requirements-definition
- **Did:** @MadaraUchiha-314 replied `the-loop execute` with the boxes untouched except
  `brainstorming`, and ticked `outer-loop-on-pull-request`. Read the failing path end to
  end (`ui/src/state/useControlPlane.ts:150-187`, `ui/src/api/client.ts:273-281`,
  `cli/the_loop/core/graphs.py:31`, `cli/the_loop/api/routes.py:206`), reproduced the 400
  against the running service with `curl`, and confirmed `GET /api/v1/sessions` carries no
  signal about whether `cwd` still resolves. Wrote `bugfix.md`.
- **Checkpoint/tests:** reproduction confirmed — `POST /api/v1/graph/check` with the stale
  `devbox#2` worktree path returns `400 {"detail":"repo path is not a directory: …"}`.
- **Next:** open the PR carrying `bugfix.md` and request review of the requirements.
- **Blockers:** none.

### 2026-08-16 02:05 UTC — requirements approved; design and testing plan written

- **Phase:** design → test-planning
- **Did:** @MadaraUchiha-314 approved on PR #241 without answering the deferred
  server-side/client-side question, so `design.md` settles it: **server-side only**.
  `core.graphs.check` returns a `200` "position unknown" report for a `repo` that does not
  resolve; `fetchGraphs` drops that answer exactly as it drops today's rejection, so
  `railFromFrozen` still renders the row. The session-listing alternative is recorded as
  rejected with its three reasons rather than dropped. Then wrote `testing-plan.md`:
  12 rows, 5 in scope, each `n/a` carrying a reason.
- **Checkpoint/tests:** `markdownlint` clean on all three artifacts. Read the two existing
  tests that assert today's `400` — `test_check_malformed_repo_never_reaches_the_graph`
  (`cli/tests/test_core_graphs.py:37`) and `test_graph_check_rejects_a_bad_repo_path`
  (`cli/tests/test_api_routers_integration.py:85`) — and planned their rewrite explicitly,
  with the red run as its own evidence row.
- **Corrected:** R3.3 of `bugfix.md` said the OpenAPI contract "SHALL be regenerated rather
  than hand-edited". False here — issue-161 made the contract **authored**, with a parity
  test asserting the app serves it. Reworded in place, with the correction noted inline.
- **Next:** wait for the `design-approval` gate (one gate, both artifacts).
- **Blockers:** none.

## Verification results

> **Only when this work item declared `test-planning` away** (issue-179). With a
> `testing-plan.md` the `verification` node records its results *there*, against the
> matrix rows it planned, and this section stays as the template left it. Without one,
> this is where the proof lives — and `verification` blocks until it is filled in, because
> skipping the plan removes the document, never the verifying.

| What was verified | Command | Outcome | Evidence |
|-------------------|---------|---------|----------|
|                   |         | pass \| fail | link or `evidence/<file>` |

## Design critic review

> **Only when this work item selected the opt-in `design-critic-review` phase** (issue-188)
> — a different model/harness reading the **locked `design.md`** against the requirements,
> before the testing plan and the task DAG are derived from it. The node blocks until this
> section is filled in; a work item that did not select the phase leaves it as the template
> left it. Rounds follow `reference/reviewing.md` unchanged: attribution prefix, own-comment
> marker, reply-first-then-fix, stop on zero new findings, escalate on a repeated finding.
> A round that could not run is recorded as **`unavailable`** with the cause and does NOT
> count toward `reviews.criticReviewCount`.

| Round | Critic (`<harness>/<model>`) | Outcome | Findings → disposition | Link |
|-------|-----------------------------|---------|------------------------|------|
|       |                             | new findings \| zero (converged) \| escalated \| unavailable | | |

## Review cycles

> Outcome is one of: new findings · zero (converged) · escalated · **unavailable** (the
> configured critic could not run — it does NOT count toward `reviews.criticReviewCount`).

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
|       |                             |          |         |      |

## Security review (gate)

> Required before ready-to-ship (`security.review.required`). See `reference/security.md`.

- **Mechanism:** <security-review skill | the-loop checklist> (`security.review.mechanism`)
- **Outcome:** <pass | findings fixed (link threads) | escalated>
- **Human sign-off:** <n/a (tier below `security.review.humanSignOffMinTier`) | @handle + link>

## Final validation evidence

The evidence presented to the user proving acceptance criteria are met. **Summarised
from `testing-plan.md`'s Verification results** (the `verification` node produced the
raw record — command, outcome, committed evidence per activity); this section maps it
onto the acceptance criteria rather than re-deriving it. Committed evidence files live
under `<specDir>/<id>/evidence/`.

## Capability docs

> Which living capability docs this work item changed, and the history row that traces
> each behaviour back to it. Capability docs are the **organized view of specs** — the
> single source of truth for a capability's *current* behaviour — so they are updated
> **in the same PR** as the change (`workflow.capabilitiesDir`), and this section is what
> the `capability-docs` node gates on. A work item that genuinely changed no capability
> says so here, and why; the section is never deleted to shorten the log.

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
|                |              |             |

## Documentation

> Which **user-facing** documents this work item changed — `README.md`, the documentation
> site under `docs/`, and the operating-model skill with its `reference/` docs. Capability
> docs above are the organized view of specs, written for a reader who already uses the
> project; this section is the surface a reader meets *before* that, and it rots the same
> way, so it is updated **in the same PR** as the change (`reference/workflow.md`,
> ready-to-ship gate). The `capability-docs` node gates this section alongside the one
> above (issue-174).
>
> A work item that genuinely changed no user-facing documentation says so here **with the
> reason** — "internal refactor, no described behaviour changed" is an answer; a blank is
> not. The section is never deleted to shorten the log. A row names a **document**, never a
> token, a credential or an internal hostname: this tree is as public as the repository.

| Document | What changed |
|----------|--------------|
|          |              |

### 2026-08-15 — entry design

- **Node:** design
- **Boundary:** entry

### 2026-08-15 — entry test-planning

- **Node:** test-planning
- **Boundary:** entry
