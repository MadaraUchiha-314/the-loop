---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#536"
---

# Verification (issue-536)

Run on 2026-11-17 on branch `issue-536-claude-docs` at `23efe118`. GitHub is the tests'
`_FakeGitHub` double, and no real socket is opened.

**Environment note.** This session runs inside a live the-loop daemon, which exports
`THE_LOOP_CLI_CONFIG`, `THE_LOOP_INSTANCE` and `THE_LOOP_WORK_ITEM`. With them set, about
20 poller/instances/lifecycle/critics tests read the live operator config and fail. They
fail the same way on a clean `origin/main` checkout, so this change did not cause them.
Every run below unsets the three variables, as CI's environment does.

## Activities

- [x] T1–T7 written first and seen red before the change.
- [x] T1–T6 green after the change.
- [x] T7 Slack mirror green.
- [x] T8 `make check` (lint, format, pyright, config validation, full suite) and `make pre-commit`.
- [x] T9 abuse-case tests: unauthorized tick, non-boolean state, both choices true on disk.

## T1–T7: red before the change

```text
$ cd cli && uv run python -m pytest -q tests/test_claude_doc.py
tests/test_claude_doc.py:340: in _ctx
    return GraphContext(
E   TypeError: GraphContext.__init__() got an unexpected keyword argument 'claude_doc'
1 error in 0.30s
```

## T1–T6: green after the change

```text
$ cd cli && uv run python -m pytest -q tests/test_claude_doc.py tests/test_handoff_selection.py \
    tests/test_selection_defaults.py tests/test_handoff_state.py
62 passed in 0.93s
```

## T7: Slack mirror

```text
$ cd cli && uv run python -m pytest -q tests/test_selection_control.py
43 passed in 0.64s
```

## T8: regression

```text
$ make check
All checks passed!                       # ruff
Summary: 0 error(s)                      # config validation
0 errors, 0 warnings, 0 informations     # pyright
6902 passed, 3 warnings in 233.75s       # full CLI suite
$ make pre-commit
(every hook Passed or Skipped)
```

The rendered checklist snapshots (`cli/tests/fixtures/handoff/*.txt`,
`cli/tests/fixtures/jira/checklist.*`) were regenerated. The diff is limited to the
publishing section: the new title, the `Default:` line, `claude-artifact` unticked,
`claude-doc` ticked, and the note.

## T9: abuse cases

Part of the T1–T6 run above:

- `test_an_unauthorized_tick_changes_nothing`: a reply from a user who is not authorized
  leaves `claudeDoc` false and the gate waiting.
- `test_anything_but_the_boolean_true_reads_as_false`: `None`, `"true"`, `1`, lists and
  maps all read as false.
- `test_both_true_on_disk_keeps_the_artifact`: a hand-edited file with both keys set
  reads as the artifact only.
- `test_both_ticked_publishes_neither`: two ticks are refused, and the confirmation says
  why.

## Re-verification after the both-ticked decision (PR #537)

The owner decided on the PR that two ticks fall back to the default
([comment](https://github.com/MadaraUchiha-314/the-loop/pull/537#issuecomment-6940400943)).
`test_both_ticked_publishes_neither` was replaced by:

- `test_both_ticked_uses_the_default_doc`: doc frozen, artifact not; the confirmation
  names the default.
- `test_both_ticked_after_an_artifact_handoff_uses_the_artifact`: the artifact is the
  default after a handoff that brought one.
- `test_both_ticked_on_another_harness_is_not_applied`: the default is picked first,
  then the harness rule rules it out.
- `test_the_default_follows_the_handoff`: the shared `_artifact_is_default` helper, used
  by both the render and the resolve.

The checklist snapshots were regenerated; only the note line changed ("Ticking both uses
the default").

```text
$ env -u THE_LOOP_CLI_CONFIG -u THE_LOOP_INSTANCE -u THE_LOOP_WORK_ITEM make check
All checks passed!                       # ruff
Summary: 0 error(s)                      # config validation
0 errors, 0 warnings, 0 informations     # pyright
6907 passed, 4 warnings in 233.47s       # full CLI suite
```
