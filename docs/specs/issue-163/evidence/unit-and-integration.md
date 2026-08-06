# Evidence: unit and integration runs (T1, T2, T3, T6, T12)

Work item: issue-163. Converted from `.txt` to markdown in PR #168, when textual
evidence became markdown by rule. The recorded output below is unchanged.

```console
$ make test   # uv run --project cli python -m pytest -q cli
........................................................................ [ 97%]
.................................                                        [100%]
1328 passed, 1 skipped in 44.91s

$ uv run pytest cli/tests/test_graph_parity.py cli/tests/test_graph_model.py cli/tests/test_graph_chain.py cli/tests/test_graph_verification_integration.py -q
...............................................................          [100%]
63 passed in 0.28s
```
