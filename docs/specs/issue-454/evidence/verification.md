---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#454"
---

# Verification (issue-454)

Executed at the `verification` node on 2026-10-02, on branch
`claude/github-issue-454-hfdzoc`, in the work item's Linux cloud checkout: `uv 0.12.22`,
Python 3.11, no network for the tests. Commands run from `cli/`. `$S` is the session
scratchpad, which holds the host conditions:

- `$S/harn`: stub `claude`, `codex`, `cursor-agent`, `aider`, `ttyd`, `gemini`, each
  `#!/bin/sh` + `exit 0`.
- `$S/notmux`: symlinks to every `/usr/bin` binary except `tmux`.
- `$S/tmpalias`: a symlink to `$S/realtmp`. It is the shape of macOS's `/var` →
  `/private/var`.

## T6 — red: the original tests under the host matrix

The five modules at `HEAD` (`f562221`), copied with `git show HEAD:cli/tests/<m>.py`, under
all three conditions at once:

```text
$ TMPDIR=$S/tmpalias PATH=$S/harn:.venv/bin:$S/notmux python -m pytest -q tests/*_old454.py
FAILED tests/test_core_repo_old454.py::test_critics_lists_the_cli_configs_entries_without_argv
FAILED tests/test_critics_old454.py::test_list_reports_availability - assert ...
FAILED tests/test_harness_gate_old454.py::TestAttemptsFile::test_a_work_item_with_slashes_does_not_escape_the_temp_dir
FAILED tests/test_hosted_ingress_integration_old454.py::test_start_hosts_everything_in_one_process_and_stop_ends_it
FAILED tests/test_poll_daemon_integration_old454.py::test_start_detaches_a_poller_that_owns_its_pidfile_and_log
FAILED tests/test_poll_daemon_integration_old454.py::test_a_started_poller_outlives_the_shell_that_started_it
FAILED tests/test_poll_daemon_integration_old454.py::test_start_is_idempotent_while_the_poller_runs
FAILED tests/test_poll_daemon_integration_old454.py::test_a_stale_pidfile_is_removed_by_the_next_start
FAILED tests/test_poll_daemon_integration_old454.py::test_stop_signals_the_poller_and_waits_for_it_to_exit
FAILED tests/test_poll_daemon_integration_old454.py::test_status_reports_a_running_poller_its_pid_and_its_last_cycle
FAILED tests/test_poll_daemon_integration_old454.py::test_the_poller_polls_the_top_level_declared_repositories
11 failed, 99 passed in 115.37s
```

These are three of the ticket's four failures, reproduced on Linux, plus the eight
tmux-preflight failures. The fourth, `ps sess=0`, is BSD-only. T4 covers it. The poller's
log on a no-tmux host names the cause:

```text
ERROR the-loop.poll missing dependency: tmux — install it (macOS: `brew install tmux` · Debian/Ubuntu: `apt install tmux` · Fedora: `dnf install tmux`)
```

Earlier, the stub-harness condition alone was run over the **whole** suite on the
original tests. It failed only the two critic tests, so no other test depends on which
harness CLIs are installed:

```text
$ PATH=$S/harn:$PATH python -m pytest -q
FAILED tests/test_core_repo.py::test_critics_lists_the_cli_configs_entries_without_argv
FAILED tests/test_critics.py::test_list_reports_availability - assert True is...
2 failed, 5294 passed, 1 skipped, 1 warning in 228.20s
```

A recording `tmux` (it appends its argv to a file) was put first on PATH for the two daemon
modules. All 11 tests passed and the file was never created, so **no test there runs
tmux**:

```text
$ PATH=$S/rec:.venv/bin:$S/notmux python -m pytest -q tests/test_poll_daemon_integration.py tests/test_hosted_ingress_integration.py
11 passed in 38.73s
$ sort $S/rec/calls.log
sort: cannot read: …/rec/calls.log: No such file or directory
```

Outcome: **pass** (the red reproduces the ticket).

## T1–T3, T7 — green: the full suite under the host matrix

```text
$ TMPDIR=$S/tmpalias PATH=$S/harn:.venv/bin:$S/notmux python -m pytest -q -rfEs
SKIPPED [1] tests/test_instructions.py:149: root reads unpermitted files anyway
5301 passed, 1 skipped, 2 warnings in 229.99s
```

The one skip is pre-existing and unrelated: the container runs as root. No new skip.

