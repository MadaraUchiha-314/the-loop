---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#246"
status: approved             # draft | in-review | approved
approvedBy: ["@MadaraUchiha-314"]  # PR #248
overrides: {}
---

# Testing plan: the poller reads all three PR comment surfaces

> Derived from the approved `bugfix.md` and `design.md`, **before** `tasks.md` — each
> task's `_Test:_` names a row of the matrix below. Authored at `test-planning` and
> completed at `verification`.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit — fetch & merge | yes | `GhClient.list_comments` asks for all three streams on a PR and one on an issue; merges, sorts by time, drops empty-body and `PENDING` reviews (R1.4, R1.5, R2.4, R4.1) | `uv run pytest cli/tests/test_poller.py -k comments` |
| T2 | Integration (scenario) | yes | a whole poll cycle: a review body and an inline comment each reach the dispatcher **exactly once** across two cycles, with the anchor; an unauthorized review and an empty approval never do (R1.1, R1.2, R2.1, R2.2, R3.1) | `uv run pytest cli/tests/test_poller_integration.py -k review` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — the poller is a client of GitHub's API, not a publisher of one; this work item adds no route to `docs/api-specs/` | | |
| T4 | End-to-end | n/a — an end-to-end run needs a live GitHub PR, a real `gh` login and a spawned harness session; the verification environment below has no `gh` binary and no credentials, and inventing one would test GitHub, not this change. T2 covers the same path with the subprocess boundary faked at the seam the code already exposes for it | | |
| T5 | UI / visual | n/a — no user-facing surface; the poller is a daemon | | |
| T6 | Snapshot | n/a — the asserted payloads are small and explicit; a snapshot would hide exactly the key set T1 is meant to pin | | |
| T7 | Performance / load | n/a — the change adds two bounded HTTP reads per polled PR per cycle (default 60s). No latency budget exists to regress against; the cost is stated in `design.md` § Trade-offs and reviewed there | | |
| T8 | Security / abuse case | yes | one negative test per trust boundary in `design.md` § Security design: unauthorized reviewer, the-loop's own review (self-comment marker), author-less review (R3.1, R3.2) | `uv run pytest cli/tests/test_poller.py -k "unauthorized or self_authored"` |
| T9 | Accessibility | n/a — no user-facing surface | | |
| T10 | Migration / upgrade | yes | an existing per-item ledger reads forward: `IC_` ids in `seenComments` are still honoured, and the new ids arrive as unresolved rather than as a re-forward of the whole thread (`design.md` § Data models) | `uv run pytest cli/tests/test_poller.py -k ledger` |
| T11 | Manual exploratory | n/a — see T4: no `gh`, no credentials in this environment. The reported failure is reproduced instead as an executable test against the pre-fix code (T12), which is stronger than a manual retelling | | |
| T12 | Regression (red→green) | yes | the reported symptom, as a test: against unfixed code the review on the reproduction thread is never forwarded; against fixed code it is (R5.1) | `uv run pytest cli/tests/test_poller.py cli/tests/test_poller_integration.py` |
| T13 | Whole-suite regression | yes | nothing else in the CLI depends on the shapes that changed (`Comment` arity, `_SEEN_COMMENTS_CAP`, the poll event names) | `uv run pytest` |
| T14 | Lint / typecheck / markdown | yes | this repo's own gate commands (`hooks.prePush`) over the changed files, docs included | `ruff`, `pyright`, `markdownlint` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.3, R1.4, R1.5, R2.2, R2.3, R2.4, R4.1 | `list_comments` on a PR issues `pr view` + both `gh api` reads; on an issue, `issue view` alone. Empty-body and `PENDING` reviews absent from the result; an outdated inline comment carries `original_line` |
| T2 | R1.1, R1.2, R2.1, R2.2, R3.1 | `Scenario: a PR review left on a polled pull request reaches its session exactly once` |
| T2 | R1.4, R3.1 | `Scenario: an empty approval and an unauthorized review are never forwarded` |
| T8 | R3.1, R3.2 | unauthorized author resolved-not-forwarded; a review carrying `<!-- the-loop:agent-comment -->` resolved-not-forwarded; `user: null` treated as unauthorized |
| T10 | R4.3 | a ledger written by an older version keeps its `IC_` baseline; the cap covers the merged stream |
| T12 | R5.1 | the four assertions above, all failing before the fix |

## Verification environment

- **Repositories:** this repository only, at the work item's branch.
- **Services / containers:** none. The poll cycle is driven in-process; the `gh`
  subprocess boundary is faked through `GhClient(runner=…)`, the injection point the
  module ships for exactly this.
- **Fixtures & data:** canned GitHub JSON inline in the tests — the reviews/review-comments
  payloads are trimmed copies of the documented REST shapes.
