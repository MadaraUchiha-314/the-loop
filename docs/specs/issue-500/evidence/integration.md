# Integration — T2

The new scenario `test_a_gate_approved_twice_on_one_day_records_distinct_headings` in `cli/tests/test_graph_integration.py`.

## Before the fix (red)

Run against the unmodified hook, `uv run pytest cli/tests/test_graph_integration.py -q -k distinct_headings`:

```text
E         
E         At index 1 diff: '2026-10-26 — approved' != '2026-10-26 — approved (2)'
E         Use -v to get more diff

cli/tests/test_graph_integration.py:325: AssertionError
=========================== short test summary info ============================
FAILED cli/tests/test_graph_integration.py::test_a_gate_approved_twice_on_one_day_records_distinct_headings
1 failed, 29 deselected in 0.18s
```

## After the fix (green)

`uv run pytest cli/tests/test_graph_integration.py -q`:

```text
30 passed in 1.41s
```