An earlier run of the same command reported `1 failed, 5300 passed`. That run overlapped
the T6 red run, which was starting and killing poller daemons on the same host at the same
time. The `-rs` flag it was run with hid the failure's name, so the test is not known.
The re-run above, and T8's run, were each the only suite on the host, and both are clean.

Outcome: **pass**.

## T2 — mutation: the escape check still catches an escape

`attempts_path` was temporarily changed to embed the raw work-item id
(`f"the-loop-gate-{digest}-{work_item}"`), then restored (no diff left in `hooks/`):

```text
$ python -m pytest -q tests/test_harness_gate.py -k "escape or symlink"
FAILED …::test_a_work_item_with_slashes_does_not_escape_the_temp_dir[../../etc/passwd]
FAILED …::test_a_work_item_with_slashes_does_not_escape_the_temp_dir[github:o/r#1]
FAILED …::test_a_work_item_with_slashes_does_not_escape_the_temp_dir[/etc/passwd]
FAILED …::test_a_work_item_with_slashes_does_not_escape_the_temp_dir[a/../../b]
FAILED …::test_containment_holds_when_the_temp_dir_is_a_symlink
5 failed, 34 deselected in 4.61s
```

Outcome: **pass**.

## T4 — `_stat()` without `/proc` (the macOS branch)

A scratch script imported the test module and ran `_stat()` twice per child: once
normally (`/proc`) and once with `Path.is_file` returning false for `/proc/…`, so `ppid`
came from `ps -o ppid=`. The children were an attached `sleep 30` and one started with
`start_new_session=True`. The last column is the detachment assertion,
`sid == pgid != getpgid(0)`:

```text
attached {'ppid': 10486, 'pgid': 10486, 'sid': 10484} {'ppid': 10486, 'pgid': 10486, 'sid': 10484} same NOT own-session
detached {'ppid': 10486, 'pgid': 10488, 'sid': 10488} {'ppid': 10486, 'pgid': 10488, 'sid': 10488} same own-session
```

Both branches agree. The assertion rejects the attached child and accepts the detached
one, so it still discriminates. Outcome: **pass**.

## T5 — the tmux tripwire

A scratch test module, deleted afterwards. One test runs `tmux ls` through the stub; the
other only resolves it:

```text
_____________________ ERROR at teardown of test_runs_tmux ______________________
E       AssertionError: a preflight-only test ran tmux: ls
tests/conftest.py:587: AssertionError
2 passed, 1 error in 0.09s
```

Outcome: **pass**.

## T8 — `make test`'s command on the host as it is

This host has tmux at `/usr/bin/tmux` and `claude` at `/opt/node22/bin/claude`.

```text
$ cd cli && uv run python -m pytest -q -rfEs
SKIPPED [1] tests/test_instructions.py:149: root reads unpermitted files anyway
5301 passed, 1 skipped, 3 warnings in 220.46s
```

Outcome: **pass**.

## T9 — static checks

```text
$ uv run ruff check cli hooks
All checks passed!
$ uv run ruff format --check cli hooks
407 files already formatted
$ uv run pyright cli
0 errors, 0 warnings, 0 informations
$ npx --yes markdownlint-cli2@0.18.1 "docs/specs/issue-454/**/*.md" docs/capabilities/testing-and-contracts.md
Summary: 0 error(s)
```

Outcome: **pass**.

## T10 — macOS host

**Not run.** There is no macOS host in this checkout. Each macOS cause is reproduced on
Linux instead: the alias by T2's symlink case and T6, `ps sess` by T4, and an installed
Cursor CLI and an absent tmux by T6 and T7. A run on the operator's Mac, the ticket's
original environment, is the remaining confirmation. It is listed in the reviewer
briefing.

## Results

| Row | Command | Outcome | Artifact |
|-----|---------|---------|----------|
| T1 | critic tests, host matrix | pass | § T1–T3, T7 |
| T2 | containment + symlink + mutation | pass | § T2 |
| T3 | daemon tests, host matrix | pass | § T1–T3, T7 |
| T4 | `_stat` without `/proc` | pass | § T4 |
| T5 | tripwire | pass | § T5 |
| T6 | old tests, host matrix | pass (red reproduced) | § T6 |
| T7 | full suite, host matrix | pass | § T1–T3, T7 |
| T8 | `make test` command | pass | § T8 |
| T9 | ruff, pyright, markdownlint | pass | § T9 |
| T10 | macOS host | not run (no host) | § T10 |
