# Evidence — verification

Every applicable row of [`testing-plan.md`](../testing-plan.md), run on
`claude/github-issue-360-uav3nz` with the fix in place.

## T1, T2, T3, T10 — the argv, the critic seam, the verdict cache, the boundaries

```console
$ uv run --project cli python -m pytest -q \
    cli/tests/test_critics.py cli/tests/test_modelchoice.py cli/tests/test_modelprobe.py
99 passed in 1.49s

$ uv run --project cli python -m pytest -q cli/tests/test_critics.py -k builtin_harness
1 passed, 51 deselected in 0.03s
```

The argv itself, after the fix — the same one-liner `bugfix.md` §Steps to reproduce uses:

```console
$ uv run --project cli python -c "from the_loop.harness import CursorAgentAdapter as C; \
print(C().oneshot_argv('review this', model='gpt-5.6-sol'))"
['-p', 'review this', '--output-format', 'json', '--model', 'gpt-5.6-sol']
```

## T13 — every gate CI runs

```console
$ make check
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Linting: 1103 file(s)
Summary: 0 error(s)
uv run ruff format --check cli hooks
301 files already formatted
uv run pyright cli
0 errors, 0 warnings, 0 informations
uv run python scripts/validate_config.py
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
uv run --project cli python -m pytest -q cli
3605 passed, 1 skipped in 159.34s (0:02:39)
```

Before this work item the suite was 3603 passed, 1 skipped; the two added tests are T1's
argv assertion and T3's verdict-cache assertion. No test was skipped, disabled or deleted:
three existing assertions were **corrected** from `-m` to `--model`, listed in
[`tasks.md`](../tasks.md) tasks 1 and 3.

## T5 — the live `cursor-agent` run (external)

Not reproducible here: this container has no `cursor-agent` and no Cursor account, which
is why T4/T5 are `n/a` in the matrix. The end-to-end proof is the reporter's, on
`cursor-agent 2026.09.10-fd3934a`, quoted verbatim in
[issue-360](https://github.com/MadaraUchiha-314/the-loop/issues/360):

```console
$ cursor-agent -p "say OK" --output-format json -m auto --force
error: unknown option '-m'

$ cursor-agent -p "reply with exactly: OK" --output-format json --model auto --force
{"type":"result","subtype":"success","is_error":false,"result":"OK", ...}
```

The second line is the argv this change now produces, with the model in the same position.

## Acceptance criteria

| Criterion | Met by |
|---|---|
| R1.1 — a resolved model is passed as `--model <name>` | T1: `test_cursor_oneshot_argv_uses_the_long_model_flag`, `test_a_model_resolves_through_the_adapters_flag` |
| R1.2 — the full critic argv for `harness: cursor` + `model:` | T2: `test_builtin_harness_derives_argv_from_the_adapter` |
| R1.3 — no model, no flag: the argv is unchanged | T1: `test_oneshot_argv_without_a_model_is_the_plain_one_shot_run`, untouched and still passing |
| R1.4 — a regression test that fails before and passes after | [`red.md`](red.md) → this file |
| R2.1 — the `model_flag` rule in the capability doc | `docs/capabilities/review-loop.md` §Current behaviour, lint-clean at T13 |
| R2.2 — a History row tracing it to issue-360 | `docs/capabilities/review-loop.md` §History, first row |
