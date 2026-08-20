# Evidence: test runs (issue-277)

Captured on 2026-08-20 on this branch, and **re-run after the owner's ruling**
([decision-100](../../../decisions/decision-100.md)) added the `create`/`delete` verbs —
the numbers below are that second run. No redaction needed: no output below carries a
token, a hostname or a path outside this checkout.

## Baseline — `make test` on `main` at `b6bfda1`

```text
2501 passed, 1 skipped in 131.06s (0:02:11)
```

## After — `make test` on this branch

```text
........................................................................ [ 97%]
...........................................................              [100%]
2600 passed, 1 skipped in 144.39s (0:02:24)
```

+99 tests, none removed, none skipped that was not skipped before: 96 in the four new
files, and 3 added to `test_tmux_runner.py` for the runner split.

## T1/T2/T8 — the new tests alone

`uv run --project cli python -m pytest -q cli/tests/test_standing.py cli/tests/test_standing_integration.py cli/tests/test_standing_channels_integration.py cli/tests/test_standing_security_integration.py`

```text
96 passed in 1.84s
```

## T1 — the runner split is a refactor

`uv run --project cli python -m pytest -q cli/tests/test_tmux_runner.py` — 111 tests
before this branch, 114 after; the 111 are unchanged, which is the check that the
work-item paths behave identically.

```text
..........................................                               [100%]
114 passed in 0.29s
```

## T3 — the served schema equals the authored contract

`uv run --project cli python -m pytest -q cli/tests/test_api_contract_parity.py`

```text
..                                                                       [100%]
2 passed in 1.22s
```

## T10 — parity gates (docs, SDK docs, state, event catalog, schema)

```text
..............................................................           [100%]
62 passed in 2.10s
```
