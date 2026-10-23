---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#519"
---

# Contract parity: the gateway's OpenAPI document

Work item issue-519 — activity **T3** of `testing-plan.md`. Every command ran from `cli/` on the branch at the commit the results table names, with `THE_LOOP_CLI_CONFIG` unset (the daemon that spawned the session sets it, and a test that resolves the CLI config from the working directory then reads the operator's file instead).

## `uv run python -m pytest -q tests/test_api_contract_parity.py`

```text
......                                                                   [100%]
6 passed in 2.33s
```

`docs/api-specs/openapi/the-loop-gateway.v1.yaml` carries the two operations the gateway now serves — `gatewaySlackCall` (`POST /api/v1/gateway/slack/call`) and `gatewaySlackDownload` (`POST /api/v1/gateway/slack/download`) — with `SlackCallBody` and `SlackDownloadBody`; the gateway half of the parity test compares every path, method and operation id of the served schema to the authored file, and the control-plane half is unchanged.
