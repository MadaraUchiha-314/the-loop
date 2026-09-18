---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#382"
---

<!-- Authored per the the-loop:writing skill. -->

# Unit evidence: the poll clocks are this machine's, not the repository's

> Testing-plan rows T1, T2, T3, T5, T6, T7. Run from the repository root with
> `uv run --project cli python -m pytest -q <suite>`.

## T1 — the clock store (`cli/tests/test_pollclocks.py`)

```text
14 passed in 0.09s
```

New file. Round-trips across processes, one entry per ref, an empty put that drops the
entry, `forget` for a ref that was never recorded, and the four faults: an absent file, a
file that is not JSON, a value that is not a string, and a directory that cannot be
written. Also pins `PollClockStore.beside()` against `StateLayout.poll_clocks`, so the
convenience and the declaration cannot drift.

## T2 — the split (`cli/tests/test_poller.py`)

```text
237 passed in 0.95s
```

Twelve of them are this work item's, and the rest are the poller's existing suite
unchanged — including the whole issue-332 closure schedule, which now reads the ledger
through a helper that joins both files.

## T3 — the readers (`cli/tests/test_reset.py`, `cli/tests/test_core_workitems.py`, `cli/tests/test_core_attention.py`)

```text
30 passed in 0.17s     # test_reset.py
7 passed in 0.08s      # test_core_workitems.py
9 passed in 0.11s      # test_core_attention.py (unchanged — the served shape is too)
```

## T5 — the upgrade (`pytest -q cli/tests/test_poller.py -k upgrade`)

```text
3 passed, 234 deselected in 0.15s
```

`test_an_upgraded_record_keeps_its_schedule_then_loses_the_keys` asserts both halves: the
schedule a stale record produces, and the keys it no longer carries after the first write.

## T6 — the declaration, the docs and the recipe (`cli/tests/test_state_portability.py`)

```text
12 passed in 0.05s
```

S1 (the new path is classified), S3 (`docs/cli/state.md` classifies it the same way) and
S5 (the published `.gitignore` block ignores it) all cover `<root>/local/poll-clocks.json`
without a line of test code being added: the suite is driven by `GENERATED_PATHS`.

## T7 — the abuse cases (`pytest -q cli/tests/test_pollclocks.py -k "future or malformed or unwritable"`)

```text
4 passed, 10 deselected in 0.05s
```

## Red → green

Each step was watched fail first:

| Test | The red |
|---|---|
| `test_pollclocks.py` (whole file) | `ModuleNotFoundError: No module named 'the_loop.pollclocks'` |
| `test_it_sits_beside_the_portable_records_where_the_layout_declares_it` | `AttributeError: 'StateLayout' object has no attribute 'poll_clocks'` |
| `test_state_portability.py::test_every_generated_path_is_classified` (S1) | `StateLayout.poll_clocks generates a path that GENERATED_PATHS does not classify` |
| `test_state_portability.py::test_every_generated_path_is_documented` (S3) | `poll clocks (<root>/local/poll-clocks.json) is missing from the classification table in docs/cli/state.md` |
| the seven split tests in `test_poller.py` | `7 failed, 3 passed` before `PollState` was split |
| `test_reset.py::test_clearing_poll_takes_the_machines_clocks_with_it` | the clock survived the reset |
| the three `test_core_workitems.py` clock tests | the served record carried no `lastPolledAt` |
