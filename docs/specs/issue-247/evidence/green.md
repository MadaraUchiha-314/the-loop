---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#247"
---

# Evidence: the green run (issue-247)

The same three tests as [`red.md`](red.md), against the fixed `record_feedback`.
Nothing in the tests changed between the two runs — only the hook.

## The graph suite (T1, T2, T8)

```console
$ uv run --project cli python -m pytest -q cli/tests/test_graph_integration.py
.....................                                                    [100%]
21 passed in 0.51s
```

The three that were red — `test_an_approval_with_comments_is_recorded_in_the_artifact`,
`test_a_recorded_review_never_writes_emphasis_alone_on_a_line` and
`test_a_comment_with_no_body_is_recorded_without_a_blank_line_pair` — are in that count,
as is T8's `test_an_unauthorized_comment_is_not_read_and_the_gate_stays_waiting`. T8's
other half, `test_self_authored_and_unauthorized_comments_never_release_a_gate`, lives in
`cli/tests/test_pdlc_e2e_integration.py` and is covered by the whole-suite run below.
Both were left untouched: the authorization boundary is upstream of the recorder.

## The whole suite

```console
$ uv run --project cli python -m pytest -q cli
2225 passed, 1 skipped in 130.59s (0:02:10)
```
