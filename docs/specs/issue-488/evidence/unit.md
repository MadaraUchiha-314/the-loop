# T1, T3, T4, T6, T8, T10 · the Python suite — issue-488

**Outcome: pass.** The full suite ran **6116 passed, 1 failed**. The failure was the Jira
golden file for the PR briefing. It differed by exactly the "Start here: the explainer"
line this change adds to `templates/pr-briefing.md`, and has been regenerated and
reviewed. `tests/test_jira_format.py` now passes, 42 of 42.

## Commands

```sh
cd cli && env -u THE_LOOP_CLI_CONFIG uv run python -m pytest -q
THE_LOOP_REGEN_JIRA_GOLDEN=1 uv run python -m pytest -q tests/test_jira_format.py -k pr-briefing
uv run python -m pytest -q tests/test_jira_format.py
```

`THE_LOOP_CLI_CONFIG` is unset because this machine's operator config, and the running
daemon it names, otherwise leaks into the suite. Without the unset, 21 tests about the
poll command, poll status, instances, lifecycle and critics fail. They fail identically
on an unchanged `main` checkout (commit `60a5dd9`), so they are not this change's.

## Results

```text
FAILED tests/test_jira_format.py::test_golden_bodies[pr-briefing] - Assertion...
1 failed, 6116 passed, 1 warning in 201.24s (0:03:21)

# after regenerating the golden file
42 passed in 0.23s
```

The golden diff that was reviewed (`cli/tests/fixtures/jira/pr-briefing.wiki`):

```diff
+*Start here:* the explainer of this change — {{<Location from evidence/explainer.md>}}.
+(Drop this line when the work item declared the {{explainer}} row away.)
```

## The new tests, by testing-plan row

| Row | Tests |
|---|---|
| T1 (unit) | `cli/tests/test_quiz.py`, 41 tests. Covers the attestation-line and digest vocabulary; `comment_edits` (newest-first sort, unknown editor kept empty, missing node refused); the provider op and Jira's refusal; `post-quiz-attestation` (link, single box, marker, idempotency per round and digest, blocking on a missing or placeholder `Location`, view commands built from safe parts only, PR fan-out with a ticket fallback); every branch of `quiz-attested`; the `explainer` row's parser, skips, confirmation and Slack mirror; the router's `edited` rewrite; the every-command-has-a-file check |
| T3 (contract) | `test_api_contract_parity.py`: unchanged and green, because no route or MCP tool was added |
| T4 (e2e) | `happy-path` now walks the four nodes with real ticks. `trivial-tier`, `ask-reply` and `review-rejection` untick the row and record four skips. The new `quiz-gates` scenario covers a refused tick, a stale spec and a fresh round |
| T6 (snapshot) | The Jira checklist golden (the new row and its section), the PR-briefing golden, and the pinned checklist layout tests |
| T8 (abuse cases) | `test_quiz_attested_refuses_unauthorized_editor`, `test_quiz_attested_fails_closed_without_editor`, `test_quiz_attested_ignores_unmarked_and_artifact_text`, `test_quiz_attested_ignores_forged_comment`, `test_explainer_template_renders_text_not_markup`, `test_a_hostile_location_gets_no_shell_command` |
| T10 (migration) | `test_frozen_graph_without_quiz_nodes_keeps_walking`, `test_a_state_with_no_frozen_graph_infers_nothing` |
