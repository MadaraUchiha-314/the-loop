---
type: bugfix
phase: requirements-definition
workItem: "github:MadaraUchiha-314/the-loop#412"
status: approved             # draft | in-review | approved
approvedBy: ["the-loop"]     # tier 1–2: autonomous-complete per the skill's risk tiers; the acceptance is the ticket's own, copied verbatim
severity: medium
collaborators: [engineer]
overrides: {}
riskTier: 2                  # test-only plus one task-runner target; no runtime code, no schema, no credential path
---

<!-- Authored per the the-loop:writing skill. -->

# Bugfix spec: four `test_instance.py` tests read the machine they run on

> Phases 1–2 of 4 (bugfix+design → testing plan → tasks). Source:
> [issue-412](https://github.com/MadaraUchiha-314/the-loop/issues/412), split out of
> [#410](https://github.com/MadaraUchiha-314/the-loop/issues/410) /
> [#411](https://github.com/MadaraUchiha-314/the-loop/pull/411).

## Summary

Four tests in `cli/tests/test_instance.py` assert the **exact** set of `-e` flags on a
spawn argv. One of those flags, `THE_LOOP_CLI_CONFIG`, is exported only when a CLI config
file is found — and the lookup that finds it reads ambient machine state. So the four
tests pass or fail depending on **where pytest was started** and **whether the machine
running it has a config at all**.

CI is green only because its runner happens to have neither. Every developer who actually
*runs* the-loop — the whole target audience — has `~/.the-loop/cli-config.yaml`, and sees
the suite red.

## Steps to reproduce

On `main` at `6809ca6`, with no `~/.the-loop/cli-config.yaml`:

```console
$ uv run --project cli python -m pytest -q cli/tests/test_instance.py   # from the repo root
4 failed, 59 passed

$ cd cli && uv run python -m pytest -q tests/test_instance.py           # the invocation CI uses
63 passed
```

Then, still from `cli/`:

```console
$ cp .the-loop/cli-config.yaml ~/.the-loop/cli-config.yaml
$ cd cli && uv run python -m pytest -q tests/test_instance.py
4 failed, 59 passed
```

## Expected vs actual

| | Expected | Actual |
|---|---|---|
| a unit test of argv construction | the same answer everywhere | the answer depends on `$PWD` and on `$HOME`'s contents |
| `make check` on a clean `main` | green wherever CI is green | red on every machine that has a CLI config |
| the Makefile's CI-parity rule | true | `make test` and the `pytest` hook run different commands |

## Root cause

`default_cli_config_path()` ([`cli/the_loop/cli_config.py:59`](../../../cli/the_loop/cli_config.py))
resolves in this order:

1. an explicit override (`--config`),
2. `$THE_LOOP_CLI_CONFIG`,
3. **`Path(".the-loop")/cli-config.yaml` — relative to the current working directory**,
4. `~/.the-loop/cli-config.yaml`.

`TmuxRunner._cli_config_export()` ([`cli/the_loop/runner.py:149`](../../../cli/the_loop/runner.py))
exports `THE_LOOP_CLI_CONFIG` whenever that path is a file. Branches 3 and 4 are ambient,
and the tests never pin the lookup, so:

| where pytest starts | `~/.the-loop/cli-config.yaml` | what step 3/4 finds | the four tests |
|---|---|---|---|
| repo root | absent | this repo's own `.the-loop/cli-config.yaml` (step 3) | **fail** |
| `cli/` | absent | nothing | pass |
| `cli/` | present | the home config (step 4) | **fail** |
| repo root | present | this repo's config (step 3) | **fail** |

Only the second row is green, and that is the row CI happens to be in.

### Two defects, not one

1. **The tests depend on ambient state.** They exercise the runner's argv, not config
   discovery, so they should pin the config path and assert the argv they mean.
2. **`make check` and CI do not run the same command, while the Makefile says they do.**

| | command | cwd |
|---|---|---|
| `make test` | `uv run --project cli python -m pytest -q cli` | repo root |
| pre-commit `pytest` hook (what CI runs) | `bash -c 'cd cli && uv run python -m pytest -q'` | `cli/` |

A claimed parity that does not hold is worse than none: `make check` is the command a
contributor is told to run before pushing, and whoever hits it first has to work out that
the failure is about their own machine, not their diff.

## The fix

### Defect 1 — pin the lookup in `test_instance.py`

The module gains an autouse `_no_ambient_cli_config` fixture that points
`$THE_LOOP_CLI_CONFIG` at a path inside the test's own `tmp_path` that is never created.

Two choices worth stating:

- **Pin the *path*, not the *function*.** Setting the environment variable leaves
  `default_cli_config_path()` and `_cli_config_export()` running for real — they simply
  find no file, the same way, from any directory on any machine. Monkeypatching either
  one would have tested a stub instead of the code under test.
- **The module, not the whole suite.** This was tried the other way first, and the suite
  said no. A `conftest.py` fixture pinning the variable for every test failed 14 tests in
  `test_poll_status.py`, `test_poll_command.py` and `test_lifecycle_cmd.py` — recorded in
  [`evidence/verification.md`](evidence/verification.md) § The suite-wide variant. Those
  tests `chdir` into a `tmp_path` and write a **real** `./.the-loop/cli-config.yaml`
  there, because the config path's parent is what anchors the **state root**
  (`state.py`'s `layout_from_config`, issue-339). Pinning the variable moved their state
  root out from under them.

  That is the correction the attempt bought: **the cwd branch is not ambient in itself.**
  A test that chdirs somewhere of its own and puts a config there controls the lookup
  completely and is hermetic already. What is ambient is a test that neither pins the
  lookup nor controls what it will find — which is these four, and not the suite. So the
  fixture belongs where the defect is.

### Defect 2 — make the parity claim true

`make test` becomes `cd cli && uv run python -m pytest -q` — byte-for-byte the pre-commit
hook's entry, working directory included — with a comment saying why the `cd` is part of
the command rather than an accident, and the header RULE reworded to match. The direction
is deliberate: the hook is what CI runs, so the *local convenience target* moves to it,
not the other way round. Changing the hook would have changed CI's behaviour to fix a
local-only complaint.

## What it costs

- Every test in `test_instance.py` now runs with `$THE_LOOP_CLI_CONFIG` set, including the
  ones that do not spawn. That is the price of an autouse fixture over four decorations,
  and it is the right way round: the next argv test added to this module inherits the
  pinning instead of inheriting the bug.
- The rest of the suite is untouched, so the same shape can recur in another module. The
  standing rule written into `docs/capabilities/testing-and-contracts.md` is what covers
  that — a rule a reviewer can apply, rather than a fixture that would move the state root
  out from under the tests that legitimately use the cwd branch.
- `make test` no longer runs from the repo root, so the header RULE ("all scripts run from
  the project root") is narrowed to invocation rather than working directory, and the
  exception is written down where it applies.

## Acceptance criteria

1. WHEN the four `test_instance.py` tests run THEN they SHALL pass regardless of the
   working directory pytest was started from and regardless of whether the machine has a
   CLI config in either location.
2. WHEN a contributor runs `make check` on a clean checkout of `main` THEN it SHALL pass
   on any machine on which CI passes for that same commit.
3. WHEN the Makefile states a CI-parity rule THEN the commands it runs SHALL be the ones
   CI runs, or the comment SHALL state where and why they differ.
