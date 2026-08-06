# Evidence: unit and parity tests

Work item: issue-164 · rows T1, T2, T3, T8, T12 of [`../testing-plan.md`](../testing-plan.md).

## The red state (TDD, task 1)

The gate assertions landed before the YAML that satisfies them. Recorded so the
red→green transition is evidence rather than a claim (`tdd.mode: standard`).

```console
uv run --project cli python -m pytest -q cli/tests/test_graph_hooks.py cli/tests/test_graph_model.py
cli/tests/test_graph_model.py:242: AssertionError
=========================== short test summary info ============================
FAILED cli/tests/test_graph_hooks.py::test_a_design_without_a_module_structure_blocks
FAILED cli/tests/test_graph_hooks.py::test_a_module_structure_heading_with_nothing_under_it_blocks
FAILED cli/tests/test_graph_model.py::TestTheDesignGateDemandsTheModuleStructure::test_the_section_is_required_beside_the_other_three
3 failed, 69 passed in 0.20s
```

The failing assertion named the missing item directly:

```text
E       AssertionError: assert {'Architectur...ing strategy'} == {'Architectur...ing strategy'}
E         Extra items in the right set:
E         'Module structure'
```

The third pre-existing case — a no-code work item whose section is one sentence — passed
in the red state too, because the gate simply did not know the section yet. It is what
proves R1.6 once the gate does.

## T1 — the design gate's section set (`test_graph_model.py`)

```console
uv run --project cli python -m pytest -q cli/tests/test_graph_model.py
........................................                                 [100%]
40 passed in 0.10s
```

## T2 — template ↔ graph parity (`test_graph_parity.py`)

P3 walks every gated section of every producing node and asserts the bundled template
offers it, read through the gate's own heading parser. No edit to this test was needed:
gating a section the template does not carry is red by construction.

```console
uv run --project cli python -m pytest -q cli/tests/test_graph_parity.py
.....                                                                    [100%]
5 passed in 0.10s
```

## T3 — the shipped gate, run through the hook (`test_graph_hooks.py`)

Three cases against the design node's real `validate-artifacts` params: a missing section
blocks, a heading with nothing under it blocks, and a docs-only one-sentence section
passes.

```console
uv run --project cli python -m pytest -q cli/tests/test_graph_hooks.py
................................                                         [100%]
32 passed in 0.13s
```

## T1/T2/T3/T12 — the full suite

No regression from the graph and template edits, and no pre-existing spec re-authored.

```console
make test
........................................................................ [ 96%]
..................................................                       [100%]
1345 passed, 1 skipped in 44.30s
```
