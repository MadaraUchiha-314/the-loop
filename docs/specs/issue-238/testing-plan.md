---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#238"
status: approved             # draft | in-review | approved
approvedBy: ["@MadaraUchiha-314"]  # PR #241, 2026-08-16
overrides: {}
---

# Testing plan: a vanished checkout is an answer, not an error

> Derived from the approved [`bugfix.md`](bugfix.md) and [`design.md`](design.md), before
> `tasks.md` — each task's `_Test:_` names a row of the matrix below. Authored at
> `test-planning`, completed at `verification`.
>
> **This file is executable content.** It names commands an agent will run, so review it
> like code.

**Two existing tests assert the behaviour this work item removes, and both are rewritten
rather than deleted.** They are named in T1 and T3 below and called out again in the task
list, because "the test changed" is the claim a reviewer should be most suspicious of on a
bug fix. The red→green evidence is therefore captured as *two* runs: the new assertions
against the unfixed code (red), then the whole suite after (green).

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit (Python) | yes | `core.graphs.check` answers a non-resolving `repo` with `repoResolved: False` and an empty node list, constructs no runtime (R3.2), and leaves a resolving repo's five keys untouched (R2.2). `repo_resolves` agrees with `resolve_repo` on directory / file / missing. | `uv run pytest cli/tests/test_core_graphs.py` |
| T2 | Unit (UI, vitest) | yes | `fetchGraphs` stores no report when the answer carries `repoResolved: false`, so `buildViews` falls back to `railFromFrozen` (R2.1); a normal answer is still stored. | `cd ui && bun run test` |
| T3 | Integration (scenario) | yes | `POST /api/v1/graph/check` over the real app returns `200` for a path that does not exist and `200` with a position for one that does — the route, the core call and the error mapping together. Gherkin-documented per `testing.gherkinDocstrings`. | `uv run pytest cli/tests/test_api_routers_integration.py` |
| T4 | Contract (OpenAPI) | yes | The `graphCheck` operation's new `description` lands in `docs/api-specs/openapi/the-loop.v1.yaml` and the served schema still matches it (R3.3). | `uv run pytest cli/tests/test_api_contract_parity.py` |
| T5 | End-to-end | n/a — the browser-to-service path has no automated harness in this repo, and the one thing e2e would add over T3 is "Chrome logged nothing", which is a devtools observation. Covered manually as T12. | | |
| T6 | UI / visual | n/a — the design's central claim is that **nothing rendered changes** (R2.1). There is no new state to screenshot; the assertion that the old rendering survives is T2, where it is checked as data rather than pixels. | | |
| T7 | Snapshot | n/a — no serialized fixture covers `GraphStatus`, and adding one to assert an absent field would test the fixture rather than the code. T1 asserts the key set directly. | | |
| T8 | Performance / load | n/a — the change removes work (an early return before any graph read). No path gets slower, and nothing here is on a hot loop worth measuring. | | |
| T9 | Security / abuse case | yes | Negative tests for both abuse cases in `design.md` § Security design: the unknown-position body leaks no path or filesystem string, and a non-resolving `repo` reaches no core graph call. | `uv run pytest cli/tests/test_core_graphs.py -k "resolve or unknown"` |
| T10 | Accessibility | n/a — no rendered change, so no new markup, focus order or contrast to evaluate. | | |
| T11 | Migration / upgrade | n/a — no persisted state, schema or config key changes. An older UI build talking to a newer service ignores an unknown key and keeps its `catch`; a newer UI against an older service never sees the field and behaves as it does today. Both directions are already correct without a migration. | | |
| T12 | Manual exploratory | yes | The reported symptom, checked the way it was reported: `curl` against the stale worktree path returns `200`, and the control-plane UI polling a state root with a stale session record logs no `/graph/check` errors in the devtools console across several ticks. | by hand, against a locally running `the-loop start` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R2.2, R3.2, R4.1 | `check` on a missing path → `repoResolved: False`, `nodes: []`, `currentNode: ""`; `_runtime` monkeypatched to raise is never called. `check` on this repository → exactly `workItem`, `currentNode`, `ok`, `parked`, `nodes`. |
| T1 | R3.1 | `repo_resolves` returns `False` for a missing path and for a regular file, `True` for a directory — the same three cases `test_resolve_repo_rejects_non_directory` already covers, now asserted on the shared predicate. |
| T2 | R2.1 | `fetchGraphs` given a client answering `repoResolved: false` returns `{outer: {}, inner: {}}`; given a normal answer it returns the report keyed by ref. |
| T3 | R1.1, R1.2 | `Scenario: a control-plane client asks where a work item stands in a checkout that has been deleted` |
| T3 | R2.2 | `Scenario: a control-plane client asks about a checkout that is still there` |
| T4 | R3.3 | The existing parity scenario, unchanged: *the served schema drifts from the authored contract*. |
| T9 | design.md § Security design, abuse cases 1–2 | The unknown-position body contains no substring of the supplied path; a non-resolving repo constructs no runtime. |
| T12 | R1.1, R1.2, R1.3 | The reproduction from `bugfix.md`, re-run after the fix, plus the console observation the ticket was opened about. |

Rendered scenario table for the reviewer briefing: `uv run the-loop scenarios --format markdown`.

## Verification environment

