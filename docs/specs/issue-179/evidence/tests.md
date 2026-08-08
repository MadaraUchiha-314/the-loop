# Evidence — tests (issue-179)

Red first, then green. Every command run from this repository's checkout on 2026-08-08.

## The red run — the new tests against the pre-change source

The four source files (`pdlc-work-item-loop.yaml`, `hooks/artifacts.py`,
`hooks/selection.py`, `templates/execution-log.md`) were reverted to `HEAD` with the new
tests in place:

```console
$ uv run --directory cli pytest -q tests/test_graph_skips.py tests/test_graph_hooks.py \
    tests/test_graph_verification_integration.py tests/test_graph_parity.py \
    tests/test_core_graphs.py tests/test_graph_model.py
FAILED tests/test_graph_skips.py::test_shipped_outer_loop_marks_every_phase_but_the_gate_skippable
FAILED tests/test_graph_skips.py::test_shipped_skip_sets_name_the_two_chains
FAILED tests/test_graph_skips.py::test_the_former_floor_is_now_declarable_and_carries_no_required_marker
FAILED tests/test_graph_skips.py::test_the_checklist_says_so_when_nothing_is_protected
FAILED tests/test_graph_skips.py::test_the_shipped_checklist_offers_every_phase_the_item_walks
FAILED tests/test_graph_hooks.py::test_only_when_skipped_is_dormant_when_the_artifact_exists
FAILED tests/test_graph_hooks.py::test_only_when_skipped_is_dormant_when_nothing_was_declared
FAILED tests/test_graph_hooks.py::test_only_when_skipped_can_never_widen_what_may_be_skipped
FAILED tests/test_graph_verification_integration.py::test_verification_gates_the_log_when_the_plan_was_declared_away
FAILED tests/test_core_graphs.py::test_skip_declares_against_the_shipped_vocabulary
FAILED tests/test_graph_model.py::test_the_shipped_graph_compiles - AssertionError
11 failed, 142 passed in 0.90s
```

Two notes on what did **not** go red, because a green test in a red run is worth
explaining:

- `test_only_when_skipped_gates_the_fallback_for_a_planned_absence` (M7) passes either
  way — without the parameter the entry simply applies unconditionally, which produces the
  same block-then-pass. Its three siblings (M8) are what pin the *dormancy*, and all three
  were red.
- `test_declaring_every_phase_away_walks_the_item_to_its_terminal` (M6) runs against a
  fixture graph, not the shipped one, so it does not depend on the YAML edit.

### M13 — the parity red, isolated

`test_p5c` only fails once the graph gates the new section, so it was run with the source
restored and **only** `templates/execution-log.md` at `HEAD`:

```console
$ uv run --directory cli pytest -q tests/test_graph_parity.py
E  AssertionError: a node gates a section of a shared artifact that the bundled template
   does not offer, so every work item authored from the template blocks there:
   execution-log.md: node 'verification' requires a 'Verification results' section the
   template does not offer
1 failed, 7 passed in 0.20s
```

This is issue-167's failure mode caught by the test issue-167 produced — exactly the
regression the section addition prevents.

## The green run

Each file run on its own (`uv run --directory cli pytest -q <file>`):

| File | Result |
|---|---|
| `tests/test_graph_skips.py` | 46 passed |
| `tests/test_graph_hooks.py` | 46 passed |
| `tests/test_graph_verification_integration.py` | 10 passed |
| `tests/test_graph_parity.py` | 8 passed |
| `tests/test_core_graphs.py` | 5 passed |

## Full regression

```console
$ uv run --directory cli pytest -q
1480 passed, 1 skipped in 47.32s
```

Baseline on `main` before this work item: 1467 passed, 1 skipped. The delta is +13:
twelve new tests (M1–M13 minus the ones folded into existing cases) and one existing test
replaced by two (`test_shipped_outer_loop_marks_exactly_the_spec_chain_skippable` and
`test_shipped_floor_is_not_skippable` became four assertions of the new truth).

## The shipped graph, as compiled

```console
$ uv run --directory cli python -c "..."
skippable:     brainstorming, capability-docs, critic-review, design, design-approval,
               evidence, human-approval, implementation, requirements-approval,
               requirements-definition, reviewer-briefing, security-review, self-review,
               tasks-breakdown, test-planning, verification
not skippable: complete, escalated, phase-selection
required:      phase-selection
sets:          spec-chain  = brainstorming, requirements-definition,
                             requirements-approval, design, test-planning,
                             design-approval, tasks-breakdown
               review-chain = self-review, critic-review, security-review, evidence,
                             capability-docs, reviewer-briefing
```
