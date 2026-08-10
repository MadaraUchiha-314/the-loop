# Evidence — integration scenarios (T2) and the CLI surface (T6)

Work item: issue-194 · captured 2026-08-10.

## T2 — `uv run --project cli python -m pytest -q cli/tests/test_graph_refs_integration.py`

```text
............                                                             [100%]
12 passed in 0.71s
```

## The Gherkin scenarios, as `the-loop scenarios` renders them

| # | Feature | Scenario | Requirement | Location |
|---|---|---|---|---|
| 73 | outbound graph hooks reach the ticket | a graph verb with no --ref posts to the repository the config declares | docs/specs/issue-194/bugfix.md R1.1 | cli/tests/test_graph_refs_integration.py:146 |
| 74 | outbound graph hooks reach the ticket | a repository with no ticketing config says what to do about it | docs/specs/issue-194/bugfix.md R1.3, R3.1 | cli/tests/test_graph_refs_integration.py:175 |
| 75 | outbound graph hooks reach the ticket | a pull request's inner loop posts to the pull request | docs/specs/issue-194/bugfix.md R1.5 | cli/tests/test_graph_refs_integration.py:197 |
| 76 | best-effort hooks are best-effort, not silent | an outbound hook that fails reports on stdout without changing the edge | docs/specs/issue-194/bugfix.md R2.1, R2.3, R2.4 | cli/tests/test_graph_refs_integration.py:231 |
| 77 | best-effort hooks are best-effort, not silent | the advance verb prints what did not happen | docs/specs/issue-194/bugfix.md R2.2 | cli/tests/test_graph_refs_integration.py:345 |

## T6 — the CLI rows on their own

```text
$ uv run --project cli python -m pytest -q cli/tests/test_graph_refs_integration.py -k cli
..                                                                       [100%]
2 passed, 10 deselected in 0.15s
```
