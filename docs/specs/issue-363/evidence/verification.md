# Evidence: verification (issue-363)

> Every applicable row of [`testing-plan.md`](../testing-plan.md), then every gate CI
> runs. Commands were executed from the project root on the work item's branch.

## T1, T9 — the recovery vocabulary and the spawn prompt

```console
$ uv run --project cli python -m pytest -q cli/tests/test_recovery.py cli/tests/test_interaction.py
...................................................                      [100%]
51 passed in 0.09s
```

## T2, T11 — the portable graph position, and a record written before it existed

```console
$ uv run --project cli python -m pytest -q cli/tests/test_control.py cli/tests/test_workitem.py \
      cli/tests/test_state_portability.py cli/tests/test_cli_config.py
........................................................................ [ 65%]
......................................                                   [100%]
110 passed in 0.55s
```

## T3 — the spawn grace window

```console
$ uv run --project cli python -m pytest -q cli/tests/test_tmux_runner.py cli/tests/test_tmux_runner_integration.py
........................................................................ [ 50%]
......................................................................   [100%]
142 passed in 4.08s
```

## T4 — the labels reader

```console
$ uv run --project cli python -m pytest -q cli/tests/test_routing.py
........................................................................ [ 72%]
......................................................                   [100%]
198 passed in 2.99s
```

## T5–T8 — the reporter's sequence, on a fresh state root

```console
$ uv run --project cli python -m pytest cli/tests/test_recovery_integration.py -v
test_a_forgotten_item_is_not_rewound_and_still_gets_a_session PASSED
test_an_event_on_a_forgotten_item_does_not_advance_it_either PASSED
test_an_item_with_no_phase_label_still_enters_the_graph PASSED
test_a_started_item_is_judged_by_its_state_file_not_its_label PASSED
test_a_corrupt_state_file_refuses_rather_than_rewinding PASSED
test_abuse_a_forged_complete_label_never_places_a_pointer PASSED
test_a_published_position_is_restored_byte_for_byte PASSED
test_the_position_is_published_on_every_graph_write PASSED
test_abuse_a_portable_position_never_overwrites_local_state PASSED
test_a_forgotten_items_old_commands_are_baselined_and_announced_once PASSED
test_a_new_items_pending_start_command_is_still_forwarded PASSED
test_abuse_an_unauthorized_command_is_still_never_executed PASSED
test_a_comment_arriving_during_the_boot_does_not_spawn_a_second_session PASSED
============================== 13 passed in 1.01s ==============================
```

## T12 — the abuse cases

```console
$ uv run --project cli python -m pytest cli/tests/test_recovery.py cli/tests/test_recovery_integration.py -k abuse -v
test_abuse_a_forged_complete_label_never_places_a_pointer PASSED
test_abuse_a_portable_position_never_overwrites_local_state PASSED
test_abuse_an_unauthorized_command_is_still_never_executed PASSED
======================= 3 passed, 27 deselected in 0.27s =======================
```

## T18 — every repository gate CI runs

```console
$ make check
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Finding: **/*.md !**/node_modules/** !cli/node_modules/** !**/.venv/** !docs/.vitepress/dist/** !docs/.vitepress/cache/** !docs/operating-model/reference/** !docs/specs/*/design/**
Linting: 1117 file(s)
Summary: 0 error(s)
uv run ruff format --check cli hooks
304 files already formatted
uv run pyright cli
WARNING: there is a new pyright version available (v1.1.411 -> v1.1.414).
Please install the new version or set PYRIGHT_PYTHON_FORCE_VERSION to `latest`

0 errors, 0 warnings, 0 informations
uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
uv run --project cli python -m pytest -q cli
3643 passed, 1 skipped in 148.47s (0:02:28)
```
