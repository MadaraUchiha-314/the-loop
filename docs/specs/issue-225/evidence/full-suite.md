# Evidence: T3, T10 — the contract is unchanged and nothing else moved

Rows T3 (contract) and T10 (migration/upgrade) of [`testing-plan.md`](../testing-plan.md).

## T3 — the control-plane API contract is unchanged

```console
$ uv run pytest tests/test_api_contract_parity.py -q
.                                                                        [100%]
1 passed in 0.99s
```

This work item adds no route, request shape or response shape; the parity test between
`docs/api-specs/openapi/the-loop.v1.yaml` and the served application proves it.

## T10 — the generalization is behaviour-preserving for the existing loops

The three "contribution or default" comparisons that became
`graph.model.resolve_outer_loop` are exercised by their own existing suites:

```console
$ uv run pytest tests/test_graph_contribution.py tests/test_graphlink.py \
    tests/test_core_graphs.py -q
........................................................................ [ 73%]
..........................                                               [100%]
98 passed in 0.50s
```

A pre-issue-225 `graph-state.json` — no `loop` field, or `loop: pdlc-contribution-loop`
— resolves exactly as before: `test_state_loop_round_trips_and_predates_gracefully` and
`test_graphlink_prefers_state_then_control_record` in the contribution suite are
unmodified and still pass.

## The whole suite

```console
$ uv run pytest -q
........................................................................ [ 99%]
........                                                                 [100%]
2023 passed, 1 skipped in 71.65s (0:01:11)
```

The one skip is `test_client.py`'s live-service case, skipped in every run (it needs the
`routed` marker and a running service).

Parity tests covering this change without new code, all included above:
`test_config_schema_parity` (the packaged schema copy is byte-identical to the authored
one), `test_docs_parity` (every schema leaf has a documented option with Type and
Default — `control.keywords.do` included), `test_graph_parity` (no gated artifact is
untracked by the manifest — trivially satisfied, since `pdlc-adhoc-loop` gates none) and
`test_graph_contribution.py::test_every_shipped_loop_is_loadable` (which now loads four).
