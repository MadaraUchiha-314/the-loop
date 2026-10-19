---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#496"
---

# T1 — unit tests

> Captured 2026-10-19 on `feat/issue-496-gateway`, from `cli/` with `THE_LOOP_CLI_CONFIG` unset (this machine's own instance sets it; one unrelated lifecycle test reads it).

```text
cd cli && uv run python -m pytest -q tests/test_gateway_*.py
187 passed in 12.62s
```

Covers `gateway/config.py` and the instance `gateway` block (`test_gateway_config.py`), the envelope and event families (`test_gateway_envelope.py`), `SqliteStore` (`test_gateway_store.py`), `consumers_for` / `resolve_ref` / `dedup_key` (`test_gateway_routing.py`), the consume API (`test_gateway_consume.py`), the client's loop against the real API in-process (`test_gateway_client.py`) and the static security assertions (`test_gateway_security.py`), plus every `*_integration.py` scenario the glob also matches.
