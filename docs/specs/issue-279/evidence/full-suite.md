# Evidence: the full suite (T3, T10)

Captured 2026-08-24, on the work item's branch, from `cli/`.

## The whole Python suite — nothing else moved

```console
$ uv run pytest -q
2667 passed, 1 skipped in 127.67s (0:02:07)
```

2600 passed, 1 skipped on `main` at `b6bfda1` (recorded by issue-277's verification;
the intervening `a5f432b` is a version bump) — **+67**: the 62 tests of
`test_graph_review.py` (55 at first verification, +1 from the security review's
marker-spoofing fix, +6 from the work-item-level reviews of the owner's PR #280
ruling), plus the review loop joining `test_graph_cleanup.py`'s
work-item-loop parametrizations (which also gained the ad-hoc loop, a pre-existing gap).

## The contract stays unchanged (T3)

```console
$ uv run pytest tests/test_api_contract_parity.py -q
..                                                                       [100%]
2 passed in 1.35s
```

No route, request or response shape was added — the review loop is comments and graph
state, not API surface.

## The generalized seams are behaviour-preserving (T10)

```console
$ uv run pytest tests/test_graph_contribution.py tests/test_graph_adhoc.py \
    tests/test_graphlink.py tests/test_core_graphs.py -q
..................                                                       [100%]
162 passed in 1.30s
```

The two adoption call sites now test `GUEST_LOOPS` membership instead of comparing to
`PDLC_CONTRIBUTION_LOOP`; every pre-existing loop's test passes unchanged.
