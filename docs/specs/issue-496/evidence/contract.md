---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#496"
---

# T3 — contract parity

> Captured 2026-10-19 on `feat/issue-496-gateway`, from `cli/` with `THE_LOOP_CLI_CONFIG` unset (this machine's own instance sets it; one unrelated lifecycle test reads it).

```text
cd cli && uv run python -m pytest -q tests/test_api_contract_parity.py tests/test_config_schema_parity.py
10 passed in 2.20s
```

The served OpenAPI surface of the gateway app equals `docs/api-specs/openapi/the-loop-gateway.v1.yaml` (path, method, operationId), every stored envelope validates against its `Envelope` component, the instance's `the-loop.v1.yaml` carries `GET /api/v1/gateway`, and the packaged `gateway-config.schema.json` is byte-identical to the authored one.

## `the-loop-gateway.v1.yaml`

- `DELETE /api/v1/gateway/claims` — `gatewayRelease`
- `GET /api/v1/gateway/health` — `gatewayHealth`
- `GET /api/v1/gateway/instances` — `gatewayInstances`
- `GET /api/v1/gateway/queues` — `gatewayQueues`
- `GET /api/v1/gateway/subjects` — `gatewaySubjects`
- `POST /api/v1/gateway/bindings` — `gatewayBind`
- `POST /api/v1/gateway/commit` — `gatewayCommit`
- `POST /api/v1/gateway/fetch` — `gatewayFetch`
- `POST /gh-webhook` — `githubWebhook`
- `POST /jira-webhook` — `jiraWebhook`
- `POST /slack/commands` — `slackCommands`
- `POST /slack/events` — `slackEvents`
- `POST /slack/interactions` — `slackInteractions`
- `PUT /api/v1/gateway/actors` — `gatewayRegisterActors`
- `PUT /api/v1/gateway/claims` — `gatewayClaim`

## `the-loop.v1.yaml`, the operation this work item adds

- `GET /api/v1/gateway` — `gateway`
