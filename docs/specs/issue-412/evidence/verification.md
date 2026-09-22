---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#412"
---

# Verification: four `test_instance.py` tests read the machine they run on

> The `verification` node executing [`testing-plan.md`](../testing-plan.md). Every planned
> activity is ticked below with the exact command, the outcome and the output.

## Environment

- `uv` 0.12.17 — the version `.github/workflows/ci.yml` pins, inside the
  `required-version = ">=0.12,<0.13"` window `pyproject.toml` enforces. `uv sync --locked`
  succeeded, so the lockfile is current.
- Python 3.11; branch `claude/github-issue-412-ykupbw` on `6809ca6`.
- `~/.the-loop/cli-config.yaml` was created and removed between runs, as the ticket's
  reproduction does — a copy of this repository's own `.the-loop/cli-config.yaml`.

## Activities

- [x] **T1** — the four tests, all four environments (AC1)
- [x] **T2** — full suite from `cli/`, home config present (AC2)
- [x] **T3** — full suite from the repo root, home config present (AC2)
- [x] **T4** — `make test` vs the pre-commit hook; `make check` (AC2, AC3)
- [x] **T5** — negative control on the unfixed tree (AC1)
- [x] **T11** — the fixture reads and writes nothing outside `tmp_path` (AC1)
- [x] **T6–T10, T12–T14** — `n/a`/`no` with the reasons recorded in the plan; nothing to run

## Verification results

| Row | Command | Outcome | Evidence |
|-----|---------|---------|----------|
| T5 | `pytest tests/test_instance.py`, 4 environments, `test_instance.py` stashed | **reproduced**: 4 failed / 59 passed in 3 of 4 rows | § T5 below |
| T1 | same, with the fixture | **63 passed** in all 4 rows | § T1 below |
| T2 | `cd cli && uv run python -m pytest -q` | **4493 passed, 1 skipped** | § T2 below |
| T3 | `uv run --project cli python -m pytest -q cli` | **4493 passed, 1 skipped** | § T3 below |
| T4 | string comparison + `make check` | **identical**; `make check` green | § T4 below |
| T11 | review of the fixture body | no path outside `tmp_path`; file never created | [`security-review.md`](security-review.md) |

### T5 — negative control: the bug, on the unfixed tree

`cli/tests/test_instance.py` stashed so only the Makefile and docs differ from `main`:

```console
=== T5 NEGATIVE CONTROL: the four tests WITHOUT the fixture (i.e. main) ===
--- repo root, home config present ---
FAILED cli/tests/test_instance.py::test_an_unnamed_instance_spawns_with_the_argv_it_used_before
FAILED cli/tests/test_instance.py::test_a_spawn_for_a_work_item_exports_its_ref
FAILED cli/tests/test_instance.py::test_a_standing_session_carries_no_work_item
FAILED cli/tests/test_instance.py::test_only_the_configured_name_reaches_tmux_and_the_comment
4 failed, 59 passed in 0.27s
--- cli/, home config present ---
FAILED tests/test_instance.py::test_an_unnamed_instance_spawns_with_the_argv_it_used_before
FAILED tests/test_instance.py::test_a_spawn_for_a_work_item_exports_its_ref
FAILED tests/test_instance.py::test_a_standing_session_carries_no_work_item
FAILED tests/test_instance.py::test_only_the_configured_name_reaches_tmux_and_the_comment
4 failed, 59 passed in 0.70s
--- repo root, home config absent ---
FAILED cli/tests/test_instance.py::test_an_unnamed_instance_spawns_with_the_argv_it_used_before
FAILED cli/tests/test_instance.py::test_a_spawn_for_a_work_item_exports_its_ref
FAILED cli/tests/test_instance.py::test_a_standing_session_carries_no_work_item
FAILED cli/tests/test_instance.py::test_only_the_configured_name_reaches_tmux_and_the_comment
4 failed, 59 passed in 0.23s
--- cli/, home config absent ---
63 passed in 0.19s
```

This is the ticket's table, row for row: the four named tests, three red rows, and the one
green row that CI happens to occupy. The failing set is exactly the four, and the other 59
are unaffected — so the fault is the inherited export, not the module.

### T1 — the same four environments, with the fixture

```console
=== T1: the four tests WITH the fixture ===
--- repo root, home config present ---
63 passed in 0.25s
--- cli/, home config present ---
63 passed in 0.23s
--- repo root, home config absent ---
63 passed in 0.26s
--- cli/, home config absent ---
63 passed in 0.24s
```

**AC1 met**: the four tests pass regardless of the working directory pytest was started
from and regardless of whether the machine has a CLI config in either location.

### T2 — full suite from `cli/`, home config present

The command `make test` and CI's `pytest` hook both run, in the machine state that makes a
contributor's checkout red:

```console
### FULL SUITE from cli/, home config PRESENT (== make test == CI hook)
........................................................................ [ 91%]
........................................................................ [ 92%]
........................................................................ [ 94%]
........................................................................ [ 96%]
........................................................................ [ 97%]
........................................................................ [ 99%]
..............................                                           [100%]
4493 passed, 1 skipped in 228.54s (0:03:48)
```

The one skip is pre-existing and unrelated (it is present on `main`).

### The suite-wide variant, and why it was rejected

Recorded because it is the evidence behind the scope decision in
[`bugfix.md`](../bugfix.md) § Defect 1, not because it shipped. The identical fixture placed
in `cli/tests/conftest.py`, applying to every test, gives:

