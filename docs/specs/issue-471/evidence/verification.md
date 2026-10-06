---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#471"
---

# Verification (issue-471)

Run on 2026-10-06 on branch `claude/github-issue-471-dyodav`, using uv 0.12.23 (the
repository requires `>=0.12,<0.13`). GitHub is the tests' `_FakeGitHub` double; the
suite's autouse fixture refuses any real socket.

## Activities

- [x] T1–T5 written first and seen red against the code before the change.
- [x] T1–T6 green after the change.
- [x] T7 full suite, ruff (lint and format), pyright, markdownlint, config validation.
- [x] T8 security review (`security-review.md`).

## T1–T5: red before the change

```text
$ cd cli && uv run python -m pytest -q tests/test_claude_artifact.py
ERROR collecting tests/test_claude_artifact.py
tests/test_claude_artifact.py:258: in _ctx
    return GraphContext(
E   TypeError: GraphContext.__init__() got an unexpected keyword argument 'claude_artifact'
1 error in 0.29s
```

## T1–T6: green after the change

```text
$ cd cli && uv run python -m pytest -q tests/test_claude_artifact.py \
    tests/test_selection_control.py tests/test_state_portability.py tests/test_docs_parity.py
85 passed in 0.44s
```

## T7: regression

```text
$ uv run ruff check cli hooks
All checks passed!
$ uv run ruff format --check cli hooks
419 files already formatted
$ uv run pyright cli
0 errors, 0 warnings, 0 informations
$ uv run python scripts/validate_config.py   # exit 0
$ cd cli && uv run python -m pytest -q
5508 passed, 1 skipped, 6 warnings in 234.60s (0:03:54)
$ npx --yes markdownlint-cli2@0.18.1 "**/*.md"
Summary: 0 error(s)
```
