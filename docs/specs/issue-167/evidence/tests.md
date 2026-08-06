# Evidence: test runs (issue-167)

Captured at the `verification` node against the working tree of
`claude/github-issue-167-18l5v9`, on Python 3.11.15 / `uv`. Nothing here contains a
token, cookie, hostname or personal datum — the outputs are pytest summaries.

## T1 — hook unit tests

`cli/tests/test_graph_hooks.py`, 12 of the 42 new: `validates:` resolution, the four
kinds of content check failing closed without a target, aggregation across produced and
validated targets, alternation, ambiguity, and the `optional:` branch.

```console
$ uv run --directory cli pytest tests/test_graph_hooks.py -q
..........................................                               [100%]
42 passed in 0.10s
```

## T2 — integration, over the shipped `security-review` and its five siblings

`cli/tests/test_graph_review_chain_integration.py` — four Gherkin-documented scenarios
parametrized over all six review nodes, driven through `Runtime.evaluate` (no network, no
subprocess) against a temp spec directory.

```console
$ uv run --directory cli pytest tests/test_graph_review_chain_integration.py -q
........................                                                 [100%]
24 passed in 0.26s
```

## T8 — parity, including the new P5

`cli/tests/test_graph_parity.py` — P1–P4 unchanged, P5a/P5b/P5c added.

```console
$ uv run --directory cli pytest tests/test_graph_parity.py -q
........                                                                 [100%]
8 passed in 0.10s

$ uv run --directory cli pytest tests/test_graph_parity.py -q -k p5
...                                                                      [100%]
3 passed, 5 deselected in 0.06s
```

### P5a fails against the pre-fix graph

The check that the assertion checks something. Run with the six nodes' `validates:` lines
removed — i.e. `pdlc.yaml` exactly as it shipped before this work item:

```console
$ uv run --directory cli pytest tests/test_graph_parity.py -q
E   AssertionError: these nodes gate on artifact content but name no artifact to read
    it from, so their validate-artifacts skips and the gate reports success without ever
    running — declare `produces:` on the node or `validates:` on the hook entry:
    capability-docs (gates on ['Capability docs']);
    critic-review (gates on ['Review cycles']);
    evidence (gates on ['Final validation evidence']);
    reviewer-briefing (gates on ['Pull requests']);
    security-review (gates on ['Security review (gate)']);
    self-review (gates on ['Review cycles'])
1 failed, 7 passed in 0.13s
```

All six, named. The graph file was restored immediately afterwards.

### P5c fails against the pre-fix template

Run with `## Capability docs` removed from `skills/the-loop/templates/execution-log.md` —
the latent defect the ticket flagged, which would have blocked every work item the moment
`capability-docs` stopped skipping:

```console
$ uv run --directory cli pytest tests/test_graph_parity.py::test_p5c_every_validated_section_exists_in_that_artifacts_template -q
E   AssertionError: a node gates a section of a shared artifact that the bundled template
    does not offer, so every work item authored from the template blocks there:
    execution-log.md: node 'capability-docs' requires a 'Capability docs' section the
    template does not offer
1 failed in 0.06s
```

## Full suite — no regression elsewhere

```console
$ uv run --directory cli pytest -q
.............                                                            [100%]
1380 passed, 1 skipped in 40.05s
```

The one skip is pre-existing and unrelated — `tests/test_instructions.py:149`, guarded
with "root reads unpermitted files anyway" because the suite runs as root here.
