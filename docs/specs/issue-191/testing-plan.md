---
type: testing-plan
phase: test-planning
workItem: issue-191
status: approved              # draft | in-review | approved
approvedBy: []                # pending — human gate on the PR (risk tier 3)
overrides: {}
---

# Testing plan: `poll start` runs as a proper daemon

> Derived from the approved [`requirements.md`](requirements.md) and
> [`design.md`](design.md), before [`tasks.md`](tasks.md). Ticket:
> [#191](https://github.com/MadaraUchiha-314/the-loop/issues/191).

**The one thing this plan must not fake is the fork.** Every other change here — the
heartbeat, the status rendering, the argument wiring — is ordinary unit-testable code, and
mocking `os.fork` would prove only that we called it. So the detach requirements (R1, R3)
are proved by spawning a real `poll start --daemon` as a subprocess and interrogating the
running system: its ppid, its session id, its lock, its log. Everything else is a unit
test.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit — heartbeat | yes | `PollHeartbeat.record`/`read` round-trip, atomic replace, unreadable/absent → `None`, write failure warns once and does not raise (R5.4) | `uv run --project cli python -m pytest -q cli/tests/test_poll_heartbeat.py` |
| T2 | Unit — `poll status` | yes | text and JSON rendering for running / not-running / stale-pidfile / no-cycle-yet; exit codes 0 and 1 (R4.1–R4.6) | `uv run --project cli python -m pytest -q cli/tests/test_poll_status.py` |
| T3 | Unit — argument wiring | yes | `--daemon`/`--foreground` last-one-wins, `--logfile` default from `state.root`, `--daemon --once` refused, `daemon_entry` forces foreground (R1.3–R1.5, R2.2) | `uv run --project cli python -m pytest -q cli/tests/test_poll_command.py` |
| T4 | Unit — state classification | yes | the three new `StateLayout` paths are declared, documented and ignored (R5.1–R5.3) — the existing portability suite, extended by construction | `uv run --project cli python -m pytest -q cli/tests/test_state_portability.py` |
| T5 | Unit — control plane | yes | `daemon_status` carries `startedAt`/`lastCycleAt`; `control_daemon("start")` redirects to the logfile rather than `DEVNULL` (R2.5, R4.7) | `uv run --project cli python -m pytest -q cli/tests/test_core_daemons.py` |
| T6 | Integration (scenario) | yes | a real detached poller: reparenting, session, pidfile-under-lock, logfile, survival of its starter's teardown, refusal when held, failure reported to the caller (R1.1, R1.2, R2.1, R3.1, R3.3–R3.5) | `uv run --project cli python -m pytest -q cli/tests/test_poll_daemon_integration.py` |
| T7 | Security / abuse case | yes | a forged heartbeat with no poller running is reported *not running* (exit 1); a planted stale pidfile is reported and removed by `start`, never signalled | in T2 and T6 (rows marked in the trace below) |
| T8 | Contract (OpenAPI / GraphQL SDL) | n/a — the `GET /api/v1/daemons` response is declared as an untyped object map; two added keys change no contract. The existing `test_api_contract_parity.py` still runs and would catch it if that were wrong. | | |
| T9 | End-to-end | n/a — an end-to-end run of the poller means a live GitHub repository and a real harness spawn. This work item changes *how the process is started*, not what a cycle does; T6 exercises the real process boundary, which is the part that could not be covered by anything smaller. | | |
| T10 | UI / visual | n/a — no user-facing surface; the-loop's CLI has no UI artifacts (`design.uiArtifacts` is empty for backend/CLI work). | | |
| T11 | Snapshot | n/a — the only rendered output is `poll status`, asserted field-by-field in T2. A snapshot would pin whitespace and make a wording fix a red build. | | |
| T12 | Performance / load | n/a — one extra `os.replace` of a <1 KB file per poll cycle, against a default interval of 60 s. There is no load dimension to measure. | | |
| T13 | Accessibility | n/a — no user interface. | | |
| T14 | Migration / upgrade | yes | a poller started by a *previous* version leaves no `poll-status.json`; `poll status` must still report liveness and pid (R4.8). Covered as a case in T2 (heartbeat absent) — no data migration exists to run. | with T2 |
| T15 | Manual exploratory | n/a — the operator-visible behaviour (detach, log, status) is exactly what T6 asserts against a real process. A human repeating it by hand would add no signal the assertions do not carry. | | |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R5.4 | round-trip; `record` after each cycle overwrites atomically; unwritable path warns once, never raises |
| T2 | R4.1, R4.2, R4.3 | a held lock renders `running (pid N)` and exits `0`; no lock renders `not running` and exits `1` |
| T2 | R4.4, **T7** | a pidfile nobody holds renders `stale — pid N is not running`, and is left on disk by `status` |
| T2 | R4.5, R4.6 | a recorded cycle renders its timestamp, its age and its counters; no heartbeat renders `no cycle recorded yet` |
| T2 | R4.7 | `--format json` carries the same facts as one object |
| T2 | R4.8, **T7**, T14 | a heartbeat present with **no** poller running still reports `not running` and exits `1` — liveness is the lock, never the file |
| T3 | R1.3, R1.4 | `--foreground` after `--daemon` leaves `daemon` false, and the reverse leaves it true |
| T3 | R1.5 | `--daemon --once` exits `2` naming the conflict |
| T3 | R2.2 | `--logfile` defaults to `<state.root>/logs/poller.out` |
| T3 | R2.5 | `daemon_entry`'s namespace has `daemon` false regardless of the flag's default |
| T4 | R5.1, R5.2, R5.3 | every new `StateLayout` path is classified, documented `local`, and ignored by the published block |
| T5 | R2.5 | `control_daemon("poller", "start")` passes an appendable logfile, not `DEVNULL` |
| T5 | R4.7 | `daemon_status("poller")` carries `startedAt` and `lastCycleAt`; `gh-webhook` carries them as `None` |
| T6 | R1.1, R1.2 | `Scenario: A daemonized poller outlives the shell that started it` |
| T6 | R2.1, R3.1 | `Scenario: A daemonized poller owns its pidfile and its logfile` |
| T6 | R3.3, **T7** | `Scenario: A daemonized start refuses when a poller already holds the lock` |
| T6 | R3.4 | `Scenario: A daemonized start reports a startup failure to its caller` |
| T6 | R3.2 | `Scenario: A stale pidfile is removed by the next start` |
| T6 | R4.1, R4.5 | `Scenario: poll status reports a running poller, its pid and its last cycle` |

## Verification environment

- **Repositories:** this repository only.
- **Services / containers:** none. The integration tests configure a `polling.sources`
  entry whose provider dependency check is satisfied by a stub `gh` on `PATH`, so no
  network call is made and no real repository is polled.
- **Fixtures & data:** a temporary `state.root` per test (`tmp_path`), a CLI config
  written into it, and a fake `gh` script that exits `0`. tmux is **not** required: the
  tests exercise the start path with routing disabled, so no session is spawned.
- **Credentials:** none. The poller holds no token; nothing in this plan reads one.
- **Bring-up:** `make install-dev` · **Tear-down:** none (temp dirs; each test kills the
  daemon it spawned in a `finally`).
- **Platform:** POSIX. The detach tests are skipped where `os.fork` is unavailable, the
  same way `RunLock` already degrades without `flock`. CI runs Linux.
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1–T5, T14 | unit run output (counts, duration) | `unit.md` |
| T6, T7 | scenario table + run output, plus the observed ppid/sid/lock/log facts | `integration.md` |
| all | `make check` — lint, format, typecheck, config validation, full suite | `check.md` |

No screenshots: there is no visual surface. Nothing captured here contains a token, a
hostname or personal data — the daemon holds no credential and the tests never reach the
network — but the captures are read before committing all the same.

## Verification activities

- [x] T1 — `uv run --project cli python -m pytest -q cli/tests/test_poll_heartbeat.py`
- [x] T2 — `uv run --project cli python -m pytest -q cli/tests/test_poll_status.py`
- [x] T3 — `uv run --project cli python -m pytest -q cli/tests/test_poll_command.py`
- [x] T4 — `uv run --project cli python -m pytest -q cli/tests/test_state_portability.py`
- [x] T5 — `uv run --project cli python -m pytest -q cli/tests/test_core_daemons.py`
- [x] T6 — `uv run --project cli python -m pytest -q cli/tests/test_poll_daemon_integration.py`
- [x] T7 — the abuse-case rows above, run as part of T2 and T6
- [x] T14 — the heartbeat-absent case, run as part of T2
- [x] all — `make check`

## Verification results

Every row marked `yes` ran. The one thing worth reading beyond the counts is the manual
walkthrough in [`evidence/integration.md`](evidence/integration.md): one line of `ps`
carries the whole ticket — `ppid 1`, a session of its own, and no controlling terminal.

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | `pytest -q cli/tests/test_poll_heartbeat.py` | pass — 8 tests | [`evidence/unit.md`](evidence/unit.md) |
| T2, T14 | `pytest -q cli/tests/test_poll_status.py` | pass — 10 tests, including both T7 abuse cases and the heartbeat-absent case | [`evidence/unit.md`](evidence/unit.md) |
| T3 | `pytest -q cli/tests/test_poll_command.py` | pass — 17 tests (10 pre-existing, 7 new) | [`evidence/unit.md`](evidence/unit.md) |
| T4 | `pytest -q cli/tests/test_state_portability.py` | pass — 7 tests, now covering three more paths; it failed first, exactly as designed, until the docs and `.gitignore` caught up | [`evidence/unit.md`](evidence/unit.md) |
| T5 | `pytest -q cli/tests/test_core_daemons.py` | pass — 7 tests | [`evidence/unit.md`](evidence/unit.md) |
| T6, T7 | `pytest -v cli/tests/test_poll_daemon_integration.py` | pass — 7 scenarios against real detached processes | [`evidence/integration.md`](evidence/integration.md) |
| T6 (manual) | `poll start --daemon` → `ps` → `status` → second start → `stop` → `status` → `--daemon --once` | pass — ppid 1, own session, no tty; exit `0`/`1` from `status`; the refusals as specified | [`evidence/integration.md`](evidence/integration.md) |
| all | `make check` | pass — lint (511 markdown files), format, pyright, config validation, **1686 passed / 1 skipped** (baseline 1650) | [`evidence/check.md`](evidence/check.md) |

**Not executed:** none. Every row marked `yes` ran; every row marked `n/a` carries its
reason in the matrix.

## Review comments

<!-- Appended by the-loop's record-feedback hook when a human gate approves with comments. -->
