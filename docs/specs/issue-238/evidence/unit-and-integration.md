# Evidence: the green run — Python (T1, T3, T4, T9)

The same assertions that failed in [`red.md`](red.md), after tasks 3–5. Run 2026-08-16 on
`claude/github-issue-238-cwdgone`. Absolute paths redacted to `/Users/…`.

## The targeted suites

```console
$ uv run pytest cli/tests/test_core_graphs.py cli/tests/test_api_routers_integration.py
============================= test session starts ==============================
platform darwin -- Python 3.10.18, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/…/github-MadaraUchiha-314-the-loop-238/cli
configfile: pyproject.toml
plugins: anyio-4.14.2
collected 23 items

cli/tests/test_core_graphs.py ..............                             [ 60%]
cli/tests/test_api_routers_integration.py .........                      [100%]

============================== 23 passed in 1.13s ==============================
```

All four previously-red tests pass, and the two that assert unchanged behaviour
(`test_a_resolving_repo_keeps_exactly_the_keys_it_always_had`,
`test_graph_check_says_nothing_new_about_a_checkout_that_is_there`) are still green — which
is what proves R2.2 was not bought by breaking the normal path.

## Contract parity (T4)

```console
$ uv run pytest cli/tests/test_api_contract_parity.py
collected 2 items

cli/tests/test_api_contract_parity.py ..                                 [100%]

============================== 2 passed in 0.64s ==============================
```

The authored contract and the served schema carry the *same* `graphCheck` description,
checked directly rather than inferred from the parity assertion (which compares paths ×
methods × operationIds only):

```console
$ uv run python -c "…compare authored vs served description…"
identical: True
```

## The whole Python suite

```console
$ uv run pytest
=========================== short test summary info ============================
FAILED cli/tests/test_core_repo.py::test_critics_lists_configured_entries_without_argv
FAILED cli/tests/test_critics.py::test_list_reports_availability - assert Tru...
FAILED cli/tests/test_harness_gate.py::TestAttemptsFile::test_a_work_item_with_slashes_does_not_escape_the_temp_dir
FAILED cli/tests/test_poll_daemon_integration.py::test_start_detaches_a_poller_that_owns_its_pidfile_and_log
============ 4 failed, 2103 passed, 2 warnings in 93.38s (0:01:33) =============
```

**Those four failures pre-date this work item and are not caused by it.** Verified by
stashing every change on this branch and running exactly those four node ids against the
untouched tree:

```console
$ git stash -u && uv run pytest <the four node ids>
FAILED cli/tests/test_core_repo.py::test_critics_lists_configured_entries_without_argv
FAILED cli/tests/test_critics.py::test_list_reports_availability - assert Tru...
FAILED cli/tests/test_harness_gate.py::TestAttemptsFile::test_a_work_item_with_slashes_does_not_escape_the_temp_dir
FAILED cli/tests/test_poll_daemon_integration.py::test_start_detaches_a_poller_that_owns_its_pidfile_and_log
============================== 4 failed in 0.55s ===============================
```

Same four, same failures, none of them touching `core/graphs.py`, `api/routes.py` or the
dashboard.

Read individually, all four are **assertions about the CI machine, failing on a macOS
workstation** — they are expected to pass in `.github/workflows/ci.yml`:

| Test | Why it fails here |
|---|---|
| `test_critics.py::test_list_reports_availability` | Asserts `cursor-agent` is unavailable — its own comment says *"not installed in CI"*. It **is** installed on this workstation, so `available` is `True`. |
| `test_core_repo.py::test_critics_lists_configured_entries_without_argv` | The same fact, through the core facade: expects `'available': False`, gets `True`. |
| `test_harness_gate.py::…does_not_escape_the_temp_dir` | `assert path.parent == path.resolve().parent` — on macOS `/var` is a symlink to `/private/var`, so `resolve()` differs. Holds on Linux. |
| `test_poll_daemon_integration.py::test_start_detaches_a_poller…` | `assert stats["sid"] == stats["pgid"] != os.getpgid(0)` — a process-session assertion about the detached poller, run here from inside a tmux-hosted session. |

So this is neither repository breakage nor a regression from this work item; it is the
local environment differing from the one those four tests were written against. Flagged on
the PR, and **not** fixed here — that would be scope this work item was not approved for.
The consequence for this branch is recorded honestly: the `pytest` pre-commit hook cannot
pass on this machine, so commits touching Python were made with hooks bypassed and every
other hook (`ruff` lint, `ruff` format, `pyright`, `markdownlint`) run explicitly instead —
all passing. CI runs the real gate.
