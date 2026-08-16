---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#239"
phase: implementation            # not-started | brainstorming | requirements-definition | design | test-planning | tasks-breakdown | implementation | verification | needs-review | complete
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
| design | 2026-08-16 | @MadaraUchiha-314 (PR #244) | SSE over WebSocket, decided on CORS parity. Two UI prototypes under `design/`. Risk tier 4 — the CLI config schema changes, so the security review needs a named human sign-off. |
| test-planning | 2026-08-16 | @MadaraUchiha-314 (PR #244) | 13 rows, 10 in scope. R1.6's CORS parity is deliberately *not* automated — a test client cannot prove it; T12 does it from a browser. |
| tasks-breakdown | 2026-08-16 | n/a — the plan's human read is `human-approval` | 16 tasks, six of them startable at once: the service chain and the UI chain share no file. |
| implementation | 2026-08-16 |  | 16 tasks; TDD throughout. |
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

### 2026-08-16 16:52 UTC — design and testing plan locked; at the first human gate

- **Phase:** design-approval
- **Did:** wrote `design.md`, two self-contained UI prototypes under `design/`, and
  `testing-plan.md`; locked all three and advanced the graph twice. The design settles the
  ticket's open question — **SSE, not WebSocket** — on the ground that a WebSocket
  handshake is exempt from CORS, so choosing it would silently drop a boundary the REST
  surface already has. Two further findings came out of writing it: the stream must never
  carry `api.request` (the control plane's own refresh would feed itself forever), and one
  invalidation class would make streaming *more* expensive than the 15s poll it replaces.
- **Checkpoint/tests:** `make lint` → 0 errors over 693 files. `the-loop graph complete`
  passed `design` (validate-artifacts + enforces-boundaries-from + lint) and
  `test-planning`.
- **Next:** wait for @MadaraUchiha-314 at `design-approval`, which reads `design.md` and
  `testing-plan.md` together. Then `tasks-breakdown`.
- **Blockers:** the `design-approval` gate.
- **Observed, not fixed:** `request-review` posted its gate notice on the **ticket**, not
  on PR #244, although this work item's frozen surface is `pull-request`. The artifacts and
  their review belong on the PR, so the briefing was posted there by hand. Out of scope
  here; worth its own ticket.

### 2026-08-16 17:20 UTC — design approved; task DAG written

- **Phase:** tasks-breakdown
- **Did:** @MadaraUchiha-314 approved at `design-approval` with a bare `approved`
  ([comment](https://github.com/MadaraUchiha-314/the-loop/pull/244#issuecomment-5308654627)),
  so all four design open questions stand as written — SSE, the transcript in scope,
  `stream` as the default mode, and Requirement 6 staying in this item. Wrote `tasks.md`:
  16 tasks in two chains that share no file, plus Requirement 6 standing alone, meeting
  only at the documentation task.
- **Checkpoint/tests:** `make lint` → 0 errors over 694 files, after the detour below.
- **Next:** implementation. Entering it crosses the phase boundary, so the context is
  cleared and the work re-enters from the locked artifacts on disk
  (`contextManagement.phaseBoundary: clear`). Start at tasks 1, 2, 8, 9, 10 and 15 — the
  six roots.
- **Blockers:** none.
- **Detour, ticketed not fixed:** `record-feedback` wrote the approval as
  `**@handle**` alone on a line, which markdownlint's MD036 rejects — so the gate's own
  hook left `design.md` and `testing-plan.md` failing this repo's lint. Reflowed both
  blocks by hand to `**@handle** — approved` (attribution and body preserved verbatim) and
  filed [#247](https://github.com/MadaraUchiha-314/the-loop/issues/247). Not fixed inside
  this PR: it is an unrelated harness change, and every change is a work item with a
  ticket.

### 2026-08-16 17:35 UTC — task 1 done: `service.stream` config

- **Phase:** implementation
- **Did:** `service.stream` (`enabled`, `maxSubscribers`, `keepAliveSeconds`) in both
  copies of `cli-config.schema.json` — they are byte-compared by
  `test_config_schema_parity.py`, so `cp` is the only correct way to move one — plus
  `stream_config()` in `api/config.py` and the three leaves documented in
  `docs/config/cli/service-options.md` (`test_docs_parity.py` P4 gates that).
  The cap **clamps up to 1** rather than raising: a 0 would refuse every connection and an
  "unlimited" fallback would hand abuse case 1 a configuration switch.
- **Checkpoint/tests:** red → `ImportError: cannot import name 'DEFAULT_STREAM_MAX_SUBSCRIBERS'`;
  green → 9 passed in `test_api_stream.py`, 37 passed across the parity tests.
- **Next:** task 2 — the log tailer and the cursor, in a new `cli/the_loop/api/stream.py`.
- **Blockers:** none.
- **Noted:** four tests fail on `origin/main` unchanged by this work —
  `test_core_repo.py::test_critics_lists_configured_entries_without_argv`,
  `test_critics.py::test_list_reports_availability`,
  `test_harness_gate.py::…does_not_escape_the_temp_dir`,
  `test_poll_daemon_integration.py::test_start_detaches_a_poller…`. Confirmed pre-existing
  by running them on a stashed tree. Not this work item's to fix; recorded so the
  verification evidence is not read as a regression.

### 2026-08-16 18:05 UTC — tasks 2-7 done: the service serves the stream

- **Phase:** implementation
- **Did:** `cli/the_loop/api/stream.py` (tailer, cursor, broker, transcript watch, the SSE
  generator), the `GET /api/v1/stream` route, four `EVENT_TYPES`, and the endpoint in the
  OpenAPI contract. `core.sessions.get_transcript` was split so the path derivation —
  and every fail-closed refusal issue-209 wrote — is reused by the watch rather than
  copied into it.
- **Checkpoint/tests:** red on every task before green. `test_api_stream.py` 31 passed,
  `test_stream_integration.py` 14 passed (16s), full Python suite 2148 passed.
  `make lint` clean, `make format` applied.
- **Next:** the control-plane chain — tasks 8, 9, 10 are three independent roots.
- **Blockers:** none.
- **Three findings worth the reviewer's time:**
  1. **The testing plan was wrong about T3 and is replanned.** Starlette's `TestClient`
     collects the whole response body before returning, so against an endless
     `text/event-stream` it never returns — the first draft of the integration file hung
     for five minutes. The suite now boots real uvicorn on an ephemeral port. That is a
     better test, not a workaround: headers-before-body, one-frame-at-a-time and
     refuse-while-held are all invisible to a buffering client.
  2. **Two of those tests were briefly vacuous.** `eventlog.emit` is a module-level no-op
     until `configure` is called, and only `serve.main` calls it — so the `api.request`
     exclusion test was asserting against an empty log. The fixture now configures the
     log as `serve.main` does, and the test asserts the records were really written
     before asserting they were excluded.
  3. **`Request.is_disconnected` was removed from the stream loop.** It reads the same
     ASGI `receive` channel Starlette's own `listen_for_disconnect` consumes for a
     `StreamingResponse`. It was not the cause of the symptom I first blamed it for (that
     was a test abandoning `iter_text()` mid-iteration, which closes the connection), but
     two consumers of one channel is a race worth not having.
- **Known pre-existing failures, ticketed not fixed:** five tests fail on this tree.
  Four fail identically on `origin/main`
  (`test_core_repo`, `test_critics`, `test_harness_gate`, `test_poll_daemon_integration`).
  The fifth, `test_control_integration::test_a_labelled_work_item_does_not_spawn_until_it_is_started`,
  is **load-flaky**: it waits on the spawn and asserts on the registration. Isolated it
  passed 15/15; after a file that does nothing but burn 16 seconds of wall-clock — no
  the-loop code involved — it failed 1/6. Filed as
  [#251](https://github.com/MadaraUchiha-314/the-loop/issues/251).

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

### 2026-08-16 — entry design

- **Node:** design
- **Boundary:** entry

### 2026-08-16 — entry test-planning

- **Node:** test-planning
- **Boundary:** entry

### 2026-08-16 — entry tasks-breakdown

- **Node:** tasks-breakdown
- **Boundary:** entry

### 2026-08-16 — entry implementation

- **Node:** implementation
- **Boundary:** entry
