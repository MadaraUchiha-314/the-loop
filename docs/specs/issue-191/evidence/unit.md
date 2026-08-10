# Evidence — unit rows (T1–T5, T14)

Rows T1–T5 of [`testing-plan.md`](../testing-plan.md), each run as its own command so a
row's outcome is attributable. T14 (a poller with no heartbeat) has no suite of its own —
it is a case inside T2, named in the run below.

Nothing captured here contains a credential, a hostname or personal data: these tests
touch only temporary directories, and the poller holds no token.

## T1 — heartbeat (`cli/tests/test_poll_heartbeat.py`)

```text
$ uv run --project cli python -m pytest -q cli/tests/test_poll_heartbeat.py
........                                                                 [100%]
8 passed in 0.04s
```

Covers the round-trip, a started-but-not-cycled poller, `startedAt` staying put across
cycles, error counting and interruption, atomic replacement leaving no `.tmp` behind, an
absent/corrupt/wrong-shaped file reading as `None`, and — the one that matters for
ingress — an unwritable path warning **once** and never raising.

## T2 — `poll status` (`cli/tests/test_poll_status.py`)

```text
$ uv run --project cli python -m pytest -q cli/tests/test_poll_status.py
..........                                                               [100%]
10 passed in 0.52s
```

Includes the two abuse cases of row T7 and the migration case of row T14:

| Test | What it pins |
|---|---|
| `test_a_forged_heartbeat_cannot_make_a_dead_poller_look_alive` | liveness is the lock; a heartbeat with no poller behind it reads *not running*, exit `1` |
| `test_a_stale_pidfile_is_reported_and_left_alone` | a stale pidfile is named, and **not** deleted by a read-only command |
| `test_heartbeat_absent_still_reports_liveness` | a poller from before the heartbeat existed still reports running and its pid (R4.8 / T14) |

## T3 — argument wiring (`cli/tests/test_poll_command.py`)

```text
$ uv run --project cli python -m pytest -q cli/tests/test_poll_command.py
.................                                                        [100%]
17 passed in 0.76s
```

Ten pre-existing tests plus seven for this work item: `--daemon`/`--foreground`
last-one-wins, the three paths defaulting under `state.root`, `--daemon --once` exiting
`2`, the pre-fork refusals (lock held, logfile unopenable) both proving no fork happened,
a stale pidfile removed by the next start, the heartbeat written by a completed cycle, and
`daemon_entry` forcing foreground.

## T4 — state classification (`cli/tests/test_state_portability.py`)

```text
$ uv run --project cli python -m pytest -q cli/tests/test_state_portability.py
.......                                                                  [100%]
7 passed in 0.02s
```

The suite is unchanged; it now covers three more paths by construction. Before the
documentation and `.gitignore` were updated it failed exactly as designed — the run that
proved the gate works:

```text
FAILED test_every_generated_path_is_documented - AssertionError: poller pidfile
  (.the-loop/poll.pid) is missing from the classification table in docs/cli/state.md
FAILED test_block_ignores_exactly_the_local_paths - AssertionError: poller heartbeat
  (.the-loop/poll-status.json) is declared local but the documented .gitignore block
  tracks it
```

## T5 — control plane (`cli/tests/test_core_daemons.py`)

```text
$ uv run --project cli python -m pytest -q cli/tests/test_core_daemons.py
.......                                                                  [100%]
7 passed in 0.06s
```

`daemon_status("poller")` carries `startedAt`/`lastCycleAt` from the heartbeat and
`gh-webhook` carries them empty; `control_daemon("poller", "start")` opens the logfile
before spawning and passes the same fd as `stdout` and `stderr` — the `DEVNULL` that used
to discard a control-plane start's output is gone.
