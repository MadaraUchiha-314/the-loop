# Evidence — the dispatcher seam (T3)

Work item: issue-199 · captured 2026-08-10.

## T3 — `uv run --project cli python -m pytest -q cli/tests/test_graph_drive_integration.py`

```text
.........                                                                [100%]
9 passed in 0.54s
```

The scenario this work item added, as `the-loop scenarios` renders it:

| # | Feature | Scenario | Requirement | Location |
|---|---|---|---|---|
| 59 | the arming comment is an input to the node it lands on (issue-199) | a comment spawns a session for a work item | docs/specs/issue-199/bugfix.md R2.1 | cli/tests/test_graph_drive_integration.py:255 |

It drives the **real** `Dispatcher` — the one both the webhook receiver and the poller
feed — with an authorized `the-loop contribute` comment on an unmatched, armed work item,
and asserts that the `RoutedEvent` handed to `on_spawn` is the very event that caused the
spawn (`link.spawn_routed is routed`). The graph link is the suite's `_SeqLink` double,
so the assertion is about the dispatcher's wiring rather than about the graph — the graph
half is T2's.

The pre-existing ordering scenario in the same file
(`test_a_spawn_reads_context_before_render_and_enters_after`) still passes unchanged: the
context is still resolved *before* the prompt is rendered, and the graph is still entered
only *after* the spawn succeeded. The new evaluation happens inside that same
`on_spawn` call, so issue-148's "reads before the spawn, writes after it" is untouched.
