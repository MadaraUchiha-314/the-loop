---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#422"
---

# Verification: the suite writes into the checked-in `.the-loop/` when run from the repo root

> The `verification` node's captured output, one section per row of
> [`testing-plan.md`](../testing-plan.md). Environment: Python 3.11, `uv` 0.12.17,
> `uv sync --all-packages` against the committed `uv.lock`, no `~/.the-loop/`.

## Results

| Row | Command | Outcome |
|-----|---------|---------|
| T1 | `uv run --project cli python -m pytest -q cli` (repo root), then both trees' status | 4528 passed, 1 skipped; both trees untouched, tracked and ignored |
| T2 | `cd cli && uv run python -m pytest -q`, then both trees' status | 4528 passed, 1 skipped; both trees untouched; `cli/.the-loop/` not created |
| T3 | final `conftest.py` over the **unfixed** tests and runtime code | 74 passed, **7 errors**: exactly the four writers, each naming its path |
| T4 | `tests/test_state_isolation.py` | 11 passed, from both directories |
| T5 | the four fixed modules + `test_channels_dm*.py` | green (inside T1/T2; 120 passed when run alone) |
| T6 | `make lint format-check typecheck validate` | green: ruff, markdownlint (0 errors), pyright (0 errors), configs valid |
| T7 | full suite from `cli/`, without then with the hook, back to back | 185.05s without, 180.81s with: no measurable cost |
| T15 | `sitecustomize` tracer over a root run | three of the four writers (it did not wrap `mkdir`), all in the test process, none in a child |
| AC3 | `git ls-files .the-loop/portable` | empty |

## How the writers were found (T15)

A `sitecustomize.py` on `PYTHONPATH` wrapped `builtins.open`, `io.open`, `os.open`,
`os.replace` and `tempfile.mkstemp`. For every write under either `.the-loop/`, it logged
the `PYTEST_CURRENT_TEST`, the pid and argv, and the stack. Because it is loaded by
`PYTHONPATH`, every child that inherits the test's environment loads it too. Run on
`main` from the root, every logged write was in the pytest process itself, grouped as:

```text
1 test=tests/test_api_health_integration.py::test_a_hosted_loop_that_ends_on_its_own_drops_its_lock_and_says_so (call) os.open /home/user/the-loop/.the-loop/poll.pid
2 test=tests/test_graph_drive_integration.py::test_the_spawning_event_reaches_the_graph (call) mkstemp .the-loop/portable
2 test=tests/test_graph_drive_integration.py::test_the_spawning_event_reaches_the_graph (call) os.open /home/user/the-loop/.the-loop/portable/TMP
1 test=tests/test_graph_drive_integration.py::test_the_spawning_event_reaches_the_graph (call) replace .the-loop/portable/github-octo-repo-15.json
1 test=tests/test_graph_drive_integration.py::test_the_spawning_event_reaches_the_graph (call) replace .the-loop/portable/index.json
2 test=tests/test_sessions_restart_integration.py::…[failed] (call) open .the-loop/logs/events.jsonl
2 test=tests/test_sessions_restart_integration.py::…[fresh] (call) open .the-loop/logs/events.jsonl
2 test=tests/test_sessions_restart_integration.py::…[stale] (call) open .the-loop/logs/events.jsonl
2 test=tests/test_sessions_restart_integration.py::…[unverified] (call) open .the-loop/logs/events.jsonl
```

The tracked record's stack, trimmed to the-loop's frames:

```text
File "cli/tests/test_graph_drive_integration.py", line 284, in test_the_spawning_event_reaches_the_graph
  dispatcher.handle(routed)
File "cli/the_loop/webhook/dispatcher.py", line 1152, in handle
  self._apply_control(control.command, routed)
File "cli/the_loop/webhook/dispatcher.py", line 2261, in record
  self.control_store.record(
File "cli/the_loop/control.py", line 636, in record
  self.store.write_section(item, CONTROL, record.to_dict())
File "cli/the_loop/workitem.py", line 398, in _write_json
  fd, tmp_name = tempfile.mkstemp(dir=str(self.root), suffix=".tmp")
```

Every write is in a test's `(call)` phase. None is at session end, which settles the
ticket's shutdown hypothesis. The tracer did not wrap `os.mkdir`, so it missed the
fourth writer (`test_doctor_slack`, which creates `local/`). The guard's first run
(T3) found it.

## T3: negative control