```console
FAILED tests/test_lifecycle_cmd.py::test_start_refuses_a_broken_config - Asse...
FAILED tests/test_poll_command.py::test_poller_launches_and_stops_ttyd_like_gh_webhook_start
FAILED tests/test_poll_command.py::test_poller_takes_the_lock_even_for_a_single_cycle
FAILED tests/test_poll_command.py::test_poller_recovers_from_a_pidfile_left_by_a_crash
FAILED tests/test_poll_command.py::test_default_options_resolve_under_the_state_root
FAILED tests/test_poll_status.py::test_a_held_lock_reports_running_and_exits_zero
FAILED tests/test_poll_status.py::test_a_forged_heartbeat_cannot_make_a_dead_poller_look_alive
FAILED tests/test_poll_status.py::test_the_last_cycle_is_reported_with_its_age_and_counters
FAILED tests/test_poll_status.py::test_a_started_poller_with_no_cycle_yet_says_so
FAILED tests/test_poll_status.py::test_heartbeat_absent_still_reports_liveness
FAILED tests/test_poll_status.py::test_json_carries_the_same_facts - Assertio...
FAILED tests/test_poll_status.py::test_a_degraded_scope_is_named_beneath_the_last_cycle
FAILED tests/test_poll_status.py::test_a_cycle_where_nothing_answered_says_so
FAILED tests/test_poll_status.py::test_json_carries_the_degraded_scopes - Key...
14 failed, 4479 passed, 1 skipped in 211.67s (0:03:31)
```

The mechanism, from the first failure's captured stdout:

```console
config      /tmp/pytest-of-root/pytest-7/cli-config-absent0/cli-config.yaml
state       /tmp/pytest-of-root/pytest-7/cli-config-absent0/.the-loop
```

The **state root is anchored on the config path's parent** (`state.py`'s
`layout_from_config`, issue-339), and `test_poll_status.py`'s `paths` fixture chdirs into
its own `tmp_path` and writes a real `./.the-loop/cli-config.yaml` there. Pinning the
variable moved the state root away from the pidfile and heartbeat the test had just
written, so `status` reported "not running".

Those tests were **already hermetic** — they control the cwd branch instead of pinning it.
That is the correction this run bought, and it is why the shipped fixture is scoped to the
module with the defect and the general rule is written as "a test **pins or controls** what
it resolves" in
[`docs/capabilities/testing-and-contracts.md`](../../../capabilities/testing-and-contracts.md).

### T3 — full suite from the repo root, home config present

The other working directory, same machine state:

```console
### T3: FULL SUITE from repo root, home config PRESENT
4493 passed, 1 skipped in 227.16s (0:03:47)
```

**AC2 met**: the suite is green from both working directories, with the operator's own CLI
config present — the state in which a contributor's `make check` was red.

### T4 — the parity claim

```console
make test : [cd cli && uv run python -m pytest -q]
hook      : [cd cli && uv run python -m pytest -q]
IDENTICAL
```

**AC3 met**: the Makefile's CI-parity rule now describes what it does — the `test:` recipe
is byte-for-byte the pre-commit `pytest` hook's entry, working directory included, and the
`# CI parity:` comment above it says why the `cd` is part of the command. The header RULE
is narrowed from "all scripts run from the project root" (which the `cd` would have made
untrue) to invocation, and states that a target needing another working directory changes
into it and says so.

`.pre-commit-config.yaml` and `.github/workflows/ci.yml` are **unchanged**: the local target
moved onto CI's command, not the reverse, so nothing about what runs on a runner changed.

And the target a contributor is actually told to run, end to end, on a machine that **has**
`~/.the-loop/cli-config.yaml` — the configuration in which it used to be red:

```console
$ make check                    # lint, format-check, typecheck, validate, test
home config PRESENT
...
4493 passed, 1 skipped in 227.35s (0:03:47)
MAKE CHECK EXIT=0
```

Each target individually: `ruff check cli hooks` — *All checks passed!*; `ruff format
--check` — *350 files already formatted*; `pyright cli` — *0 errors, 0 warnings, 0
informations*; `validate_config.py` — all `VALID`; `markdownlint-cli2 "**/*.md"` —
*1387 file(s), 0 error(s)*.

**AC2 met**: `make check` passes on a machine carrying the operator's own CLI config, which
is the machine CI's green was not predicting.

## Found while verifying, not fixed here: the repo-root run writes into the checked-in tree

Running the suite from the repository root leaves the working tree **dirty**:

```console
$ git status --porcelain .the-loop/
 M .the-loop/portable/github-octo-repo-15.json
```

The diff is a control record's timestamp — `"requestedAt"` moved to the moment the suite
ran. The mechanism is this ticket's own root cause, one layer further on: from the repo
root, `default_cli_config_path()` finds this repository's `.the-loop/cli-config.yaml`
(branch 3), that file sets `state: root: .the-loop`, and a test that reaches the default
state root therefore writes its control record into the **checked-in** `.the-loop/portable/`
rather than a `tmp_path`.

It is **pre-existing and not this change's doing**: nothing in the diff writes a control
record, the affected path is in no test this PR touches, and the run from `cli/` (T2) leaves
the tree clean. It has already cost the repository once —
`.the-loop/portable/github-octo-repo-15.json` holds the *tests'* fixture ref, `octo/repo#15`,
and was committed in [PR #366](https://github.com/MadaraUchiha-314/the-loop/pull/366)
alongside an unrelated change, which is what test debris looks like after someone ran the
suite from the root and committed the result.

Not fixed here, because it is a different defect from the two this ticket names and fixing
it would widen the PR past its acceptance criteria — the same call
[#410](https://github.com/MadaraUchiha-314/the-loop/issues/410) made when it split this
ticket out. Filed separately; recorded here so the split is on the record rather than in
someone's memory. **The Makefile change in this PR removes the way a contributor most
easily hits it**: `make test` no longer runs the suite from the repository root.

The file was restored (`git checkout`) and is **not** part of this PR's diff.
