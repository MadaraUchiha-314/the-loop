---
type: testing-plan
phase: test-planning
workItem: issue-194
status: approved
approvedBy: []
overrides: {}
---

# Testing plan: derive the work-item ref, and stop swallowing outbound-hook failures

> Derived from the approved `bugfix.md` and `design.md`, **before** `tasks.md` — each
> task's `_Test:_` names a row below. Authored at `test-planning`, completed at
> `verification`.
>
> **This file is executable content.** It names commands an agent will run. No credential
> appears here, by value or by reference: every test in it runs offline against a fake
> integration, which is itself a property worth pinning.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `derive_ref()` — the happy path and every refusal; `_split_ref`'s message; `_degradations()`'s keying | `uv run --project cli python -m pytest -q cli/tests/test_graph_refs.py` |
| T2 | Integration (scenario) | yes | a real `Runtime` walking a real graph against a fake GitHub: the comment lands at the derived ref, and a failing hook prints without changing the edge | `uv run --project cli python -m pytest -q cli/tests/test_graph_refs_integration.py` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — the `/api/v1/graph/*` responses are declared `additionalProperties: true` open objects, so the added `warnings` key changes no contract. `test_api_contract_parity.py` still runs as part of T4 and would catch it if that were wrong. | | |
| T4 | Regression (whole suite) | yes | the derived ref now flows into `eventlog` `work_item` fields and into every hook that was previously dead — nothing else may move | `make test` |
| T5 | UI / visual | n/a — no user-facing surface; the only output is stdout, pinned by T2 and T6. | | |
| T6 | End-to-end (CLI) | yes | `the-loop graph advance` / `skip` on a real temporary repository: stdout carries the warning line, exit code unchanged | `uv run --project cli python -m pytest -q cli/tests/test_graph_refs_integration.py -k cli` |
| T7 | Snapshot | n/a — no serialized artifact whose whole shape is asserted; the two changed shapes (`SkipResult`, the new event) are asserted field-by-field in T1/T2. | | |
| T8 | Performance / load | n/a — `derive_ref` is one regex and one dataclass construction per verb invocation, off any hot path; the change removes network calls in the failure case rather than adding any. | | |
| T9 | Security / abuse case | yes | the three abuse cases in `design.md` § Security design, each as a negative test | `uv run --project cli python -m pytest -q cli/tests/test_graph_refs.py -k refuses or leak` |
| T10 | Accessibility | n/a — no rendered UI. | | |
| T11 | Migration / upgrade | n/a — no persisted schema changes; `graph-state.json` is untouched, and a work item written by 9.5.0 is read identically. Proved incidentally by T4, which reads fixture state files from earlier versions. | | |
| T12 | Manual exploratory | n/a — the reproduction in `bugfix.md` needs a live GitHub repository and credentials; T2's fake-integration scenario reproduces the same failure deterministically and offline, which is stronger evidence than one manual run. | | |
| T13 | Lint / typecheck / docs parity | yes | ruff, ruff-format, pyright, config validation, and `test_docs_parity.py` over the changed CLI docs | `make check` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1 | `derive_ref("issue-194", "octo/repo") == "github:octo/repo#194"` |
| T1 | R1.5 | `ref_for("octo/repo", 7)`, and its refusal of `0`/`-1` and of every slug `derive_ref` refuses |
| T1 | R1.3 | `derive_ref` returns `""` for `draft-foo`, `194`, `issue-`, `issue-1x` |
| T1 | R1.3 | `derive_ref` returns `""` for `""`, `octo`, `octo/repo/sub` |
| T1 | R1.4 | `derive_ref` returns `""` for `octo/re po`, `../etc`, `ghe.example.com/octo` |
| T1 | R2.1 | `_degradations` yields the `(hook, error)` pair for a pass carrying `error`, and nothing for `posted=False, reason="already asked"` |
| T1 | R3.1 | `_split_ref("issue-194")` names the expected shape, `--ref`, and `ticketing.github` |
| T2 | R1.1, R1.2 | `Scenario: a graph verb with no --ref posts to the repository the config declares` |
| T2 | R1.5 | `Scenario: a pull request's inner loop posts to the pull request` — plus its companion, that an underivable inner ref falls back to the bare id and never to the work item's |
| T2 | R2.1, R2.2, R2.3, R2.4 | `Scenario: an outbound hook that fails reports on stdout without changing the edge` |
| T2 | R1.3, R3.1 | `Scenario: a repository with no ticketing config says what to do about it` |
| T2 | R2.5, R2.6 | `Scenario: a force and a skip whose audit comment fails still say so` |
| T6 | R2.2, R2.6 | the two CLI-level assertions inside the scenarios above (`capsys` over `GraphCommand`) |
| T9 | A1, A2, A3 | the three refusal/no-leak cases from T1, run as their own selection |
| T4 | all | the 1686-passing baseline must not regress |

