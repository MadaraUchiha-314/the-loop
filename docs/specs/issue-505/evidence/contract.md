---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#505"
---

# Contract parity (T3)

## `uv run python -m pytest -q tests/test_api_contract_parity.py`

```text
6 passed in 2.20s
```

The served gateway surface equals `docs/api-specs/openapi/the-loop-gateway.v1.yaml`
(path, method, operationId). The one operation this work item adds:

- `PUT /api/v1/gateway/rooms` — `gatewayPublishRooms`, body `RoomsBody`

`GET /api/v1/gateway/instances` gains a `rooms` list per instance. Its response schema
is an open object, so the contract is unchanged there.
