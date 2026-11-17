---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#533"
status: draft                # the design-approval gate locks it (declared skipped here; review is on the PR)
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: opt-in session credentials, never on argv

> Derived from [`requirements.md`](requirements.md) and [`design.md`](design.md). The
> proof that matters is a real tmux spawn (T2): it is the only test that can show a
> value is absent from `ps`, from the server's global environment and from a second
> session. Everything else is unit-level.
>
> **This file is executable content.** Credentials appear by reference only; the tests
> use dummy values.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | config parsing and warnings, boundary resolution per work item, `compare()`, file writing and loader argv, client-env stripping, scrubber, route scrubbing, event-log scrubbing, visibility rows | `cd cli && uv run python -m pytest -q tests/test_envstate.py tests/test_tmux_runner.py tests/test_sessioncreds.py tests/test_session_environment.py tests/test_api_session_credentials.py` |
| T2 | Integration (scenario) | yes | a real tmux spawn on a private server: pane holds the value; `ps`, `show-environment -g` and a second session do not; the file is `0600` and gone; rotation reads `stale`; with nothing configured, today's behaviour | `cd cli && uv run python -m pytest -q tests/test_session_credentials_integration.py tests/test_session_secrets_integration.py` |
| T3 | Contract (OpenAPI) | n/a — no route, request or response shape changes; scrubbing alters field *content* only | | |
| T4 | End-to-end | n/a — T2 drives the real runner and tmux; a daemon + GitHub round-trip adds a network dependency without covering a further criterion | | |
| T5 | UI / visual | n/a — no UI | | |
| T6 | Snapshot | n/a — no rendered output worth freezing; the status line and list column are asserted directly in T1 | | |
| T7 | Performance / load | n/a — one `stat` per event-log line when configured, nothing otherwise; asserted structurally in T1 (no disk read when unconfigured) | | |
| T8 | Security / abuse case | yes | one negative test per abuse case A1–A7 (design § Security design table) | within T1 and T2 commands |
| T9 | Accessibility | n/a — no UI | | |
| T10 | Migration / upgrade | yes | the issue-482 suite passes unchanged with no `sessionCredentials` (R1.2); schema validation of the shipped example configs | `cd cli && uv run python -m pytest -q` (full suite) and `make validate` |
| T11 | Manual exploratory | n/a — T2 already exercises the real spawn path end to end | | |
| T12 | Static checks | yes | lint, format, typecheck, markdown lint — CI parity | `make lint format-check typecheck` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.3, R1.4, R1.6, R1.8 | parsing: valid entry; bad `name`/`from`; unset source; daemon-credential source warns; duplicate name; own identifier refused |
| T1 | R1.5 | source from the env file wins over `os.environ`; re-read per call |
| T1 | R1.7, A7 | scoped entry: matching GitHub ref inherits; other repo, Jira ref, empty ref do not, and the name stays removed |
| T1 | R1.9, A5 | `sessionPassthrough: [GH_TOKEN]` still refused with `sessionCredentials` set |
| T1 | R2.1, R2.2 | `remove` gains every `from` and un-inherited `name`; loses inherited names |
| T1 | R1.2 | no `sessionCredentials`: `SessionEnvironment` equal to today's; `_harness_command` and argv unchanged; no file written |
| T1 | R3.1, R3.2, A1 | runner argv contains the path and the constant loader, never the value |
| T1 | R3.2, A3 | file mode `0600`, dir `0700`, `O_EXCL`; a pre-placed symlink is refused; unwritable dir → no credentials, names removed, warning |
| T1 | R3.4 | spawn failure deletes the file; sweep removes files older than the bound and keeps fresh ones |
| T1 | R3.5, A2 | `_run`'s child environment excludes inherited names and the daemon's same-named token |
| T1 | R4.1, R4.3 | `compare()`: inherited name missing → differs; wrong value → differs; right value → clean; rendering shows fingerprint only |
| T1 | R5.1, R5.2, R5.3, A4 | `scrub`: masks values, longest first; picks up a rotated value; remembers a rotated-out one; no-op and no disk read when unconfigured; short values left alone with a warning |
| T1 | R5.1, A4 | each scrubbed route posts masked text (comments, ask, reply, tickets, PRs, force/skip); `EventLog.emit` writes masked strings |
| T1 | R7.1, R7.2 | drift row and `list_sessions` carry `credentials` (name → fingerprint); `status` line; `sessions list` column only when present; one warning event per spawn naming names, no value |
| T2 | R3.1–R3.6, R1.2 | `Scenario: a spawned session inherits an opted-in credential that no argv or tmux environment holds` |
| T2 | R4.1, R4.2 | `Scenario: rotating the source value marks the session stale` |
| T2 | R3.6 | `Scenario: a second session on the same server does not inherit the credential` |
| T10 | R1.2 | existing `test_session_secrets_integration.py`, `test_envstate.py`, `test_session_environment.py` unchanged and green |

## Verification environment

- **Repositories:** this repository only.
- **Services / containers:** none. T2 starts its own tmux server on a private
  `TMUX_TMPDIR` and kills it on teardown (the issue-482 fixture pattern).
- **Fixtures & data:** dummy credential values generated in the tests; `tmp_path` for
  `state.root` and the env file.
- **Credentials:** none real. Never a real token.
- **Requirements:** tmux ≥ 3.2 and Linux `/proc` for T2 (the test skips otherwise, and
  a skip is recorded as *not run*, not as a pass).
- **Bring-up:** `uv sync` · **Tear-down:** nothing (fixtures clean up).
- **If bring-up fails:** record it under Verification results, leave T2 unticked and
  escalate on the PR.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T8 | targeted test run output, pass counts | `verification.md` § Unit |
| T2 | integration run output (not skipped) | `verification.md` § Integration |
| T10 | full-suite summary + `make validate` | `verification.md` § Regression |
| T12 | lint / format / typecheck summaries | `verification.md` § Static checks |

## Verification activities

- [x] T1/T8 — `cd cli && uv run python -m pytest -q tests/test_envstate.py tests/test_tmux_runner.py tests/test_sessioncreds.py tests/test_session_environment.py tests/test_api_session_credentials.py`
- [x] T2 — `cd cli && uv run python -m pytest -q -rs tests/test_session_credentials_integration.py tests/test_session_secrets_integration.py` (no skips)
- [x] T10 — `make test` and `make validate`
- [x] T12 — `make lint format-check typecheck`

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1/T8 | targeted unit tests (five files) | pass — 235 passed | [`evidence/verification.md` § Unit](evidence/verification.md#unit-t1-t8) |
| T2 | real-tmux integration, `-rs` (no skips) | pass — 4 passed, 0 skipped | [`evidence/verification.md` § Integration](evidence/verification.md#integration-t2) |
| T10 | full suite (CI environment) + `make validate` | pass — 6867 passed; every config VALID | [`evidence/verification.md` § Regression](evidence/verification.md#regression-t10) |
| T12 | `make lint format-check typecheck` | pass — ruff, markdownlint, format, pyright clean | [`evidence/verification.md` § Static checks](evidence/verification.md#static-checks-t12) |
