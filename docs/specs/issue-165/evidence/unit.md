# Evidence: unit + abuse-case tests (T1, T8)

Work item: issue-165 · re-run after the owner's review removed length budgets
(PR #168), which took the parity assertions from P1–P6 down to P1–P4.

## The writing-parity test

```console
$ uv run --project cli python -m pytest -q cli/tests/test_writing_parity.py
............                                                             [100%]
12 passed in 0.36s
```

## What it asserts

```console
$ uv run --project cli python -m pytest cli/tests/test_writing_parity.py --collect-only -q
tests/test_writing_parity.py::test_p1_writing_skill_exists_and_parses
tests/test_writing_parity.py::test_p2_human_read_template_points_at_the_skill[requirements.md]
tests/test_writing_parity.py::test_p2_human_read_template_points_at_the_skill[bugfix.md]
tests/test_writing_parity.py::test_p2_human_read_template_points_at_the_skill[design.md]
tests/test_writing_parity.py::test_p2_human_read_template_points_at_the_skill[testing-plan.md]
tests/test_writing_parity.py::test_p2_human_read_template_points_at_the_skill[tasks.md]
tests/test_writing_parity.py::test_p2_human_read_template_points_at_the_skill[pr-briefing.md]
tests/test_writing_parity.py::test_p2_human_read_template_points_at_the_skill[decision.md]
tests/test_writing_parity.py::test_p2_human_read_template_points_at_the_skill[capability.md]
tests/test_writing_parity.py::test_p3_pointers_name_the_configured_skill
tests/test_writing_parity.py::test_p3_the_schema_declares_no_length_limits
tests/test_writing_parity.py::test_p4_no_p0_tell_in_shipped_prose

12 tests collected in 0.02s
```

## Full suite — no regression from the schema and template edits

```console
$ make test
........................................................................ [ 96%]
.............................................                            [100%]
1340 passed, 1 skipped in 49.00s
```
