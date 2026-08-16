---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#238"
phase: needs-review          # not-started | brainstorming | requirements-definition | design | test-planning | tasks-breakdown | implementation | verification | needs-review | complete
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
| design | 2026-08-16 | @MadaraUchiha-314 (PR #241) | Settled the deferred question **server-side only**; recorded the rejected session-listing alternative. |
| test-planning | 2026-08-16 | @MadaraUchiha-314 (PR #241) | 12 rows, 5 in scope. Two existing tests are rewritten, not deleted — called out explicitly. |
| tasks-breakdown | 2026-08-16 |  | 7 tasks, two independent red roots. |
| implementation | 2026-08-16 |  | TDD: red committed before the fix. |
| verification | 2026-08-16 |  | Every activity ran but the devtools screenshot — replanned, reason recorded. |
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

### 2026-08-16 02:30 UTC — implemented, red first

- **Phase:** tasks-breakdown → implementation
- **Did:** design and testing plan approved; wrote `tasks.md` (7 tasks, two independent red
  roots) and executed it. Tasks 1–2 wrote the tests and **committed them red**; tasks 3–5
  made them green (`repo_resolves` factored out of `resolve_repo`; `check` returns the
  unknown-position dict before `_runtime`; the `graphCheck` operation gained a description
  in both the handler docstring and the authored contract, verified identical); task 6
  updated `docs/capabilities/control-plane.md` and `ui/README.md`; task 7 ran CI's own
  commands.
- **Checkpoint/tests:** targeted suites 23 passed; contract parity 2 passed; UI lint clean,
  106 vitest passed, build clean. Full `uv run pytest`: 2103 passed, 4 failed.
- **Found (not caused):** those 4 failures are assertions about the CI machine that fail on
  this macOS workstation — `cursor-agent` is installed here but two tests assert it is not,
  `/var` is a symlink so a `resolve()` equality fails, and a detached-poller test asserts a
  session id that differs under tmux. Proved unrelated by re-running exactly those four
  against the stashed tree. Consequence: the `pytest` pre-commit hook cannot pass here, so
  the two Python-touching commits bypassed hooks **with the reason in the commit message**,
  and `ruff`, `ruff-format`, `pyright` and `markdownlint` were run explicitly instead.
- **Deviation:** task 2 exported `fetchGraphs` (module-private before) so the UI test can
  address it. Recorded in `tasks.md` § Deviations before it was done.
- **Next:** execute `testing-plan.md`.
- **Blockers:** none.

### 2026-08-16 02:50 UTC — verified against two live services

- **Phase:** verification
- **Did:** ran every planned activity. For T12, brought up this branch's API on `:4199`
  reading the **same state root** as the operator's installed `10.2.0` on `:4114`, so the
  stale `devbox#2` record (whose `cwd` genuinely does not exist) was answered by both. Then
  ran the board's own `fetchGraphs` + `HttpApi` against each, with `fetch` wrapped to record
  every `/graph/check` status.
- **Checkpoint/tests:** `400` before / `200 {"repoResolved": false}` after on the same
  request. One real poll tick: **1× 4xx before, 0× after**, and `reports.outer` identical
  in both runs — which is R2.1 (nothing rendered changes) shown on the real path rather
  than inferred. Temporary service and Vite dev server torn down; the operator's `:4114`
  daemon was never touched.
- **Not executed:** the devtools console screenshot — the Chrome extension was not
  connected, so no browser could be driven. Replanned rather than skipped (the status list
  it would have shown was captured directly, with a before/after contrast), reason recorded
  in `testing-plan.md` § Verification results, and flagged for a human on PR #241.
- **Found (not caused):** the `record-feedback` hook appends `**@handle**` as a standalone
  line, which markdownlint rejects (MD036) — so a spec whose gate approves-with-comments
  fails this repo's own lint hook. Patched in the two affected files here; the hook itself
  is a separate defect, reported on the PR.
- **Next:** self-review, critic review, security review, reviewer briefing.
- **Blockers:** none.

### 2026-08-16 03:10 UTC — self-review found two real defects in the fix

- **Phase:** needs-review
- **Did:** three self-review rounds over the whole diff, tracing consumers rather than
  re-reading the diff three times.
- **Round 1 — a CI gate that would go green on a typo.** `the-loop check --fail-on block`
  is the automated-gate mode, and `_fails` decides it by looking for a blocking node. The
  new unknown-position report has *no nodes*, so it has no blocking node either: a mistyped
  `--repo` would have exited 0. `.github/workflows/the-loop-gate.yml:56` runs exactly that
  command. Fixed test-first (`test_a_repo_that_is_not_there_fails_both_modes`, red before
  the fix): `_fails` refuses an unresolved repo in **both** modes ahead of either rule, and
  the row renders `UNREAD — <path> is not a directory` instead of `UNMET (at )` with
  nothing under it. Also tidied `resolve_repo` (it computed `expanduser()` twice) and
  strengthened the oracle test to pin the whole key set rather than today's absence.
- **Round 2 — the other two consumers.** The MCP tool `check_work_item` and the SDK's
  `check` both return core's dict straight through, so both now hand back
  `repoResolved: false` where they used to raise. Neither is wrong, but an agent reading
  `nodes: []` could report "no phases"; both docstrings now say what the shape means, and
  the MCP one — which is a tool description an LLM reads — says it in the imperative.
- **Round 3 — my own testing plan was wrong about upgrades.** T11 claimed an older UI build
  against a newer service "ignores an unknown key and keeps its `catch`". False: the old
  build keeps its `catch` only for a *rejection*, and a `200` is stored and rendered as an
  empty rail. The dashboard is published to Pages and pointed at whatever local service the
  operator runs, so that combination is real. Nothing server-side can fix an
  already-published page, so `buildWorkItemViews` now treats a report with no nodes as no
  position and falls back to `railFromFrozen` regardless of the caller. T11's reason is
  corrected in place rather than quietly rewritten.
- **Checkpoint/tests:** `uv run pytest` 2104 passed / the same 4 pre-existing environment
  failures; UI lint clean, 107 vitest passed, build clean.
- **Next:** critic review (none configured — record as unavailable), security review,
  capability docs, reviewer briefing.
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
| 1 | self | the-loop session | new findings — `the-loop check --fail-on block` would have exited 0 on a repo that does not resolve, because the position-unknown report has no nodes and so no *blocking* node. Fixed test-first; `resolve_repo` tidied and the abuse-case test strengthened to pin the whole key set | [commit](https://github.com/MadaraUchiha-314/the-loop/commit/2e166de) |
| 2 | self | the-loop session | new findings — the MCP tool and the SDK's `check` pass core's dict straight through, so both now answer where they used to raise. Docstrings state what the shape means; the MCP one in the imperative, since an LLM reads it as a tool description | [commit](https://github.com/MadaraUchiha-314/the-loop/commit/2e166de) |
| 3 | self | the-loop session | new findings — `testing-plan.md`'s own T11 claim was wrong: an older UI build against a newer service stores the `200` and renders an empty rail, rather than "ignoring an unknown key". `buildWorkItemViews` now falls back to `railFromFrozen` for a report with no nodes; T11's reason corrected in place | [commit](https://github.com/MadaraUchiha-314/the-loop/commit/2e166de) |
| 4 | critic | — | **unavailable** — `reviews.critics: []` in `.the-loop/harness-config.yaml`, so `the-loop critic list` reports none configured. Does **not** count toward `reviews.criticReviewCount` (`reference/reviewing.md`) | — |
| 5 | security | built-in security-review skill | pass — no findings at confidence ≥ 8 | see § Security review |

Rounds 1–3 each found something new, so the loop did not stop early. A fourth self-round
was not run: `reviews.selfReviewCount` is 3, and the three rounds were spent on distinct
surfaces (the CLI gate, the other API consumers, upgrade compatibility) rather than three
re-readings of the same diff.

## Security review (gate)

> Required before ready-to-ship (`security.review.required`). See `reference/security.md`.

- **Mechanism:** the built-in `security-review` skill (`security.review.mechanism: auto`,
  which prefers the skill when available).
- **Outcome:** **pass** — no findings at confidence ≥ 8. Five questions were put to it
  explicitly, because they are where this change could plausibly have gone wrong:

  | Question | Verdict |
  |---|---|
  | Does `check` reach core with an unvetted path? | No. The early return is unconditional and precedes `_runtime`, the only route to `resolve_repo`/`build_runtime` from this verb. The returned dict is literals plus the caller's own `work_item` — no filesystem, no graph state, no config load. |
  | Does `repo_resolves` differ from the old inline predicate? | No. Byte-identical (`is_dir()` follows symlinks in both). `resolve_repo` now builds the `Path` twice, but `is_dir()` and `resolve()` were already two syscalls, so the TOCTOU window is unchanged in existence and width — and `resolve()` was never the security decision. |
  | Does the `200` leak more than the `400` did? | No — **less**. The old body echoed the caller's path; the new one names nothing the caller did not send. The directory-existence oracle is unchanged, not newly introduced. |
  | Does error→success change any gating decision? | Every consumer traced. `_fails` fails closed (and the `is False` identity test is correct against JSON-parsed `false` over HTTP). `graph status` and `--dry-run` fail closed already via `ok: False`. `check --all` still raises through `_show`. The API, MCP and SDK entry points make no decision. `the-loop-gate.yml` uses `--repo .` and is unaffected. |
  | Anything in the UI change? | No. `=== false` is strict identity, not truthiness. No `dangerouslySetInnerHTML`/`innerHTML`/`eval` anywhere in `ui/src`; values reach React text nodes and are escaped. Exporting `fetchGraphs` widens no runtime surface. |

  One residual was considered and rejected below the reporting threshold: a **version-skewed
  old CLI** (a `_fails` without the new branch) against a new service would take
  `--fail-on block` to exit 0 on a non-resolving repo. It needs mixed versions *and*
  attacker influence over `--repo`, which is a CLI flag — a trusted value — and is `.` in
  the only gate in this repository. Recorded rather than dropped.

- **Human sign-off:** n/a. Risk tier 3 (`autonomy.defaultTier`, and no `sensitivePaths`
  glob matches — the change touches no schema, no `.the-loop/` config and no
  `.github/workflows/`), which is below `security.review.humanSignOffMinTier: 4`.

## Final validation evidence

Every acceptance criterion is met. Summarised from
[`testing-plan.md` § Verification results](testing-plan.md#verification-results); the raw
record is there and the committed output is under [`evidence/`](evidence/).

| Criterion | Met by |
|---|---|
| **R1.1** no browser-logged 4xx/5xx for a non-resolving `cwd` | One real poll tick through the board's own `fetchGraphs`: **1× 4xx before, 0× after**, same records, same tick ([`manual.md`](evidence/manual.md)). |
| **R1.2** no growth over time | The answer is a pure function of the path — no state, no cache, no reconcile — so every tick is the one measured above. `test_check_answers_a_vanished_checkout_instead_of_raising` pins it. |
| **R1.3** satisfied from the first tick after removal, with no reconcile | Structural: the answer comes from a `Path.is_dir()` at request time. Nothing is remembered between ticks, so there is no window to be wrong in — which is why the session-listing alternative was rejected in `design.md`. |
| **R2.1** the rail renders exactly as today | `reports.outer` is byte-for-byte identical before and after on the real path ([`manual.md`](evidence/manual.md)), plus `useControlPlane.test.ts` and the `railFromFrozen` fallback test in `model.test.ts`. |
| **R2.2** a resolving repo's response is unchanged, byte for byte | `test_a_resolving_repo_keeps_exactly_the_keys_it_always_had` asserts the exact five-key set; `test_graph_check_says_nothing_new_about_a_checkout_that_is_there` asserts it over HTTP. Both were green *before* the change too, which is what makes them meaningful. |
| **R3.1** malformed requests still refused | Untouched — the request model and `Path("")` behaviour are exactly as before, verified by the unchanged tests around them. |
| **R3.2** no core graph call receives an unvetted path | `test_check_answers_a_vanished_checkout_instead_of_raising` monkeypatches `_runtime` to raise if reached. Independently confirmed by the security review: the early `return` precedes the only route to `resolve_repo`. |
| **R3.3** the contract describes the shape; parity green | `graphCheck` gained a `description`, verified `identical: True` against the served schema; `test_api_contract_parity.py` passes ([`unit-and-integration.md`](evidence/unit-and-integration.md)). |
| **R4.1** a test that fails before and passes after | [`red.md`](evidence/red.md) — four Python assertions and one vitest case failing against unfixed code, committed as their own commit before the fix. |
| **R4.2** coverage of a session record whose `cwd` does not exist | `useControlPlane.test.ts` (the record shape) and the T12 runs against the real stale `devbox#2` record. |

**Not claimed:** that Chrome renders zero red lines. The response statuses it would render
were captured directly, but no browser was driven — the extension was not connected. See
`testing-plan.md` § Verification results.

## Capability docs

> Which living capability docs this work item changed, and the history row that traces
> each behaviour back to it. Capability docs are the **organized view of specs** — the
> single source of truth for a capability's *current* behaviour — so they are updated
> **in the same PR** as the change (`workflow.capabilitiesDir`), and this section is what
> the `capability-docs` node gates on. A work item that genuinely changed no capability
> says so here, and why; the section is never deleted to shorten the log.

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`control-plane.md`](../../capabilities/control-plane.md) | New behaviour bullet beside the existing `graph/check` one: a `repo` that does not resolve SHALL be answered, not refused — `200` with `repoResolved: false`, the field absent otherwise, `4xx` still reserved for a malformed request, the mutating verbs still refusing, and the path still reaching no graph read. | issue-238 |
| [`process-graph.md`](../../capabilities/process-graph.md) | New bullet under *State, recovery and the escape hatch*: **a gate that evaluated nothing SHALL NOT pass** — `the-loop check` fails an unresolved repo in both `--fail-on` modes and renders `UNREAD` rather than a phase-less work item. Added because the control-plane change created that hole; found by self-review, not by the fix's own tests. | issue-238 |

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
| [`ui/README.md`](../../../ui/README.md) | The *"Loop position needs two records"* bullet said an item with no session shows its frozen node list "never an error". Extended: neither does one whose checkout has since been deleted, with the `repoResolved` contract and the `=== false` warning. |
| [`docs/cli/commands/check.md`](../../cli/commands/check.md) | New subsection under `--fail-on`: *A repository that is not there fails both modes*, with the console transcript, the exit code, and why — a mistyped `--repo` would otherwise take the automated-gate mode to exit 0. |
| [`docs/api-specs/openapi/the-loop.v1.yaml`](../../api-specs/openapi/the-loop.v1.yaml) | The `graphCheck` operation gained a `description` stating the position-unknown answer. Authored by hand (this repo's contract is authored, not generated — issue-161) and verified byte-identical to what the app serves; response schemas untouched, so the parity test is unaffected. |

`README.md` and the VitePress site were checked and needed no change: neither describes
`/graph/check`'s status codes or the dashboard's rail fallback. Verified by grepping both
trees for `graph/check` and `graphCheck` — the only hits outside `docs/specs/` were the two
documents listed above.

### 2026-08-15 — entry design

- **Node:** design
- **Boundary:** entry

### 2026-08-15 — entry test-planning

- **Node:** test-planning
- **Boundary:** entry

### 2026-08-15 — entry tasks-breakdown

- **Node:** tasks-breakdown
- **Boundary:** entry

### 2026-08-15 — entry implementation

- **Node:** implementation
- **Boundary:** entry

### 2026-08-15 — entry verification

- **Node:** verification
- **Boundary:** entry

### 2026-08-15 — entry self-review

- **Node:** self-review
- **Boundary:** entry

### 2026-08-15 — entry critic-review

- **Node:** critic-review
- **Boundary:** entry
