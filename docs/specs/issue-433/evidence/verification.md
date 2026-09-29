---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#433"
---

# Verification: two bugs in the `hooks[]` declaration loader

> The `verification` node executing [`testing-plan.md`](../testing-plan.md). Every planned
> activity is ticked below with the exact command, the outcome and the output.

## Environment

- `uv` 0.12.17 (the version `.github/workflows/ci.yml` pins), `uv sync --locked` succeeded.
- Python 3.11.15, PyYAML 6.0.3 from `uv.lock`; branch `claude/github-issue-433-dwdky8`
  on `3360972` (19.14.0).
- All `pytest` runs from `cli/`, the working directory the pre-commit hook and
  `make test` use.

## Activities

- [x] **T1–T3** — loader unit tests (R1.1–R1.4, R2.1, R2.2)
- [x] **T4** — the ticket's reproduction through a file and `the-loop hooks` (R1.5)
- [x] **T5** — negative control on the unfixed loader (R2.3)
- [x] **T6** — the two modules, all tests
- [x] **T7** — full suite from `cli/`
- [x] **T8** — `ruff check`, `ruff format --check`, `pyright cli`, `markdownlint`
- [x] **T11** — the normalisation widens nothing (review + the unchanged catalog test)
- [x] **T9, T10, T12–T14** — `n/a`/`no` with the reasons recorded in the plan; nothing to run

## Verification results

| Row | Command | Outcome | Evidence |
|-----|---------|---------|----------|
| T5 | the 7 new tests with `declaration.py` stashed | **7 failed**, with the ticket's `TypeError` texts | § T5 below |
| T1–T4 | the same 7 tests on the fixed tree | **7 passed** (part of T6) | § T6 below |
| T6 | `uv run python -m pytest -q tests/test_lifecycle_declaration.py tests/test_hooks_cmd.py` | **81 passed** | § T6 below |
| T7 | `cd cli && uv run python -m pytest -q` | **4885 passed, 1 skipped** | § T7 below |
| T8 | `uv run ruff check cli hooks`; `uv run ruff format --check cli hooks`; `uv run pyright cli`; `markdownlint-cli2` on the touched pages | all clean | § T8 below |
| T11 | `test_on_may_name_only_catalog_points` unchanged and green; diff review | no widening | [`security-review.md`](security-review.md) |

### T5 — negative control: the bugs, on the unfixed loader

`cli/the_loop/lifecycle/declaration.py` stashed so only the tests differ from `main`;
the seven new tests selected with `-k`:

```console
    7 failed, 74 deselected in 0.28s
    E           TypeError: sequence item 0: expected str instance, NoneType found
    E           TypeError: sequence item 0: expected str instance, bool found
    E           TypeError: sequence item 0: expected str instance, int found
    E        +  where 1 = main(['hooks', '--format', 'json'])
    E       AssertionError: assert 1 == 0
    E       TypeError: '<' not supported between instances of 'int' and 'str'
    FAILED tests/test_hooks_cmd.py::test_the_documented_bare_on_key_is_reported_not_a_type_error
    FAILED tests/test_lifecycle_declaration.py::test_a_bare_on_key_loads_as_the_docs_write_it
    FAILED tests/test_lifecycle_declaration.py::test_a_quoted_on_key_still_loads_and_both_spellings_together_are_refused
    FAILED tests/test_lifecycle_declaration.py::test_an_unknown_key_that_is_not_a_string_is_still_a_hooks_config_error[1]
    FAILED tests/test_lifecycle_declaration.py::test_an_unknown_key_that_is_not_a_string_is_still_a_hooks_config_error[False]
    FAILED tests/test_lifecycle_declaration.py::test_an_unknown_key_that_is_not_a_string_is_still_a_hooks_config_error[None]
    FAILED tests/test_lifecycle_declaration.py::test_unknown_keys_of_mixed_types_are_all_named
```

The first line is the ticket's bug 2 verbatim; the `'<' not supported` line is the
same defect one statement earlier, in `sorted()`, when the unknown keys mix types. The
command test failed with the report
`could not read …/cli-config.yaml: TypeError: sequence item 0: expected str instance, bool found`,
the ticket's `the-loop hooks` output.

### T6 — the two modules on the fixed tree

```console
$ cd cli && uv run python -m pytest -q tests/test_lifecycle_declaration.py tests/test_hooks_cmd.py
81 passed in 0.35s
```

Seven of those are new (T1: 1, T2: 1, T3: 4 including the parametrised three, T4: 1);
the existing `test_an_unknown_key_is_refused` still passes under the quoted wording.

### T7 — full suite

```console
$ cd cli && uv run python -m pytest -q
4885 passed, 1 skipped in 197.79s (0:03:17)
```

### T8 — static checks

```console
$ uv run ruff check cli hooks
All checks passed!
$ uv run ruff format --check cli hooks
373 files already formatted
$ uv run pyright cli
0 errors, 0 warnings, 0 informations
$ npx --yes markdownlint-cli2@0.18.1 "docs/specs/issue-433/**/*.md" docs/capabilities/lifecycle-hooks.md docs/config/cli/hooks-options.md
Linting: 9 file(s)
Summary: 0 error(s)
```

### The loop's own gate

```console
$ uv run the-loop check issue-433 --recompute --fail-on block
issue-433: UNMET (at phase-selection)
  WAIT   phase-selection
```

A `WAIT` at a human node, not a `BLOCK`, which is the state CI's `the-loop gate` job
accepts (`--fail-on block`); the same position issue-412 reports.
