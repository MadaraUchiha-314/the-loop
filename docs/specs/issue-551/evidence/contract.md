# Contract parity (T3)

Run on 2026-11-20 at `a0b978dd`, after the review fixes, from `cli/`, with `THE_LOOP_CLI_CONFIG`,
`THE_LOOP_INSTANCE` and `THE_LOOP_WORK_ITEM` unset. A daemon-spawned session exports
those, and with them set some unrelated status tests read the live daemon.

| Row | Command | Result |
|---|---|---|
| T3 | `uv run python -m pytest -q tests/test_api_contract_parity.py` | 8 passed in 2.93s |

The contract `docs/api-specs/openapi/the-loop.v1.yaml` gained three operations
(`waitSession`, `stopCheckSession`, `turnStartSession`), `defaultAfterSeconds` on
the ask body, and descriptions of the new response fields. The parity test
compares the contract with the schema the service serves.
