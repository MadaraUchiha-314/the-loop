---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#519"
---

# Integration scenarios: outbound Slack through the gateway

Work item issue-519 — activity **T2** of `testing-plan.md`: the instance's real Slack channel on the real bus, its gateway-backed client bridged to a real gateway app in-process (FastAPI's test client over a real `SqliteStore`), a fake Slack Web API on the gateway, and the gateway's signed Slack HTTP ingress for the reply. Every command ran from `cli/` on the branch at the commit the results table names, with `THE_LOOP_CLI_CONFIG` unset (the daemon that spawned the session sets it, and a test that resolves the CLI config from the working directory then reads the operator's file instead).

## Scenarios (`the-loop scenarios --glob cli/tests/test_gateway_slack_proxy_integration.py --format markdown`)

| # | Feature | Scenario | Requirement | Location |
|---|---|---|---|---|
| 1 | an instance behind a gateway posts to Slack with the gateway's token | an instance with no bot token opens a work item's thread through the gateway and binds it | docs/specs/issue-519/requirements.md#requirement-2 (R2.1, R2.2), | cli/tests/test_gateway_slack_proxy_integration.py:282 |
| 2 | an instance behind a gateway posts to Slack with the gateway's token | a reply in a thread opened through the gateway reaches the work item | docs/specs/issue-519/requirements.md#requirement-4 (R4.7) | cli/tests/test_gateway_slack_proxy_integration.py:315 |
| 3 | an instance behind a gateway posts to Slack with the gateway's token | a voice note's transcript reaches the session through the gateway's download route | docs/specs/issue-519/requirements.md#requirement-3 (R3.1, R3.3) | cli/tests/test_gateway_slack_proxy_integration.py:344 |
| 4 | an instance behind a gateway posts to Slack with the gateway's token | an instance with a local token never calls the gateway | docs/specs/issue-519/requirements.md#requirement-4 (R4.1) | cli/tests/test_gateway_slack_proxy_integration.py:398 |
| 5 | an instance behind a gateway posts to Slack with the gateway's token | an instance with neither path warns at start and the post fails | docs/specs/issue-519/requirements.md#requirement-1 (R1.1, R1.6), | cli/tests/test_gateway_slack_proxy_integration.py:423 |
| 6 | an instance behind a gateway posts to Slack with the gateway's token | a gateway that stops posting fails the post and never falls back to a local token | docs/specs/issue-519/requirements.md#requirement-4 (R4.4), | cli/tests/test_gateway_slack_proxy_integration.py:453 |

## `uv run python -m pytest -q tests/test_gateway_slack_proxy_integration.py`

```text
......                                                                   [100%]
6 passed in 0.55s
```

## `uv run python -m pytest -q --dispatch-lag=0.5 tests/test_gateway_slack_proxy_integration.py`

```text
......                                                                   [100%]
6 passed in 0.59s
```

The scenarios were red on the branch before tasks 3–6 were wired (the construction sites without their CLI config, the captions guard keyed on the token) and found three gaps fixed in the task-7 commit: `chat.getPermalink` missing from the allow-list, nine `SlackBotChannel` construction sites without the CLI config, and voice-note captions skipped without a local token.