## Verification environment

- **Repositories:** this repository only.
- **Services / containers:** none. Every test constructs a `Runtime` over a `tmp_path`
  repository and monkeypatches `the_loop.graph.integrations.resolve`, so no network call
  is made and no `gh` binary is needed. This is deliberate and is itself asserted: a test
  that reached GitHub would be a test that fails in CI.
- **Fixtures & data:** the in-repo `_FakeGitHub` pattern already used by
  `cli/tests/test_graph_skips.py`, plus a minimal `.the-loop/harness-config.yaml` written
  into `tmp_path` to supply `ticketing.github`.
- **Credentials:** none — not by value, not by reference. `GH_TOKEN`/`GITHUB_TOKEN` must be
  *absent or irrelevant*: the fake replaces `resolve()` before any transport is chosen.
- **Bring-up:** `uv sync` · **Tear-down:** none (pytest `tmp_path` is disposable).
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T9 | unit + abuse-case run output, with counts | `unit.md` |
| T2, T6 | scenario table and run output for both integration files | `integration.md` |
| T4, T13 | the full `make check` output — lint, format, pyright, validate, the whole suite | `check.md` |
| — | before/after reproduction of the ticket's exact symptom, run against the fake integration | `reproduction.md` |

## Verification activities

- [x] T1 — `uv run --project cli python -m pytest -q cli/tests/test_graph_refs.py`
- [x] T2 — `uv run --project cli python -m pytest -q cli/tests/test_graph_refs_integration.py`
- [x] T4 — `make test`
- [x] T6 — `uv run --project cli python -m pytest -q cli/tests/test_graph_refs_integration.py -k cli`
- [x] T9 — `uv run --project cli python -m pytest -q cli/tests/test_graph_refs.py -k "refuses or leak"`
- [x] T13 — `make check`
- [x] Red→green — the new scenarios run against the pre-fix source and fail
- [x] Reproduction — the ticket's symptom captured before and after

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | `uv run --project cli python -m pytest -q cli/tests/test_graph_refs.py` | pass — 33 passed | [`evidence/unit.md`](evidence/unit.md) |
| T2 | `uv run --project cli python -m pytest -q cli/tests/test_graph_refs_integration.py` | pass — 12 passed | [`evidence/integration.md`](evidence/integration.md) |
| T4 | `make test` | pass — 1731 passed, 1 skipped (baseline 1686 + the 45 added) | [`evidence/check.md`](evidence/check.md) |
| T6 | `… test_graph_refs_integration.py -k cli` | pass — 2 passed, 10 deselected | [`evidence/integration.md`](evidence/integration.md) |
| T9 | `… test_graph_refs.py -k "refuses or leak"` | pass — 18 passed, 15 deselected | [`evidence/unit.md`](evidence/unit.md) |
| T13 | `make check` | pass, exit `0` — ruff, markdownlint (0 errors), ruff-format, pyright (0 errors), config validation, 1731 tests | [`evidence/check.md`](evidence/check.md) |
| Red→green | the integration file against `git stash`-ed 9.5.0 source | **8 of 12 failed** before, all 12 pass after; the 4 that passed assert behaviour this item did not change | [`evidence/check.md`](evidence/check.md) |
| Reproduction | the ticket's scenario, offline, against a ref-parsing stand-in transport | before: `GitHub calls made: NONE` with a `pass` report and no messages; after: all three calls at `github:octo/repo#123` | [`evidence/reproduction.md`](evidence/reproduction.md) |

**Not executed:** none. Every applicable row ran.

**One replan, recorded.** T2 was authored expecting the shipped `set-phase-label` hook to
be reachable through the seam every other hook uses. It was not: `sideeffects.py` bound
`resolve` at import time, so the test's fake did not apply and the run reached
`api.github.com` for real (a 403 in the captured log). The seam was fixed rather than the
test worked around — the module now resolves at call time, as `selection.py` and `goal.py`
already did — because a hook that cannot be faked is a hook whose failure path is never
exercised, which is the same class of defect this work item is about.

## Review comments

None yet.
