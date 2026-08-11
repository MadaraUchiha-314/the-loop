# Verification evidence — issue-205

Executed on 2026-08-11 against
[`claude/github-issue-205-jn4vq8`](https://github.com/MadaraUchiha-314/the-loop/tree/claude/github-issue-205-jn4vq8),
one section per row of [`requirements.md`](../requirements.md) § Testing.

## T1 — the heartbeat records no pid

```console
$ uv run --project cli python -m pytest -q cli/tests/test_poll_heartbeat.py -k pid
...                                                                      [100%]
3 passed, 8 deselected in 0.07s
```

Three tests match `-k pid`: `test_the_heartbeat_records_no_pid` (the document has exactly
`startedAt`, `lastCycleAt`, `intervalSeconds`, `lastCycle`, and `Heartbeat` has no `pid`
attribute), plus T2's and T3's, quoted separately below.

## T2 — why the two files cannot be one (the measurement)

```console
$ uv run --project cli python -m pytest -q cli/tests/test_poll_heartbeat.py -k pidfile
.                                                                        [100%]
1 passed, 10 deselected in 0.32s
```

`test_writing_a_heartbeat_over_the_pidfile_would_free_the_lock` performs exactly what
`PollHeartbeat._write` does — `tempfile` + `os.replace` — over a held `RunLock`, and
asserts the lock is then free to a second process. The same run, instrumented by hand to
print the inode:

```text
lock held: True inode: 1884214
before atomic rewrite -> another process sees it held: True
after atomic rewrite  -> another process sees it held: False inode: 1884215
```

The lock survives on the inode the daemon opened (`1884214`); the path now names
`1884215`, which nobody holds. Merged, the poller would free its own lock on its first
cycle.

## T3 — a pre-change heartbeat still reads

```console
$ uv run --project cli python -m pytest -q cli/tests/test_poll_heartbeat.py -k older
.                                                                        [100%]
1 passed, 10 deselected in 0.45s
```

## T4 — `poll status` unchanged, over a heartbeat that carries no pid

```console
$ uv run --project cli python -m pytest -q cli/tests/test_poll_status.py
...........                                                              [100%]
11 passed in 0.23s
```

Includes the new `test_a_pid_left_in_an_older_heartbeat_is_never_reported`, which plants
`os.getpid()` — a **live** pid — in the heartbeat with no pidfile present, and asserts the
report carries `pid: 0` and `recordedPid: 0` while still using the heartbeat's progress
facts.

## T5 — poller, daemon and control-plane regressions

```console
$ uv run --project cli python -m pytest -q cli/tests/test_poll_daemon_integration.py \
    cli/tests/test_core_daemons.py cli/tests/test_poller_integration.py
...............................                                          [100%]
31 passed in 13.42s
```

## T6 — the whole suite

```console
$ make test
........................................................................ [ 99%]
.                                                                        [100%]
1800 passed, 1 skipped in 94.94s (0:01:34)
```

## T7 — repository gates

```console
$ make lint format-check typecheck validate
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Linting: 562 file(s)
Summary: 0 error(s)
uv run ruff format --check cli hooks
189 files already formatted
uv run pyright cli
0 errors, 0 warnings, 0 informations
uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```

`validate` includes the docs↔CLI parity check, which is what proves `docs/cli/state.md`
and `the_loop.state.GENERATED_PATHS` still agree after both descriptions of the heartbeat
changed.
