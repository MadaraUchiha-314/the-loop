---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#496"
---

# T10 — migration and compatibility

> Captured 2026-10-19 on `feat/issue-496-gateway`, from `cli/` with `THE_LOOP_CLI_CONFIG` unset (this machine's own instance sets it; one unrelated lifecycle test reads it).

```text
cd cli && uv run python -m pytest -q tests/test_hosted_reconcile.py tests/test_core_lifecycle.py tests/test_gateway_client_integration.py
32 passed in 2.06s
make validate
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
VALID   skills/the-loop/templates/gateway-config.yaml
```

- An instance config **without** a `gateway` block hosts the receiver, the poller and the listener exactly as before (`test_gateway_hosted_integration.py::test_an_instance_without_a_gateway_block_hosts_the_receiver_poller_and_listener_as_before`, and the hosted-reconcile and lifecycle suites unchanged in behaviour; `enabled_services` gains the additive `gateway-client` key).
- Adding the block switches the hosted set to `{gateway-client}` (`…::test_an_instance_with_a_gateway_block_runs_no_ingress_of_its_own`).
- The `cli-config.schema.json` change is additive: the repository's dogfood config and the templates validate (`make validate`).
- The store carries a `schema_version` row (`SqliteStore.schema_version()`), asserted in `test_gateway_store.py::test_offsets_survive_a_reopen`.
- **A behaviour change for Slack readers in poll mode** (found in T4, 2026-10-19): an instance that read its threads with `read.mode: poll` took every reply in a bound thread as input. Under a gateway Slack arrives over Socket Mode only, where the issue-389 rule holds — a plain reply is `not-addressed` and the mention arrives as `app_mention` — so an app installed before issue-389 (no `app_mentions:read`) hears no reply until the manifest is re-applied and the app reinstalled. Documented in the capability and raised with the author on the ticket.
