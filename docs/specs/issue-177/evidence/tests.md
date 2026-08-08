# Evidence: the tests test something, and everything is green

> Red→green record for issue-177 (M1–M9). Commands run from the repository root;
> the suite runs from `cli/` via `uv`.

## The red — before the implementation existed

`cli/tests/test_graph_skips.py` was written first and run against the unchanged
runtime:

```text
$ uv run --directory cli pytest -q tests/test_graph_skips.py
ImportError while importing test module '…/cli/tests/test_graph_skips.py'.
tests/test_graph_skips.py:33: in <module>
    from the_loop.graph.runtime import Runtime, declare_skips
E   ImportError: cannot import name 'declare_skips' from 'the_loop.graph.runtime'
1 error in 0.39s
```

Mid-implementation, with the runtime built but the shipped graph not yet touched, the
vocabulary assertions were still red — proving M2 reads the real YAML rather than the
test's miniature graph:

```text
FAILED tests/test_graph_skips.py::test_shipped_outer_loop_marks_exactly_the_spec_chain_skippable
2 failed, 25 passed in 0.26s
```

**After the owner's review replaced the declaration channel**, the nine selection tests
were written against the *label* implementation and were red there — four of them
structurally (there was no gate to answer at all), and the rest once the gate existed but
before the two bugs self-review found were fixed:

```text
FAILED tests/test_graph_skips.py::test_entry_posts_the_checklist_naming_the_selectable_phases
FAILED tests/test_graph_skips.py::test_the_checklist_is_posted_once - IndexError
FAILED tests/test_graph_skips.py::test_unticked_phases_become_declared_skips_and_the_loop_starts
FAILED tests/test_graph_skips.py::test_unticking_a_protected_phase_is_refused_and_said_so
4 failed, 29 passed in 8.32s
```

Both reds were real defects, not fixture noise: the hook was re-loading the **shipped**
graph instead of the one the runtime was executing (so `tasks` resolved to nothing in a
test graph — and would have listed the wrong phases for the inner PR loop), and its
module-level `from ..integrations import resolve` bound the name locally, bypassing the
seam every other caller patches.

## The green

```text
$ uv run --directory cli pytest -q tests/test_graph_skips.py
34 passed in 0.34s

$ uv run --directory cli pytest -q tests/test_core_graphs.py tests/test_graph_skips.py tests/test_api_contract_parity.py
39 passed in 1.6s
```

## Nothing else moved (M9)

Baseline before this work item: **1423 passed, 1 skipped** (issue-172's record at
`25a885d`). After:

```text
$ uv run --directory cli pytest -q
1459 passed, 1 skipped in 45.83s
```

The +36 are this work item's tests (34 in `test_graph_skips.py`, 2 in
`test_core_graphs.py`). Six pre-existing tests changed rather than grew: they asserted
the outer loop starts at `brainstorming` and that a spawn delivers a claim command, both
of which the new first node deliberately changes — a session is now told it is waiting at
a human gate, not told to claim it.

The API contract parity test passes with the authored `POST /graph/skip` entry, and the
graph/manifest/template parity suite (`test_graph_parity.py`), including P4's
config↔graph phase-order check, passes with `phase-selection` added to both configs'
`workflow.phases`.
