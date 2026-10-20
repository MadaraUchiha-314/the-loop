---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#503"
---

# Integration scenarios (T2)

The three Gherkin scenarios pass.

- **Scenario 3** (the Approve pair renders in gateway mode) fails on `origin/main`.
  That failure is the defect the ticket reported.
- **Scenarios 1 and 2** pass on `origin/main` too. The gateway client's Slack path
  never checked `read_mode`, as the ticket noted, so these two guard against a
  regression rather than prove the fix.

## Scenario table: `the-loop scenarios --root . --glob cli/tests/test_slack_gateway_read_mode_integration.py --format markdown`

| # | Feature | Scenario | Requirement | Location |
|---|---|---|---|---|
| 1 | a gateway consumer that never opens Socket Mode keeps every interactive feature | a button pressed in Slack reaches a gateway-mode instance and is handled | docs/specs/issue-503/requirements.md#requirement-1 (R1.2, R1.4), R2.2 | cli/tests/test_slack_gateway_read_mode_integration.py:52 |
| 2 | a gateway consumer that never opens Socket Mode keeps every interactive feature | the gateway client's Slack path classifies a press without checking the read mode | docs/specs/issue-503/requirements.md#requirement-1 (R1.4) | cli/tests/test_slack_gateway_read_mode_integration.py:93 |
| 3 | a gateway consumer that never opens Socket Mode keeps every interactive feature | a gateway-mode instance renders Approve / Request changes on an approval notification | docs/specs/issue-503/requirements.md#requirement-2 (R2.2), R3.1 | cli/tests/test_slack_gateway_read_mode_integration.py:116 |

## Run: `cd cli && uv run python -m pytest -q tests/test_slack_gateway_read_mode_integration.py`

```text
test_slack_gateway_read_mode_integration.py::test_an_approval_press_reaches_a_gateway_mode_instance PASSED
test_slack_gateway_read_mode_integration.py::test_the_real_classifier_routes_a_gateway_press PASSED
test_slack_gateway_read_mode_integration.py::test_a_gateway_mode_instance_renders_the_approve_pair PASSED
============================== 3 passed in 0.42s ===============================
```
