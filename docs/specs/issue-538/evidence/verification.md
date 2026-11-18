---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#538"
---

# Verification (issue-538)

Run on 2026-11-18 on branch `the-loop/issue-538-pr-session-notices` at `916c5ece`. No network:
`FakeTmux` stands in for tmux, and GitHub is never reached.

**Environment note.** This session runs inside a live the-loop daemon, which exports
`THE_LOOP_CLI_CONFIG`, `THE_LOOP_INSTANCE` and `THE_LOOP_WORK_ITEM`. Every run below unsets
them, as CI's environment does. With them set, `test_ask_reply_integration.py::test_the_ask_verb_warns_when_the_bus_names_no_channel`
reads the live config and fails, and it passes once they are unset.

## Verification results

See the table in [`testing-plan.md`](../testing-plan.md#verification-results). Raw output follows.

## V1 — new tests

```text
$ cd cli && uv run python -m pytest -q tests/test_prnotice.py tests/test_pr_notices_integration.py tests/test_outer_reevaluation_integration.py
.......................................                                  [100%]
39 passed in 9.67s
```

## V2 — neighbouring suites

```text
$ cd cli && uv run python -m pytest -q tests/test_webhook_routing_integration.py tests/test_graph_multirepo_integration.py tests/test_graph_loops.py
......................                                                   [100%]
94 passed in 23.90s
```

## V3 — full suite

```text
$ make test
FAILED tests/test_session_secrets_integration.py::test_issue_485_a_spawned_server_and_its_pane_hold_no_secret
1 failed, 6952 passed, 4 warnings in 242.81s (0:04:02)

$ cd cli && uv run python -m pytest -q tests/test_session_secrets_integration.py
1 passed
```

The one failure spawns a real tmux server and checks its environment. It passes on rerun
and is unrelated to this diff, which does not touch session secrets or the spawn
environment.

## V4 — lint, format, types

```text
$ make lint
All checks passed!
Summary: 0 error(s)
$ make format-check
522 files already formatted
$ make typecheck
0 errors, 0 warnings, 0 informations
```

## V5 — scenarios

| # | Feature | Scenario | Requirement | Location |
|---|---|---|---|---|
| 1 | pull-request session notices | a pull request with a session of its own merges | docs/specs/issue-538/requirements.md R1.5, R1.9, abuse case 1 | cli/tests/test_pr_notices_integration.py:101 |
| 2 | pull-request session notices | the same merge arrives twice under two delivery ids | docs/specs/issue-538/requirements.md abuse case 4 | cli/tests/test_pr_notices_integration.py:128 |
| 3 | pull-request session notices | a pull request with a session of its own is closed unmerged | docs/specs/issue-538/requirements.md R1.6, R2.6 | cli/tests/test_pr_notices_integration.py:150 |
| 4 | pull-request session notices | the merged pull request's events always reached the work item | docs/specs/issue-538/requirements.md R1.5 (non-functional: | cli/tests/test_pr_notices_integration.py:174 |
| 5 | pull-request session notices | the work item's session is paused | docs/specs/issue-538/requirements.md R3.1, R3.4 | cli/tests/test_pr_notices_integration.py:196 |
| 6 | pull-request session notices | the work item's record has no tmux session | docs/specs/issue-538/requirements.md R3.2 | cli/tests/test_pr_notices_integration.py:220 |
| 7 | pull-request session notices | pasting the notice fails | docs/specs/issue-538/requirements.md R3.3 | cli/tests/test_pr_notices_integration.py:243 |
| 8 | pull-request session notices | a pull request nobody linked to the work item closes | docs/specs/issue-538/requirements.md abuse case 3 | cli/tests/test_pr_notices_integration.py:268 |
| 9 | pull-request session notices | a cross-repository pull request gets a session of its own | docs/specs/issue-538/requirements.md R1.1, R1.9 | cli/tests/test_pr_notices_integration.py:353 |
| 10 | pull-request session notices | no checkout, so the work item's session takes the pull request's event | docs/specs/issue-538/requirements.md R1.2, R1.4, R1.9 | cli/tests/test_pr_notices_integration.py:379 |
| 11 | pull-request session notices | spawning the pull request's session fails | docs/specs/issue-538/requirements.md R1.3, R1.4 | cli/tests/test_pr_notices_integration.py:403 |
| 12 | pull-request session notices | the pull request's session died and is respawned | docs/specs/issue-538/requirements.md R1.8 | cli/tests/test_pr_notices_integration.py:441 |
| 13 | pull-request session notices | the pull request's dead session cannot be respawned | docs/specs/issue-538/requirements.md R1.8 | cli/tests/test_pr_notices_integration.py:462 |
| 14 | pull-request session notices | the work item's own session is respawned | docs/specs/issue-538/requirements.md R1.8 | cli/tests/test_pr_notices_integration.py:483 |
| 15 | pull-request session notices | the pull request's review approves and its inner loop completes | docs/specs/issue-538/requirements.md R1.5, R2.2 | cli/tests/test_pr_notices_integration.py:544 |
| 16 | pull-request session notices | an event leaves the pull request's inner loop escalated | docs/specs/issue-538/requirements.md R1.7 | cli/tests/test_pr_notices_integration.py:576 |
| 17 | pull-request session notices | the outer gate is re-evaluated when the last inner loop finishes | docs/specs/issue-538/requirements.md R2.1, R2.4 | cli/tests/test_outer_reevaluation_integration.py:106 |
| 18 | pull-request session notices | the re-evaluation waits again while another inner loop runs | docs/specs/issue-538/requirements.md R2.5 | cli/tests/test_outer_reevaluation_integration.py:134 |
| 19 | pull-request session notices | no previous evaluation waited, so nothing is re-run | docs/specs/issue-538/requirements.md R2.3, R4.1 | cli/tests/test_outer_reevaluation_integration.py:157 |
| 20 | pull-request session notices | parked on a node that does not wait on inner loops | docs/specs/issue-538/requirements.md R2.3 | cli/tests/test_outer_reevaluation_integration.py:178 |
| 21 | pull-request session notices | a fault in the re-evaluation does not escape | docs/specs/issue-538/requirements.md R3.5 | cli/tests/test_outer_reevaluation_integration.py:197 |
