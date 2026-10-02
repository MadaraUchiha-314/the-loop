# Verification (issue-451)

Executed at the `verification` node on 2026-10-02, on this work item's PR branch
(`claude/github-issue-451-bs23ml`), in the work item's cloud checkout: `uv 0.12.22`,
Python 3.11, no network for the tests. One section per row of `testing-plan.md`. The
summaries are as the runner printed them, from `cli/`.

## Red first (T6, negative control)

The new tests were written before the code. Against the unchanged source:

```text
$ uv run python -m pytest -q tests/test_modelchoice.py
E   ImportError: cannot import name 'default_model' from 'the_loop.modelchoice'

$ uv run python -m pytest -q tests/test_dispatcher_choice.py tests/test_selection_choices.py tests/test_models_cmd.py
FAILED tests/test_dispatcher_choice.py::test_a_work_item_that_chose_no_model_launches_on_its_harnesss_default
FAILED tests/test_dispatcher_choice.py::test_an_effort_only_choice_still_runs_on_the_default_model
FAILED tests/test_dispatcher_choice.py::test_abuse_a_forged_frozen_model_lands_on_the_default
FAILED tests/test_selection_choices.py::test_the_model_section_names_the_default_harnesss_default_model
FAILED tests/test_selection_choices.py::test_the_confirmation_names_the_default_model_when_none_was_ticked
FAILED tests/test_models_cmd.py::test_each_harnesses_default_model_is_asked_about_on_that_harness_once
6 failed, 66 passed
```

The tests that stayed green on the old source are the "nothing changes" guards (a frozen
model wins, the default never reaches another harness, an invalid default reaches no
argv, a refused default is dropped, the unchanged confirmation): they assert behaviour
the old code already had and must keep. The schema test fails on the old schema too: its
`additionalProperties: false` rejects `defaultModel` outright. Outcome: **pass**.

## T1: unit, vocabulary

```text
$ uv run python -m pytest -q tests/test_modelchoice.py
54 passed
```

`default_model` reads the named entry; another harness's entry, a missing one, and
flag-, path-, shell-shaped or non-string values all give `""`; it does not need
`models[]`; the no-model-flag finding fires. Outcome: **pass**.

## T2: integration, dispatcher

```text
$ uv run python -m pytest -q tests/test_dispatcher_choice.py
32 passed
```

Through the real dispatcher over the fake tmux: a work item with no model launches on
`--dangerously-skip-permissions --model opus-5`, and the session record says `opus-5`. A
frozen model wins. An effort-only choice gets the default model. A forged frozen model
lands on the default. Claude's default never reaches cursor. An invalid default leaves
the shared adapter untouched. A refused default is dropped. Outcome: **pass**.

## T3: unit, gate

```text
$ uv run python -m pytest -q tests/test_selection_choices.py
30 passed
```

The checklist tail names `opus-5` as the `claude` harness's default. The confirmation
names `opus-5` as the `claude` harness's default. A ticked model still wins, and
without a default both lines are unchanged. Outcome: **pass**.

## T4: unit, probe matrix

```text
$ uv run python -m pytest -q tests/test_models_cmd.py
10 passed
```

Outcome: **pass**.

## T5: static, schema

```text
$ uv run python scripts/validate_config.py
VALID   (6 files, including .the-loop/cli-config.yaml and the shipped template)
```

Both schema copies are byte-identical (`test_config_schema_parity.py`). The schema test
in `test_modelchoice.py` accepts `opus-5` and `claude-opus-5:beta` and rejects `--model`
and `a b`. Outcome: **pass**.

## T7: regression, full suite

```text
$ uv run python -m pytest -q
5238 passed, 1 skipped, 2 warnings in 229.29s
```

The first full run failed one test, `test_docs_parity.py::test_p4_every_schema_leaf_is_documented`,
because the new schema leaf had no config-reference entry yet. Adding
`harnesses[].defaultModel` to `docs/config/cli/harnesses-options.md` fixed it. Outcome:
**pass**.

## T8: static

```text
$ uv run ruff format --check cli hooks
401 files already formatted
$ uv run ruff check cli hooks
All checks passed!
$ uv run pyright cli
0 errors, 0 warnings, 0 informations
$ npx markdownlint-cli2 <changed .md>
Summary: 0 error(s)
```

Outcome: **pass**.

## Not run

T9 (a real `claude` launch), T10 (UI), T11 (OpenAPI) and T12 (performance) are `n/a`, for
the reasons the testing plan gives.
