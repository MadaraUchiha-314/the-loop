# Evidence — tests (issue-174)

Test evidence for the testing plan's rows T1, T2, T8 and T10. Every command was run from
the repository root on the work item's branch. Output is reproduced verbatim; it contains
test names, counts and file paths only — no tokens, credentials or internal hostnames.

## The red → green transition (`tdd.mode: standard`)

The task DAG's tasks 1 and 2 are one red→green pair, and the order was chosen so the red is
real: **task 2 first** (gate the section), then **task 1** (offer it in the template).

### Red — the gate declared, the template silent

```console
$ uv run --project cli pytest cli/tests/test_graph_parity.py -k p5c -v

>       assert not problems, (
            "a node gates a section of a shared artifact that the bundled template does not "
            "offer, so every work item authored from the template blocks there: "
            + "; ".join(problems)
        )
E       AssertionError: a node gates a section of a shared artifact that the bundled
        template does not offer, so every work item authored from the template blocks
        there: execution-log.md: node 'capability-docs' requires a 'Documentation'
        section the template does not offer
E       assert not ["execution-log.md: node 'capability-docs' requires a 'Documentation'
        section the template does not offer"]

cli/tests/test_graph_parity.py:334: AssertionError
======================= 1 failed, 7 deselected in 0.14s ========================
```

The failure names the node, the artifact and the section — which is the assertion doing
exactly the job issue-167 built it for.

### Green — the template offers the section

```console
$ uv run --project cli pytest cli/tests/test_graph_parity.py -v
============================== 8 passed in 0.14s ===============================
```

## T1 — graph parity (`test_graph_parity.py`)

```console
$ uv run --project cli pytest cli/tests/test_graph_parity.py -v
platform linux -- Python 3.11.15, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/user/the-loop/cli
collected 8 items

test_p1_every_tracked_artifact_is_accepted_by_its_phase_node PASSED       [ 12%]
test_p2_every_gated_name_is_tracked_by_the_manifest PASSED                [ 25%]
test_p3_every_gated_name_has_a_template_that_can_satisfy_it PASSED        [ 37%]
test_p5a_every_content_gate_resolves_an_artifact_to_read PASSED           [ 50%]
test_p5b_every_validated_artifact_is_tracked_by_the_manifest PASSED       [ 62%]
test_p5c_every_validated_section_exists_in_that_artifacts_template PASSED [ 75%]
test_p4_the_graph_defines_the_phase_sequence[own-config] PASSED           [ 87%]
test_p4_the_graph_defines_the_phase_sequence[template-config] PASSED      [100%]

============================== 8 passed in 0.14s ===============================
```

P5a/P5b/P5c run over **both** shipped loops (issue-172 made the assertions iterate the loop
registry), which is what proves R4.5 mechanically: the inner `pdlc-pr-loop` declares no
`capability-docs` node, so it gates neither section, and the suite is green either way only
because the outer loop's declaration and the bundled template agree.

P4 is the assertion behind R1.4 and R3.3 — the graph defines the phase sequence the prose
renders. The sequence it pins, and which the README and `what-is-the-loop.md` now copy:

```console
$ uv run --project cli python -c "import yaml; print(' -> '.join(
    yaml.safe_load(open('.the-loop/harness-config.yaml'))['workflow']['phases']))"
not-started -> brainstorming -> requirements-definition -> design -> test-planning
  -> tasks-breakdown -> implementation -> verification -> needs-review -> complete
```

## T2 / T8 — the gate's behaviour, including fail-closed

The testing plan marked T2 (integration) `n/a` on the reasoning that the change was
confined to one element of a `sections:` list. **That was wrong**, and the implementation
found it: `cli/tests/test_graph_review_chain_integration.py` evaluates the *shipped* graph's
review-chain nodes end to end against real execution logs, and it encoded "one gated section
per node" in a `GATED` map. Adding a second section to `capability-docs` failed it:

```console
$ make check
FAILED cli/tests/test_graph_review_chain_integration.py::
       test_a_review_node_passes_once_its_section_carries_a_record[capability-docs]
E       AssertionError: assert 'block' == 'pass'
1 failed, 1422 passed, 1 skipped in 53.39s
```

`GATED` now maps a node to a **tuple** of sections, and a new negative test asserts the
property R4.2 actually needs — that neither section can stand in for the other:

```console
$ uv run --project cli pytest cli/tests/test_graph_review_chain_integration.py -v
collected 25 items

test_a_review_node_blocks_when_its_section_was_never_written[capability-docs] PASSED
test_a_review_node_blocks_when_its_section_was_never_written[critic-review] PASSED
test_a_review_node_blocks_when_its_section_was_never_written[evidence] PASSED
test_a_review_node_blocks_when_its_section_was_never_written[reviewer-briefing] PASSED
test_a_review_node_blocks_when_its_section_was_never_written[security-review] PASSED
test_a_review_node_blocks_when_its_section_was_never_written[self-review] PASSED
test_a_review_node_passes_once_its_section_carries_a_record[capability-docs] PASSED
test_a_review_node_passes_once_its_section_carries_a_record[critic-review] PASSED
test_a_review_node_passes_once_its_section_carries_a_record[evidence] PASSED
test_a_review_node_passes_once_its_section_carries_a_record[reviewer-briefing] PASSED
test_a_review_node_passes_once_its_section_carries_a_record[security-review] PASSED
test_a_review_node_passes_once_its_section_carries_a_record[self-review] PASSED
test_capability_docs_blocks_when_only_one_of_its_two_sections_is_written PASSED
test_a_review_node_blocks_when_the_log_is_absent_entirely[capability-docs] PASSED
test_a_review_node_blocks_when_the_log_is_absent_entirely[critic-review] PASSED
test_a_review_node_blocks_when_the_log_is_absent_entirely[evidence] PASSED
test_a_review_node_blocks_when_the_log_is_absent_entirely[reviewer-briefing] PASSED
test_a_review_node_blocks_when_the_log_is_absent_entirely[security-review] PASSED
test_a_review_node_blocks_when_the_log_is_absent_entirely[self-review] PASSED
test_the_bundled_template_can_clear_every_gate_in_the_chain[capability-docs] PASSED
test_the_bundled_template_can_clear_every_gate_in_the_chain[critic-review] PASSED
test_the_bundled_template_can_clear_every_gate_in_the_chain[evidence] PASSED
test_the_bundled_template_can_clear_every_gate_in_the_chain[reviewer-briefing] PASSED
test_the_bundled_template_can_clear_every_gate_in_the_chain[security-review] PASSED
test_the_bundled_template_can_clear_every_gate_in_the_chain[self-review] PASSED

============================== 25 passed in 0.14s ==============================
```

The three assertions that carry R4.3's fail-closed criterion:

| Test | Proves |
|------|--------|
| `test_capability_docs_blocks_when_only_one_of_its_two_sections_is_written` | A work item that folded in its capability docs and left the README stale **blocks**. Asserted in both directions |
| `test_a_review_node_blocks_when_its_section_was_never_written[capability-docs]` | A log with neither section blocks, and the message names both |
| `test_the_bundled_template_can_clear_every_gate_in_the_chain[capability-docs]` | The **unedited** bundled template clears the gate — so the new requirement is satisfiable by an agent that starts from the template, which is the latent failure issue-167 warned about |

With the hook suite alongside it:

```console
$ uv run --project cli pytest cli/tests/test_graph_review_chain_integration.py \
      cli/tests/test_graph_hooks.py -q
...................................................................      [100%]
67 passed in 0.49s
```

## T10 — the migration sweep

`design.md` §Error handling states that every execution log predating this change fails
`capability-docs` until the section is added. This is that consequence, measured rather
than assumed:

```console
$ ls docs/specs/*/execution-log.md | wc -l
56
$ grep -L '^## Documentation' docs/specs/*/execution-log.md | wc -l
55
$ grep -l '^## Documentation' docs/specs/*/execution-log.md
docs/specs/issue-174/execution-log.md
```

**55 logs lack the section, and none of them is live work.** All 56 carry
`status: in-progress` — the pre-existing drift the graph was built to address, recorded in
`pdlc-work-item-loop.yaml`'s own header ("23 of 26 execution logs stopped there") — but the
work items behind them are closed and their PRs merged:

```console
$ # open issues at the time of this run
174  doc update to add inner (PR) and outer loop (Work Item)   loop:requirements-definition
157  `the-loop install`/`upgrade` should support the Cursor…    loop:needs-review
$ ls docs/specs/issue-157 2>/dev/null || echo "no spec dir"
no spec dir
```

So the practical migration surface is: **this work item** (which carries the section) and
issue-157, which has no spec directory at all and therefore already blocks on a missing
execution log rather than on a missing section — unchanged by this work item. A historical
log is only re-evaluated if someone re-runs a closed work item's node, and the remedy then
is one heading and one sentence, which is the work the gate is asking for.

## T12 — whole-suite regression

```console
$ make check
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
Linting: 451 file(s)
Summary: 0 error(s)
…
1424 passed, 1 skipped in 50.04s
```

1424 passed against 1423 on `main` — the one added test is
`test_capability_docs_blocks_when_only_one_of_its_two_sections_is_written`. Full lint, type
and schema output is in [`lint-and-types.md`](lint-and-types.md).
