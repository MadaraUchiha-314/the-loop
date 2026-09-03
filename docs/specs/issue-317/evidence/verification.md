# Verification — issue-317

> The testing plan executed (`testing-plan.md`, rows T1, T2, T8, T10, T12). Commands run
> from the repository root at the head of `claude/github-issue-317-7mtlc5`. Fixture ids
> (`C123`, `xoxb-test`, `octo/repo`, `github:o/r#7`) are not real; nothing here needed
> redaction.

## Red → green, per task

The tests for tasks 1–4 were written first and run against `f56a71f`:

```text
uv run --project cli python -m pytest -q cli/tests/test_channels.py cli/tests/test_control_integration.py \
  cli/tests/test_core_sessions.py cli/tests/test_channels_integration.py \
  -k "open or origin or opener or start_opens or restarted or outage_never"
FAILED cli/tests/test_channels.py::test_open_posts_the_root_alone_and_binds_with_origin_start
FAILED cli/tests/test_channels.py::test_open_is_idempotent_for_a_bound_work_item
FAILED cli/tests/test_channels.py::test_open_fails_closed_like_post - AttributeError
FAILED cli/tests/test_channels.py::test_a_failed_open_binds_nothing - AttributeError
FAILED cli/tests/test_channels.py::test_a_corrupt_state_file_still_opens_on_start
FAILED cli/tests/test_channels.py::test_an_unknown_origin_is_coerced_to_event
FAILED cli/tests/test_control_integration.py::test_a_start_opens_the_conversation_once_before_the_checkout
FAILED cli/tests/test_control_integration.py::test_a_refused_start_opens_no_thread
FAILED cli/tests/test_control_integration.py::test_an_unauthorized_start_opens_no_thread
FAILED cli/tests/test_control_integration.py::test_a_raising_opener_never_fails_the_spawn
FAILED cli/tests/test_control_integration.py::test_the_opener_is_handed_the_ref_alone
FAILED cli/tests/test_control_integration.py::test_a_dispatcher_without_an_opener_opens_nothing
FAILED cli/tests/test_core_sessions.py::test_the_facade_dispatcher_opens_with_the_config_it_was_given
FAILED cli/tests/test_core_sessions.py::test_the_poll_builder_wires_an_opener_by_default
FAILED cli/tests/test_channels_integration.py::test_a_start_opens_the_work_items_thread_before_any_event
FAILED cli/tests/test_channels_integration.py::test_a_refused_start_opens_no_thread_scenario
FAILED cli/tests/test_channels_integration.py::test_a_restarted_work_item_keeps_its_thread
FAILED cli/tests/test_channels_integration.py::test_a_channel_outage_never_fails_the_spawn
18 failed, 6 passed, 144 deselected in 0.68s

uv run --project cli python -m pytest -q cli/tests/test_bus.py
ImportError: cannot import name 'open_conversation' from 'the_loop.channels.bus'
```

| Task | Red (before the change) | Green |
|------|-------------------------|-------|
| 1 channel `open` + origin | `test_channels.py` — 6 failed: `AttributeError: 'SlackBotChannel' object has no attribute 'open'`; `origin="start"` coerced to `event` | 6 passed |
| 2 bus + opener | `test_bus.py` — collection error: no `open_conversation`, no `conversation_opener` | 3 passed |
| 3 dispatcher seam + wiring | `test_control_integration.py` — 6 failed: `Dispatcher.__init__() got an unexpected keyword argument 'opener'`; `test_core_sessions.py` — 2 failed: no `opener` attribute | 8 passed |
| 4 scenarios | `test_channels_integration.py` — 4 failed (the four scenarios) | 4 passed |
| 5 docs | — | `make check` (markdownlint) below |

One test bug on the way to green: `test_open_is_idempotent_for_a_bound_work_item` first
built its second event through the file's `event()` helper, which ignores a `work_item`
argument, so the "other work item" was the already-bound one and the assertion on a fresh
root failed for the wrong reason. The test now builds the event explicitly.

Three self-review passes over the diff (recorded in `execution-log.md`): the open moved
behind the missing-adapter check so R1.4 holds for that refusal too; the opener's inner
function no longer shadows the bus's name; the restart scenario uses `dataclasses.replace`
instead of `__dict__` surgery. Pass three found nothing new.

## Rows T1, T2, T8, T10

```text
== T1  uv run --project cli python -m pytest -q cli/tests/test_channels.py cli/tests/test_bus.py cli/tests/test_control_integration.py cli/tests/test_eventlog.py
153 passed in 1.44s
== T2  uv run --project cli python -m pytest -q cli/tests/test_channels_integration.py cli/tests/test_control_integration.py
54 passed in 0.99s
== T8  uv run --project cli python -m pytest -q cli/tests -k "unauthorized_start_opens or refused_start_opens or outage_never_fails_the_spawn or handed_the_ref_alone or still_opens_on_start"
6 passed, 2992 deselected in 1.89s
== T10 uv run --project cli python -m pytest -q cli/tests/test_channels.py -k "pre_issue_312 or origin"
3 passed, 59 deselected in 0.06s
== R3.2 (the facade and the poll builder)  uv run --project cli python -m pytest -q cli/tests/test_core_sessions.py -k "opens_with_the_config or wires_an_opener"
2 passed, 50 deselected in 0.09s
```

## `make check` — the way CI runs it (T12)

```text
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Finding: **/*.md !**/node_modules/** !cli/node_modules/** !**/.venv/** !docs/.vitepress/dist/** !docs/.vitepress/cache/** !docs/operating-model/reference/** !docs/specs/*/design/**
Linting: 950 file(s)
Summary: 0 error(s)
uv run ruff format --check cli hooks
274 files already formatted
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
uv run --project cli python -m pytest -q cli
.....................................................................s.. [ 57%]
2997 passed, 1 skipped in 142.01s (0:02:22)
exit=0
```
