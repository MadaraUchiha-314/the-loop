# Green runs (issue-273)

Every command below was run on the final tree, after the self-review rewordings.

## Unit — the coupling's gate order and the pending context

```console
$ uv run pytest -q -p no:randomly cli/tests/test_graphlink.py cli/tests/test_graph_drive.py
65 passed
```

Covers T1: the exempt actions (`start`, `context`) and the gated ones (`advance`, `clean`);
that an exempt action records no `graph.skipped` and a gated one still does, naming the
action; the declared-`specDir` parity across both; and the `pending` context — the graph's
start node, the status, and that it is not a waiting human gate.

## Integration — the reproduction, against a real dispatcher and a real runtime

```console
$ uv run pytest -q -p no:randomly \
    cli/tests/test_graphlink_integration.py \
    cli/tests/test_harness_config_scaffold_integration.py
22 passed
```

Covers T2, T8 and T10, all Gherkin-documented:

- *A work item minted as a plain ticket starts at the human gate* — the pointer lands on
  `phase-selection`, `loop:phase-selection` is set, one checklist is posted asking for
  `the-loop execute`, and no `graph.skipped` is recorded.
- *Starting the graph is not the same as walking it* — an unauthorized `the-loop execute`
  on the freshly started graph leaves the pointer where it is.
- *The prompt is rendered before the graph is entered* — the block names the node, says
  NOT ENTERED YET, names the human gate, and carries no `the-loop graph complete` line.
- *`pending` never masks a work item in flight* — a started graph reports its real node and
  a status that is not `pending`. Green on both sides of the change, by design: it is the
  control for R2.3.
- The adoption suite's plain-ticket spawn now writes `graph-state.json` where it used to
  assert its absence, and records no skip.

## Full suite

```console
$ make test
uv run --project cli python -m pytest -q cli
2482 passed, 1 skipped
```

Eleven tests are this work item's: **six new** (two in `test_graphlink.py`, four in
`test_graphlink_integration.py`) and **five rewritten** in place, where the assertion that
existed pinned the behaviour the ticket reports. Eight of the eleven failed before the
production change (see [`red.md`](red.md)); the other three are guards and controls that are
green on both sides by design — the `advance` still-skips test, the started-graph
still-reports-its-node test, and the event-log skip record retargeted to `advance`.

The suite count therefore rises by the six new tests: 2476 passed, 1 skipped before, 2482
passed, 1 skipped after.