The final `cli/tests/conftest.py` was copied into a clean worktree of `main` (`a754cea`),
with the tests and runtime code unfixed, and the four modules were run from its root:

```console
$ python -m pytest -q cli/tests/test_api_health_integration.py cli/tests/test_doctor_slack.py \
    cli/tests/test_graph_drive_integration.py cli/tests/test_sessions_restart_integration.py
wrote into a protected `.the-loop/` state tree — give the code under test a state root under tmp_path (issue-422):
os.mkdir <worktree>/.the-loop
open <worktree>/.the-loop/poll.pid
os.remove <worktree>/.the-loop/poll.pid
wrote into a protected `.the-loop/` state tree — …
os.mkdir .the-loop/local
open <worktree>/.the-loop/local/tmpu_ki4v0g.tmp
os.rename .the-loop/local/slack-directory.json
wrote into a protected `.the-loop/` state tree — …
os.mkdir .the-loop/portable
os.rename .the-loop/portable/github-octo-repo-15.json
os.rename .the-loop/portable/index.json
wrote into a protected `.the-loop/` state tree — …   (×4, one per restart case)
os.mkdir .the-loop/logs
open .the-loop/logs/events.jsonl
ERROR cli/tests/test_api_health_integration.py::test_a_hosted_loop_that_ends_on_its_own_drops_its_lock_and_says_so
ERROR cli/tests/test_doctor_slack.py::test_doctor_slack_prints_all_three_sections_and_exits_zero_when_clean
ERROR cli/tests/test_graph_drive_integration.py::test_the_spawning_event_reaches_the_graph
ERROR cli/tests/test_sessions_restart_integration.py::TestSecretsAreNeverPrinted::test_no_declared_value_reaches_any_output_on_any_path[fresh]
ERROR cli/tests/test_sessions_restart_integration.py::TestSecretsAreNeverPrinted::test_no_declared_value_reaches_any_output_on_any_path[stale]
ERROR cli/tests/test_sessions_restart_integration.py::TestSecretsAreNeverPrinted::test_no_declared_value_reaches_any_output_on_any_path[unverified]
ERROR cli/tests/test_sessions_restart_integration.py::TestSecretsAreNeverPrinted::test_no_declared_value_reaches_any_output_on_any_path[failed]
74 passed, 7 errors in 3.80s
```

The same four tests, the same seven cases, went red in the full-suite run from the
repository root on this checkout before task A2 (`4517 passed, 1 skipped, 7 errors`).

## T1 and T2: both working directories, after the fix

At `06e06e6`:

```console
## T1 root
$ git status --porcelain --ignored .the-loop cli/.the-loop
$ uv run --project cli python -m pytest -q cli
4528 passed, 1 skipped in 200.83s (0:03:20)
$ git status --porcelain --ignored .the-loop cli/.the-loop
$ git status --porcelain
## T2 cli/
$ cd cli && uv run python -m pytest -q
4528 passed, 1 skipped in 177.61s (0:02:57)
$ git status --porcelain --ignored .the-loop cli/.the-loop
$ git status --porcelain
$ git ls-files .the-loop/portable
```

Every status is empty, `--ignored` included, so neither the tracked records nor the
ignored `local/`, `logs/` and `poll.pid` were written. On `main`, the same root run
reports the record modified (`M`) and `.the-loop/local/` and `.the-loop/logs/` as
ignored (`!!`).

## T4: the guard's own tests

```console
$ cd cli && uv run python -m pytest -q tests/test_state_isolation.py
11 passed
```

Two of these were written red first, during self-review, and fixed in the hook:

```text
E  AssertionError: assert [('os.symlink', '.the-loop')] == []
E  AssertionError: assert [('os.rmdir', … '.the-loop')] == []
```

## T7: cost

The same machine, one run after the other, from `cli/`. The first run used a clean
worktree of `main`, whose `conftest.py` has no hook. The second used this branch.

```text
4517 passed, 1 skipped in 185.05s (0:03:05)   # main, no hook
4528 passed, 1 skipped in 180.81s (0:03:00)   # this branch, hook installed (+11 guard tests)
```

The difference is within run-to-run noise. T1 and T2 above (200.83s, 177.61s) show the
same spread between directories.

## T12: the restored abuse case

`test_no_declared_value_reaches_any_output_on_any_path` now asserts
`(tmp_path / "events.jsonl").read_text()` is non-empty before searching it. All four
cases pass, so the search covers a real log and finds no declared value in it.
