---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#247"
status: in-review             # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Testing plan: record-feedback writes markdown that fails the project's own markdownlint

> Derived from `bugfix.md` and `design.md`, **before** `tasks.md` — each task's `_Test:_`
> names a row of the matrix below. Authored at `test-planning` and completed at
> `verification`. See `reference/testing.md`.
>
> **This file is executable content.** It names commands an agent will run, so review it
> like code. Credentials appear by reference only; this work item needs none.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `record_feedback` emits no line that is emphasis and nothing else (R1.1), and an empty body produces no blank-line pair (R1.2) | `uv run --project cli python -m pytest -q cli/tests/test_graph_integration.py` |
| T2 | Integration (scenario) | yes | at the `design-approval` gate, a recorded approval keeps the handle and the body (R2.1, R2.2) and lands lint-clean by shape (R1.3) | `uv run --project cli python -m pytest -q cli/tests/test_graph_integration.py` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — no API surface changes; the control-plane spec under `docs/api-specs/` is untouched | | |
| T4 | End-to-end | n/a — an end-to-end run needs a live webhook, a tmux session and a human approver; the gate's exit chain is already covered at T2, which is the seam the defect lives on | | |
| T5 | UI / visual | n/a — no user-facing surface (`design.md` §UI/UX) | | |
| T6 | Snapshot | n/a — the artifact's exact bytes are asserted directly at T1/T2; a snapshot would restate them less legibly | | |
| T7 | Performance / load | n/a — two string branches on a path that runs once per human approval | | |
| T8 | Security / abuse case | yes | the authorization boundary this hook sits behind still holds: an unauthorized author's approval is not read, and a self-authored comment is not feedback (existing negative tests, re-run because the file changed) | `uv run --project cli python -m pytest -q cli/tests/test_graph_integration.py` |
| T9 | Accessibility | n/a — no rendered UI | | |
| T10 | Migration / upgrade | n/a — no persisted state, no config key, no schema; artifacts already recorded into by the old code are explicitly out of scope | | |
| T11 | Manual exploratory | n/a — replaced by T12, which is the same check made reproducible | | |
| T12 | Linter conformance (added) | yes | the real linter, at the version `make lint` pins, accepts an artifact the fixed hook recorded into — and rejects the same artifact recorded into by the old hook (R1.3) | `npx --yes markdownlint-cli2@0.18.1 "<artifact>"` |
| T13 | Repository gates (added) | yes | the whole repository still passes what CI runs: ruff, ruff format, pyright, config validation, the full suite, and markdownlint over every `**/*.md` — including the four spec artifacts this work item adds | `make check` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1 | `test_a_recorded_review_never_writes_emphasis_alone_on_a_line` |
| T1 | R1.2 | `test_a_comment_with_no_body_is_recorded_without_a_blank_line_pair` |
| T2 | R1.3, R2.1, R2.2 | `Scenario: an approval carrying suggestions is recorded in the artifact` (extended: the recorded block is lint-clean and the body is verbatim) |
| T8 | bugfix.md §Security considerations | `Scenario: an unauthorized author's approval is not feedback` · `Scenario: the harness's own comment is not feedback` (existing) |
| T12 | R1.3 | the fixed hook's output through `markdownlint-cli2`, and the old hook's output through the same, in the same run |
| T13 | R3.1, R3.2 | `make check` |

## Verification environment

- **Repositories:** this repo only.
- **Services / containers:** none.
- **Fixtures & data:** none beyond `pytest` `tmp_path` fixtures already in the suite.
- **Credentials:** none. This work item reads and writes no secret.
- **Node.js:** required for T12 and for the markdown half of T13 only — `npx` fetching
  `markdownlint-cli2@0.18.1`, the same invocation `make lint` uses. The Python suite (T1,
  T2, T8) deliberately does **not** depend on it.
- **Bring-up:** `uv sync` · **Tear-down:** none.
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate — do not pass the gate on an environment that never
  came up.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T8 | the red run (both new tests failing against the unfixed hook) | `red.md` |
| T1, T2, T8 | the green run, with counts | `green.md` |
| T12 | both linter runs — old shape rejected, new shape accepted — with the exact output | `shapes.md` |
| T13 | `make check` output, per target | `check.md` |

Nothing captured here contains a token, a hostname or personal data: the fixtures use the
literal author `owner` and bodies written for the tests.

## Verification activities

- [x] T1 — `uv run --project cli python -m pytest -q cli/tests/test_graph_integration.py`
- [x] T2 — same command (the gate scenario)
- [x] T8 — same command, plus `cli/tests/test_pdlc_e2e_integration.py` in the whole-suite run
- [x] T12 — `npx --yes markdownlint-cli2@0.18.1` over an artifact recorded by each shape
- [x] T13 — `make check`

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | `uv run --project cli python -m pytest -q cli/tests/test_graph_integration.py` | pass — both new tests red before the fix, green after; 21 passed | [`evidence/red.md`](evidence/red.md), [`evidence/green.md`](evidence/green.md) |
| T2 | same command | pass — the extended gate scenario asserts the handle, the body verbatim, and no emphasis-only line | [`evidence/red.md`](evidence/red.md), [`evidence/green.md`](evidence/green.md) |
| T8 | same command, and the full suite for `test_self_authored_and_unauthorized_comments_never_release_a_gate` | pass — both negative tests unchanged and still passing | [`evidence/green.md`](evidence/green.md) |
| T12 | `npx --yes markdownlint-cli2@0.18.1` over `old.md`/`new.md` (the same two comments through each shape) and over the three candidate shapes | pass — 2× MD036 on the pre-fix shape, 0 errors on the fixed one; the ticket's blockquote candidate also passes, for the reason the design rejects it | [`evidence/shapes.md`](evidence/shapes.md) |
| T13 | `make check` | pass — ruff, ruff format, pyright (0 errors), config validation, markdownlint over every `**/*.md` (0 errors), 2225 passed / 1 skipped | [`evidence/check.md`](evidence/check.md) |

**Not executed:** none. Every planned activity ran.

Two findings from the verification itself, both recorded rather than smoothed over:

- **This work item's own artifacts failed markdownlint on the first full run** — an
  `MD038` in `bugfix.md` (a code span written as `` `+ ` ``) and an `MD010` in
  `shapes.md`, where the captured linter output quotes a hard tab back. Fixed and
  disabled-with-a-reason respectively, before T13 was ticked. Worth stating: the gate
  that caught them is the same one this ticket is about.
- **T12 confirms the ticket's blockquote suggestion works.** It is rejected on the
  grounds in `design.md` §Chosen shape — it passes only because MD036 does not descend
  into blockquotes — not because it fails.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed: an approval never silently
> discards a reviewer's suggestions, and the feedback travels with the document
> it concerns rather than living in a side-channel tracker.
