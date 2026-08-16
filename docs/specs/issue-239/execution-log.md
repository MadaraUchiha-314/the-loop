---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#239"
phase: requirements-definition   # not-started | brainstorming | requirements-definition | design | test-planning | tasks-breakdown | implementation | verification | needs-review | complete
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

# Execution Log: Add streaming support from the-loop's service to control plane

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
| phase-selection | 2026-08-16 | @MadaraUchiha-314 | `brainstorming`, `requirements-approval` and `critic-review` declared skipped; `design-critic-review` not selected. Outer loop iterates **on a pull request**. |
| requirements-definition | 2026-08-16 | n/a — `requirements-approval` skipped | 6 requirements. The transport choice (SSE vs WebSocket) is deferred to design *with its constraints fixed here*, CORS parity among them. |
| design |  |  |  |
| test-planning |  |  |  |
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
| [#244](https://github.com/MadaraUchiha-314/the-loop/pull/244) | The whole work item — the spec chain (this item iterates its outer loop on a PR) and the implementation. | open |

## Progress entries

### 2026-08-16 16:30 UTC — the graph had to be entered by hand again

- **Phase:** phase-selection
- **Did:** found the work item parked at `phase-selection` with its checklist never posted —
  the same spawn-time gap issue-238 hit and recorded (`graphlink._guarded` refuses to enter
  the graph until `docs/specs/<id>/` exists, and `graph run` → `advance` evaluates the
  *current* node's exit chain rather than running an entry chain). Scaffolded
  `docs/specs/issue-239/execution-log.md`, then entered the node by calling
  `Runtime.start("issue-239", ref=…)` through `core.graphs._runtime` — the same code path
  `graphlink.on_spawn` uses. The entry chain ran: `loop:phase-selection` applied and the
  phase-selection checklist posted
  ([comment](https://github.com/MadaraUchiha-314/the-loop/issues/239#issuecomment-5308444073)).
- **Checkpoint/tests:** `the-loop graph status issue-239` → `at phase-selection`, waiting.
- **Next:** wait for an authorized user's `the-loop execute` to freeze the phase selection
  and the outer-loop surface, then derive `requirements.md`.
- **Blockers:** the phase-selection gate — a human act the session never answers itself.

### 2026-08-16 16:36 UTC — phases frozen; requirements drafted

- **Phase:** requirements-definition
- **Did:** @MadaraUchiha-314 replied `the-loop execute` with `brainstorming`,
  `requirements-approval` and `critic-review` unticked and
  `outer-loop-on-pull-request` ticked
  ([comment](https://github.com/MadaraUchiha-314/the-loop/issues/239#issuecomment-5308477504)).
  Read the refresh path end to end before writing anything — `useControlPlane`'s two
  rounds, `HttpApi`, the `/api/v1` router, `eventlog`'s JSONL contract and `EVENT_TYPES`,
  the Settings page, and the detail page's trace/chat-bar layout. Wrote
  `requirements.md`: 6 requirements, the load-bearing one being that a stream which only
  replays `/api/v1/events` does **not** refresh the board, because loop position comes
  from round two (`graph/check` over `graph-state.json`) and is not in the event log's
  shape.
- **Checkpoint/tests:** `make lint` → ruff clean, markdownlint 691 files, 0 errors.
- **Next:** derive `design.md` — settle SSE vs WebSocket against the constraints
  requirements fixed, then the testing plan; both land at the `design-approval` gate.
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

### 2026-08-16 — entry phase-selection

- **Node:** phase-selection
- **Boundary:** entry

### 2026-08-16 — entry requirements-definition

- **Node:** requirements-definition
- **Boundary:** entry
