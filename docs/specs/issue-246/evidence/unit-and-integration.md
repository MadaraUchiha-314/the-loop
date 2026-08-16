# Unit and integration runs (green)

All commands run from the repository root on the work item branch.

## T1 — fetch, merge and filtering

```console
$ uv run pytest cli/tests/test_poller.py -k "comments or review" -q
...............                                                          [100%]
15 passed, 115 deselected in 0.07s
```

## T2 — the poll cycle, end to end (Gherkin-documented)

```console
$ uv run pytest cli/tests/test_poller_integration.py -k review -q
..                                                                       [100%]
2 passed, 17 deselected in 0.57s
```

## T8 — the negative tests (authorization and the self-comment marker)

```console
$ uv run pytest cli/tests/test_poller.py -k "unauthorized or self_authored or webhook_path_is" -q
.........                                                                [100%]
9 passed, 121 deselected in 0.07s
```

## T10 — the ledger reads forward, and holds a merged thread

```console
$ uv run pytest cli/tests/test_poller.py -k "ledger" -q
.....                                                                    [100%]
5 passed, 125 deselected in 0.07s
```

## T13 — the whole suite

```console
$ uv run pytest -q
2124 passed, 1 skipped, 2 warnings in 102.13s (0:01:42)
```
