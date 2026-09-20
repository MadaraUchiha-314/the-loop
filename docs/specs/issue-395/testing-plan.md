---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#395"
status: in-review            # draft | in-review | approved — tier 3: locked with design.md at the PR
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: the hosted ingress set follows the config

> Derived from [`bugfix.md`](bugfix.md) and [`design.md`](design.md). Planned at
> `test-planning`, results recorded at `verification` (below).

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `_wanted` composes the same list for boot and reconcile; `HostedIngresses.reconcile` stops what is no longer wanted and starts what is newly wanted, drops a dead entry, and leaves a same-membership change alone | `cd cli && uv run pytest tests/test_hosted_reconcile.py` |
| T2 | Integration (scenario, Gherkin-docstringed) | yes | a real config file, a supervisor with a short interval, the file rewritten: `read.mode: off` ends the listener's loop and releases its lock with no restart; `socket` again starts it with the **new** config; an unrelated edit and an unparseable edit change nothing; `polling.enabled: false` stops a hosted poller; shutdown stops the supervisor then the ingresses (R1.1–R1.6, R1.8) | `cd cli && uv run pytest tests/test_hosted_reconcile.py` |
| T3 | Contract (OpenAPI) | n/a — no API route or schema change; `status --format json` is unchanged (R2.2) | | |
| T4 | End-to-end (live) | no — the Socket Mode client is faked at the seam issue-334's tests fake; the live B5 reproduction is the next Slack run's | | |
| T5 | UI / visual | n/a | | |
| T6 | Snapshot | n/a — the `status` line is asserted directly (T7) | | |
| T7 | CLI rendering | yes | `the-loop status` prints the non-contradictory flag for a running-but-disabled row, hosted and standalone, and the plain flags otherwise (R2.1) | `cd cli && uv run pytest tests/test_lifecycle_cmd.py` |
| T8 | Security / abuse case | yes | an unparseable edit changes nothing (abuse 2); a reconcile whose starter raises records `ingress.hosted_failed` and the supervisor survives (abuse 3); the missing-token refusal on a reconcile start names the variable, not the value | with T2 |
| T9 | Accessibility | n/a | | |
| T10 | Migration / upgrade | n/a — no key, state or schema change; `build_lifespan`'s new argument has a default | | |
| T11 | Manual exploratory | no — deferred to the next live Slack run (B5's own steps) | | |
| T12 | Regression (full suite) | yes | the existing hosted-listener, hosted-ingress, lifecycle and SDK suites stay green: `start_hosted_ingresses` / `stop_hosted_ingresses` keep their contract | `cd cli && uv run pytest -q` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.2, R1.3 | `_wanted` for {nothing, poller, receiver, socket listener, poll-mode listener} equals what `start_hosted_ingresses` composes |
| T2 | R1.1, R1.4, R1.8 | `Scenario: read.mode goes from socket to off` — the listener's stop event is set, its thread ends, its lock is released, `ingress.hosted_stopped reason=config` and `config.reloaded` are emitted, the service process is still up (no restart) |
| T2 | R1.2, R1.4 | `Scenario: read.mode comes back to socket` — a second listener starts, under the same lock, with the **edited** config; `ingress.hosted` emitted |
| T2 | R1.3 | `Scenario: an unrelated key changes` — same thread object still alive; no ingress event |
| T2 | R1.5 | `Scenario: the edit is not valid YAML` — nothing changes; the next valid edit is applied |
| T2 | R1.1 | `Scenario: polling.enabled goes false` — the hosted poller's stop event is set and its lock released |
| T2 | R1.6 | `Scenario: shutdown` — `stop()` ends the supervisor thread before the ingresses; no ingress is started by a tick after `stop()` returns |
| T2 | R1.2, T8 | `Scenario: the newly wanted listener has no tokens` — `ingress.hosted_failed` names the variable; the supervisor keeps ticking |
| T7 | R2.1 | hosted + running + disabled → `disabled in config — still running; the service stops it on its next config check`; standalone → `\`the-loop stop\` ends it`; enabled rows unchanged |
| T12 | R1.7, all | the whole suite |

## Verification environment

- **Repositories:** this repo only.
- **Services / containers:** none; the Socket Mode client and the poller's run loop are
  faked at their seams, and the supervisor runs in-process on `tmp_path`.
- **Fixtures & data:** a `cli-config.yaml` written per test under `tmp_path`.
- **Credentials:** by reference only — `THE_LOOP_SLACK_BOT_TOKEN`,
  `THE_LOOP_SLACK_APP_TOKEN`, set to placeholder strings by `monkeypatch`.
- **Bring-up:** `uv sync` · **Tear-down:** none.
- **If bring-up fails:** record under Verification results, leave the rows unticked.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T7, T8 | test names and run output, red → green noted | `automated-tests.md` |
| T12 | full-suite, lint, format, typecheck output | `automated-tests.md` |

## Verification activities

- [x] T1 + T2 + T8 — `cd cli && uv run pytest -q tests/test_hosted_reconcile.py`
- [x] T7 — `cd cli && uv run pytest -q tests/test_lifecycle_cmd.py`
- [x] T12 — `cd cli && uv run pytest -q` · `uv run ruff check cli hooks` · `uv run ruff format --check cli hooks` · `uv run pyright cli`

## Verification results

Recorded in [`evidence/automated-tests.md`](evidence/automated-tests.md).

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 + T2 + T8 | `cd cli && uv run pytest -q tests/test_hosted_reconcile.py tests/test_hosted_listener.py` | see evidence | `evidence/automated-tests.md` |
| T7 | `cd cli && uv run pytest -q tests/test_lifecycle_cmd.py` | see evidence | `evidence/automated-tests.md` |
| T12 | `cd cli && uv run pytest -q` · ruff · pyright | see evidence | `evidence/automated-tests.md` |

## Review comments

*None yet.*