- **Repositories:** this repository only. No second checkout, no external service.
- **Services / containers:** none for T1–T4 and T9. T12 needs the local service —
  `the-loop start` — reachable at its configured address (`http://127.0.0.1:4114` on the
  reporter's machine) and the control-plane UI (`cd ui && bun run dev`) pointed at it.
- **Fixtures & data:** T1/T3 build their own `tmp_path` repositories, as the existing tests
  in those files already do. T12 needs a session record whose `cwd` no longer exists; the
  reporter's stale `github:MadaraUchiha-314/devbox#2` record is one, and any closed session
  whose worktree has been removed will do. **Do not create one by deleting a worktree that
  another session is using.**
- **Credentials:** none. No row authenticates to anything; the API is loopback and the two
  test suites are offline.
- **Bring-up:** `uv sync` (Python), `cd ui && bun install --frozen-lockfile` (UI),
  `the-loop start` (T12 only). · **Tear-down:** `the-loop stop` (T12 only). Nothing else
  leaves state behind.
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate. T12 is the only row with an environment that can fail
  to come up; T1–T4 and T9 failing to run is a repository problem, not an environment one.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T0 | The red run: the new assertions against the **unfixed** code, proving they fail before the change (R4.1) | `red.md` |
| T1, T3, T4, T9 | Command, full pytest output, counts and duration | `unit-and-integration.md` |
| T2 | Command and vitest output | `ui-tests.md` |
| T12 | The `curl` transcript before and after; a screenshot of the devtools console after several poll ticks with no `/graph/check` error | `manual.md`, `manual-console.png` |

**Redaction.** The `curl` transcript and the console screenshot both carry absolute
filesystem paths containing the operator's username, and the screenshot may show work-item
titles from unrelated repositories. Replace the home-directory prefix with `/Users/…` in
text evidence (as `bugfix.md` already does), and crop or blank unrelated rows in the
screenshot before committing. No token, cookie or credential appears on any of these
surfaces; if one does, the capture is not committed and the row says so.

## Verification activities

- [x] T0 — capture the red run: apply the new tests only (no fix) and run
      `uv run pytest cli/tests/test_core_graphs.py cli/tests/test_api_routers_integration.py`
- [x] T1 — `uv run pytest cli/tests/test_core_graphs.py`
- [x] T2 — `cd ui && bun run test`
- [x] T3 — `uv run pytest cli/tests/test_api_routers_integration.py`
- [x] T4 — `uv run pytest cli/tests/test_api_contract_parity.py`
- [x] T9 — `uv run pytest cli/tests/test_core_graphs.py -k "resolve or unknown"`
- [x] Full suite — `uv run pytest` and `cd ui && bun run lint && bun run test && bun run build`
- [x] T12 — `curl` the stale path against a running service, before and after
- [ ] T12 (visual) — open the UI and read the devtools console across at least three poll
      ticks. **Not executed** — the browser extension was not connected. Replanned; see
      Verification results.

## Verification results

Every planned activity ran except the devtools screenshot, which was replanned rather than
skipped — the row and its reason are below the table.

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T0 — red | `uv run pytest cli/tests/test_core_graphs.py cli/tests/test_api_routers_integration.py` (before the fix) | 4 failed, 19 passed — the four new/rewritten assertions | [`evidence/red.md`](evidence/red.md) |
| T0 — red (UI) | `cd ui && bun run test` (before the fix) | 1 failed, 105 passed — `fetchGraphs` stored the answer it should drop | [`evidence/red.md`](evidence/red.md) |
| T1, T3 | `uv run pytest cli/tests/test_core_graphs.py cli/tests/test_api_routers_integration.py` | pass — 23 passed | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| T2 | `cd ui && bun run test` | pass — 106 passed (8 files) | [`evidence/ui-tests.md`](evidence/ui-tests.md) |
| T4 | `uv run pytest cli/tests/test_api_contract_parity.py` + a direct authored-vs-served description comparison | pass — 2 passed, descriptions `identical: True` | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| T9 | `uv run pytest cli/tests/test_core_graphs.py -k "resolve or unknown"` | pass — 3 passed, 11 deselected | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| Full suite (Python) | `uv run pytest` | 2103 passed, **4 failed** — all four are CI-machine assertions failing on this macOS workstation, proved unrelated by re-running them against the stashed tree | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| Full suite (UI) | `cd ui && bun run lint && bun run test && bun run build` | pass — no lint findings, 106 tests, build clean (`tsc --noEmit` included) | [`evidence/ui-tests.md`](evidence/ui-tests.md) |
| T12 — the reported request | `curl` the stale worktree path at `:4114` (10.2.0) and `:4199` (this branch), same state root | pass — `400` before, `200 {"repoResolved": false}` after; a live checkout still answers with a position and no `repoResolved` key | [`evidence/manual.md`](evidence/manual.md) |
| T12 — one real poll tick | the board's own `fetchGraphs` + `HttpApi` against both services, with `fetch` wrapped to record statuses | pass — 1× 4xx before, 0× after, and `reports.outer` identical in both runs | [`evidence/manual.md`](evidence/manual.md) |

**Not executed:** *T12 (visual) — the devtools console screenshot.* The Chrome extension
this session drives a browser through was not connected (`tabs_context_mcp` returned
"Browser extension is not connected"), so no browser could be opened. The service and the
Vite dev server were brought up for it and CORS was configured; only the browser was
missing.

**Replanned, not dropped.** A console screenshot would have shown a list of `/graph/check`
response statuses. That list was captured directly instead, from the same client code the
browser runs, against the same records — with a before/after contrast a single screenshot
could not have provided. What stays unverified by machine is the last inch: that Chrome
renders zero red lines for a set of `200` responses. That is browser behaviour rather than
this project's, and a human can confirm it in thirty seconds; flagged on PR #241 rather
than claimed.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed.

### 2026-08-15 — approved

By @MadaraUchiha-314 —

approved