- **Credentials:** none. No token is read, and no network call is made by any row above.
- **Bring-up:** `uv sync` · **Tear-down:** none (no state outside `tmp_path`).
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T12 | the failing run against unfixed code, per assertion | `red.md` |
| T1, T2, T8, T10 | targeted run output with counts | `unit-and-integration.md` |
| T13 | whole-suite counts, and any pre-existing failure identified as such | `unit-and-integration.md` |
| T14 | lint / typecheck / markdownlint output | `lint-and-typecheck.md` |

Nothing captured here contains a token, a hostname or personal data: the fixtures are
invented logins (`octocat`, `stranger`) against `octo/repo`.

## Verification activities

- [x] T1 — `uv run pytest cli/tests/test_poller.py -k "comments or review"`
- [x] T2 — `uv run pytest cli/tests/test_poller_integration.py -k review`
- [x] T8 — `uv run pytest cli/tests/test_poller.py -k "unauthorized or self_authored"`
- [x] T10 — `uv run pytest cli/tests/test_poller.py -k "ledger or cap"`
- [x] T12 — the same tests against the pre-fix tree (red), captured before the fix
- [x] T13 — `uv run pytest`
- [x] T14 — `ruff check`, `ruff format --check`, `pyright`, `markdownlint`

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T12 (red) | the new tests against the tree with the three source files reverted | **10 failed**, 139 passed — including the reported symptom itself (`tmux.delivers` never reaches 2 on the poll cycle) | [`red.md`](evidence/red.md) |
| T1 | `uv run pytest cli/tests/test_poller.py -k "comments or review" -q` | pass — 15 passed, 115 deselected | [`unit-and-integration.md`](evidence/unit-and-integration.md) |
| T2 | `uv run pytest cli/tests/test_poller_integration.py -k review -q` | pass — 2 passed (both Gherkin-documented) | [`unit-and-integration.md`](evidence/unit-and-integration.md) |
| T8 | `uv run pytest cli/tests/test_poller.py -k "unauthorized or self_authored or webhook_path_is" -q` | pass — 9 passed | [`unit-and-integration.md`](evidence/unit-and-integration.md) |
| T10 | `uv run pytest cli/tests/test_poller.py -k ledger -q` | pass — 5 passed | [`unit-and-integration.md`](evidence/unit-and-integration.md) |
| T13 | `uv run pytest -q` | pass — **2124 passed, 1 skipped, 0 failed** | [`unit-and-integration.md`](evidence/unit-and-integration.md) |
| T14 | `ruff check` · `ruff format --check` · `pyright` · `markdownlint-cli2` | pass — clean on all four (222 files formatted, 0 pyright diagnostics, 0 markdown errors) | [`lint-and-typecheck.md`](evidence/lint-and-typecheck.md) |

**Which of the new tests were actually red**, stated because "10 failed" flatters itself:
the four *negative* cases (empty approval, `PENDING` review, unauthorized reviewer,
self-marked review) pass against the unfixed tree too — trivially, since it reads no
reviews at all. They gate the fix, not the bug. The nine failures that mattered are the
positive ones: the three-surface fetch, the anchor, the per-kind event shapes, the merged
ledger, and the end-to-end cycle.

**Corrected after execution:** the T2 row of the matrix says the two instructions "each
reach the dispatcher exactly once", and the test first asserted two *deliveries*. What
actually happens is one delivery and one endpoint spawn: a `pull_request_review*` payload
names a pull request, so the dispatcher opens that PR's inner loop and the instruction
becomes its first prompt (`sessionPerPr`). The requirement — conveyed exactly once, never
again — is met and asserted; the assertion was wrong about *where*. See `design.md` § What
the kind-specific names activate downstream.

**Not executed:** T4 and T11 (both `n/a` in the matrix above, with reasons stated there —
no `gh` binary and no GitHub credentials exist in this environment). Neither was replanned
into a weaker form: T12 reproduces the reported symptom as an executable red test, which is
what a manual retelling would only have described. What this leaves unproven is named in
§ Residual risk below.

## Residual risk

One assumption cannot be tested here, so it is stated rather than implied: that
`gh api --paginate` merges the pages of a JSON **array** response into one array, which is
what `_run_rest_list` parses. It is `gh`'s documented behaviour for array endpoints (the
reason `--slurp` exists for object responses), and a `gh` that behaved otherwise would emit
concatenated arrays — invalid JSON, which `_run_json` turns into a loud `GhError` on the
existing `poll.item_error` path, not a silent empty list. So the failure mode of a wrong
assumption is a visible, retried error rather than the silence this work item is fixing.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109).

*None yet.*
