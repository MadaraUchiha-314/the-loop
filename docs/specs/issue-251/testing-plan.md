---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#251"
status: in-review             # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Testing plan: integration tests that wait on the attempt and assert on its outcome

> Derived from `bugfix.md` and `design.md`, **before** `tasks.md`. Authored at
> `test-planning` and completed at `verification` — one file, written once as a plan and
> once as a record.
>
> **This file is executable content.** Review the commands like code. No credentials are
> named here, by reference or otherwise: the suite is hermetic (tmp paths, fake GitHub
> state, an in-process tmux double) and reaches no network.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | n/a — this work item adds no unit of production behaviour. The `--dispatch-lag` fixture is exercised by every test that runs under it, which is a stronger check than a unit test of the fixture. | | |
| T2 | Integration (scenario) | yes | The two fixed tests still prove their own scenarios (a failed delivery is isolated and retried; an abandoned comment is reported on the work item) — the fix changes *when* they look, never *what* they claim. | `uv run --project cli python -m pytest cli/tests/test_webhook_routing_integration.py cli/tests/test_poller_integration.py` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — no API surface changes. | | |
| T4 | End-to-end | n/a — the PDLC e2e suite (`test_pdlc_e2e_integration.py`) is unaffected; it runs in the full-suite rows below rather than as its own activity. | | |
| T5 | UI / visual | n/a — no user-facing surface (`design.md` §UI/UX design). | | |
| T6 | Snapshot | n/a — no rendered artifact. | | |
| T7 | Performance / load | n/a as a *benchmark*, but the cost of the default path is checked: the clean full-suite run (T9) must stay in the same band as the pre-change baseline, proving `--dispatch-lag=0` is inert. | | |
| T8 | Security / abuse case | yes | One negative check for the one boundary this change has: the lag cannot be turned on outside pytest. Grepped rather than asserted, because there is nothing to call. | `rg -n "dispatch.lag" cli/the_loop` — must return nothing |
| T9 | Chaos (added row — the regression test for this work item) | yes | Every dispatcher write that follows a spawn or a delivery, delayed 0.5s: no test in the suite may fail. This is the acceptance criterion for R1.4 and the proof for R1.3. | `uv run --project cli python -m pytest --dispatch-lag=0.5 cli` |
| T10 | Accessibility | n/a — no UI. | | |
| T11 | Migration / upgrade | n/a — no schema, config key or on-disk format changes. | | |
| T12 | Manual exploratory | n/a — the behaviour under test is a race, which is precisely what a human cannot observe reliably; T9 replaces it. | | |
| T13 | Lint / typecheck / markdown | yes | Repo-wide gates, CI parity (`make lint`, `make typecheck`, `make format-check`). Markdown matters here: this work item is mostly documents. | `make lint format-check typecheck` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T2 | R1.1, R1.2 | `Scenario: A failed tmux delivery is logged and the delivery can be retried` |
| T2 | R1.1, R1.2 | `Scenario: every delivery of a comment fails until the retry budget is spent` |
| T9 | R1.3 | Both tests above fail under `--dispatch-lag=0.5` before the fix, pass after it |
| T9 | R1.4, R2.1, R2.2 | The whole suite passes under `--dispatch-lag=0.5`; absent the flag, nothing is patched |
| T8 | `design.md` §Security design | The lag has no caller outside the test suite |
| T13 | R3.1, R3.2 | The shipped rule and the capability doc lint clean |

## Verification environment

- **Repositories:** this repo only.
- **Services / containers:** none. The suite fakes GitHub, tmux and the harness at their
  seams; no daemon, no service, no container.
- **Fixtures & data:** the suite's own (`cli/tests/conftest.py`, `cli/tests/fixtures/`).
- **Credentials:** none — not by value and not by reference. Nothing here authenticates.
- **Bring-up:** `uv sync` · **Tear-down:** none (tmp paths are pytest's).
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, escalate on the PR.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T2, T9 | The sweep: the pre-fix lagged run over the whole suite (the two failures, with the failing assertions), and the post-fix lagged run | `sweep.md` |
| T2, T9, T13 | Final validation: clean suite, lagged suite, lint, format, typecheck | `verification.md` |

Redaction: the only environment-specific strings in this output are pytest's
`/tmp/pytest-of-root/...` paths. No tokens, hostnames, or personal data are produced by
this suite.

## Verification activities

- [x] T2 — `uv run --project cli python -m pytest -q cli/tests/test_webhook_routing_integration.py cli/tests/test_poller_integration.py`
- [x] T8 — grep for a `--dispatch-lag` caller under `cli/the_loop/` (must be none)
- [x] T9a — pre-fix: `uv run --project cli python -m pytest -q --dispatch-lag=0.5 cli` (expect exactly the two failures)
- [x] T9b — post-fix: `uv run --project cli python -m pytest -q --dispatch-lag=0.5 cli` (expect zero)
- [x] T9c — clean: `uv run --project cli python -m pytest -q cli`
- [x] T13 — `make lint`, `make format-check`, `make typecheck`

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T9a (pre-fix) | `pytest -q -p lagplugin2 -p no:randomly cli` (the option's prototype, same seams, 0.5s) | **2 failed, 2221 passed, 1 skipped** — exactly the two tests `bugfix.md` names | [`sweep.md`](evidence/sweep.md) |
| T9a (per-test) | `pytest --dispatch-lag=0.5` on each named test, fix reverted | both fail on every run | [`sweep.md`](evidence/sweep.md) |
| T2 | `pytest -q cli/tests/test_webhook_routing_integration.py cli/tests/test_poller_integration.py` | 42 passed | [`verification.md`](evidence/verification.md) |
| T9b | `pytest -q --dispatch-lag=0.5 cli` | 2223 passed, 1 skipped, in 9m23s | [`verification.md`](evidence/verification.md) |
| T9c | `pytest -q cli` | 2223 passed, 1 skipped, in 1m58s — the same band as the pre-change baseline (2m02s) | [`verification.md`](evidence/verification.md) |
| T8 | `rg -n "dispatch.lag" cli/the_loop` | no matches — the lag has no caller in production code | [`verification.md`](evidence/verification.md) |
| T13 | `make lint`, `make format-check`, `make typecheck` | clean | [`verification.md`](evidence/verification.md) |

**Not executed:** none. Every planned activity ran.

## Review comments

*None yet.*
