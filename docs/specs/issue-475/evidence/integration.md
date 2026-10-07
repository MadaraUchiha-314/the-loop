---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#475"
---

# Integration scenarios (T6, issue-475)

Run on 2026-10-06 at `b5c1154`, with the session's env vars removed (see
[`verification.md`](verification.md)). The harness runs the router, the dispatcher and
the session registry in-process, with `FakeJiraClient` and the fake tmux runner.

```text
$ cd cli && uv run python -m pytest -q tests/test_jira_integration.py
...........                                                              [100%]
11 passed in 2.22s
```

## Scenarios (Jira rows)

From `the-loop scenarios --root <repo> --glob 'cli/tests/test_*_integration.py' --format markdown`.
The listing has 680 rows in all, and these 11 are Jira's. All six scenarios the plan
names are among them (rows 368, 369, 370, 375, 376 and 377).

| # | Feature | Scenario | Requirement | Location |
|---|---|---|---|---|
| 368 | Jira as a work-item source | an authorized Jira comment resumes the work item's session | docs/specs/issue-475/requirements.md#R5.3 | cli/tests/test_jira_integration.py:212 |
| 369 | Jira as a work-item source | the same Jira comment by webhook and by poll is delivered once | docs/specs/issue-475/requirements.md#R6.4 | cli/tests/test_jira_integration.py:246 |
| 370 | Jira as a work-item source | a Jira phase-selection checklist ticked in place is read at execute | docs/specs/issue-475/requirements.md#R5.5 | cli/tests/test_jira_integration.py:325 |
| 371 | Jira as a work-item source | an unlisted Jira user's execute leaves the gate waiting | docs/specs/issue-475/requirements.md#R7.2 | cli/tests/test_jira_integration.py:363 |
| 372 | Jira as a work-item source | a gate answer given on Slack advances a Jira work item's gate | docs/specs/issue-475/design.md#c8--ingress-poll-provider-webhook-doorbell-allow-list | cli/tests/test_jira_integration.py:392 |
| 373 | Jira as a work-item source | arming a Jira ticket is a label; starting it is a person | docs/specs/issue-475/design.md#security-design (abuse case 5) | cli/tests/test_jira_integration.py:445 |
| 374 | Jira as a work-item source | a Jira comment reaches the session as untrusted data | docs/specs/issue-475/design.md#security-design (abuse case 10) | cli/tests/test_jira_integration.py:478 |
| 375 | Jira as a work-item source | a PR naming a registered Jira key routes to the Jira work item | docs/specs/issue-475/requirements.md#R8.1 | cli/tests/test_jira_integration.py:505 |
| 376 | Jira as a work-item source | finish-tasks transitions the Jira ticket to Done | docs/specs/issue-475/requirements.md#R3.7 | cli/tests/test_jira_integration.py:585 |
| 377 | Jira as a work-item source | the-loop comment on a Jira ref is recorded on the Jira ticket | docs/specs/issue-475/requirements.md#R8.2 | cli/tests/test_jira_integration.py:620 |
| 378 | Jira as a work-item source | the delivered prompt names Jira and the origin repository | docs/specs/issue-475/requirements.md#R5.3 | cli/tests/test_jira_integration.py:655 |

## Deviation: an absolute `--root`

Run as the plan writes it (no `--root`), `the-loop scenarios` found nothing. It printed
`no scenarios found under <another checkout>`. A daemon was running on this host, so
the command was routed to it, and the daemon resolved the default `--root .` against its
own working directory, not the caller's. Passing the repository's absolute path as
`--root` gives the listing above. This behaviour is older than issue-475, which does not
touch `commands/scenarios.py`. It is noted here, not fixed.
