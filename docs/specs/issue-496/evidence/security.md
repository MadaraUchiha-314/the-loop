---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#496"
---

# T8 — the eight abuse cases, the import graph, the SQL assertion, the exposure guard

> Captured 2026-10-19 on `feat/issue-496-gateway`, from `cli/` with `THE_LOOP_CLI_CONFIG` unset (this machine's own instance sets it; one unrelated lifecycle test reads it).

```text
cd cli && uv run python -m pytest -q -rA tests/test_gateway_security.py tests/test_gateway_*.py -k "security or signature or replayed or injected or second_peer or never_fetched or ten_thousand or retention_expires or pasted_token or duplicate_actor or every_claim or non_loopback or missing_secret or import or f_string or exposure"
60 passed, 127 deselected in 2.04s
```

The plan named one file (`test_gateway_abuse_integration.py`); the scenarios landed beside the component each attacks instead, so the selection above is by scenario name. The mapping:

| Abuse case | Scenario | File |
|---|---|---|
| 1 bad / missing signature | a webhook with a wrong signature is refused and stores nothing | `test_gateway_adapters_integration.py` |
| 2 Slack timestamp outside window | a replayed Slack delivery is refused | `test_gateway_slack_integration.py` |
| 3 prompt injection in a payload | an injected start keyword from an unauthorized actor is dropped on the instance (gateway half: stored verbatim and held; instance half: the router drops it as unauthorized-actor) | `test_gateway_adapters_integration.py`, `test_gateway_client_integration.py` |
| 4 second peer under a live instance name | a second peer under the same instance name is refused while the first polls | `test_gateway_consume.py`, `test_gateway_client.py`, `test_gateway_store.py` |
| 5 commit for a delivery never fetched | a commit for a delivery never fetched is refused | `test_gateway_consume.py`, `test_gateway_store.py` |
| 6 duplicate flood / unbounded growth | ten thousand duplicate deliveries store one row; retention expires committed rows | `test_gateway_process_integration.py`, `test_gateway_store.py` |
| 7 literal token in config | a config with a pasted token fails validation naming the key (six `*Env` keys) | `test_gateway_config.py` |
| 8 a claim or registration steers a subject | a duplicate actor registration is refused; every claim is listed with its instance and time | `test_gateway_consume.py`, `test_gateway_store.py` |
| fail-closed | a non-loopback bind without exposed refuses to start; a missing secret variable leaves that ingress off and says so in health | `test_gateway_process_integration.py` |
| import graph / SQL | no gateway module imports the dispatcher or authz; no `execute(` takes an f-string; the exposure guard is the service's | `test_gateway_security.py` |

## Every test in the run

- `tests/test_gateway_adapters_integration.py::test_a_webhook_with_a_wrong_signature_is_refused_and_stores_nothing`
- `tests/test_gateway_adapters_integration.py::test_an_injected_start_keyword_is_stored_verbatim_and_unclassified`
- `tests/test_gateway_client.py::test_a_duplicate_actor_is_refused_and_the_client_keeps_retrying`
- `tests/test_gateway_client.py::test_a_second_peer_under_the_name_is_refused_and_retried_on_the_backoff_schedule`
- `tests/test_gateway_client_integration.py::test_an_injected_start_keyword_from_an_unauthorized_actor_is_dropped_on_the_instance`
- `tests/test_gateway_config.py::test_a_config_with_a_pasted_token_fails_validation_naming_the_key[block0-slack.socket.appTokenEnv]`
- `tests/test_gateway_config.py::test_a_config_with_a_pasted_token_fails_validation_naming_the_key[block1-slack.socket.botTokenEnv]`
- `tests/test_gateway_config.py::test_a_config_with_a_pasted_token_fails_validation_naming_the_key[block2-github.webhook.secretEnv]`
- `tests/test_gateway_config.py::test_a_config_with_a_pasted_token_fails_validation_naming_the_key[block3-github.poll.tokenEnv]`
- `tests/test_gateway_config.py::test_a_config_with_a_pasted_token_fails_validation_naming_the_key[block4-jira.poll.tokenEnv]`
- `tests/test_gateway_config.py::test_a_config_with_a_pasted_token_fails_validation_naming_the_key[block5-slack.http.signingSecretEnv]`
- `tests/test_gateway_consume.py::test_a_commit_for_a_delivery_never_fetched_is_409_and_nothing_is_fetched`
- `tests/test_gateway_consume.py::test_a_duplicate_actor_registration_is_409`
- `tests/test_gateway_consume.py::test_a_second_peer_under_a_live_name_is_409_naming_the_holder`
- `tests/test_gateway_process_integration.py::test_a_missing_secret_variable_leaves_that_ingress_off_and_says_so_in_health`
- `tests/test_gateway_process_integration.py::test_a_non_loopback_bind_without_exposed_refuses_to_start`
- `tests/test_gateway_process_integration.py::test_ten_thousand_duplicate_deliveries_store_one_row`
- `tests/test_gateway_security.py::test_no_sql_is_built_from_an_f_string[__init__.py]`
- `tests/test_gateway_security.py::test_no_sql_is_built_from_an_f_string[adapters/__init__.py]`
- `tests/test_gateway_security.py::test_no_sql_is_built_from_an_f_string[adapters/common.py]`
- `tests/test_gateway_security.py::test_no_sql_is_built_from_an_f_string[adapters/github.py]`
- `tests/test_gateway_security.py::test_no_sql_is_built_from_an_f_string[adapters/ingest.py]`
- `tests/test_gateway_security.py::test_no_sql_is_built_from_an_f_string[adapters/jira.py]`
- `tests/test_gateway_security.py::test_no_sql_is_built_from_an_f_string[adapters/poll.py]`
- `tests/test_gateway_security.py::test_no_sql_is_built_from_an_f_string[adapters/slack_http.py]`
- `tests/test_gateway_security.py::test_no_sql_is_built_from_an_f_string[adapters/slack_socket.py]`
- `tests/test_gateway_security.py::test_no_sql_is_built_from_an_f_string[client.py]`
- `tests/test_gateway_security.py::test_no_sql_is_built_from_an_f_string[client_dispatch.py]`
- `tests/test_gateway_security.py::test_no_sql_is_built_from_an_f_string[config.py]`
- `tests/test_gateway_security.py::test_no_sql_is_built_from_an_f_string[consume.py]`
- `tests/test_gateway_security.py::test_no_sql_is_built_from_an_f_string[envelope.py]`
- `tests/test_gateway_security.py::test_no_sql_is_built_from_an_f_string[ingresses.py]`
- `tests/test_gateway_security.py::test_no_sql_is_built_from_an_f_string[routing.py]`
- `tests/test_gateway_security.py::test_no_sql_is_built_from_an_f_string[serve.py]`
- `tests/test_gateway_security.py::test_no_sql_is_built_from_an_f_string[store.py]`
- `tests/test_gateway_security.py::test_the_exposure_guard_is_the_services_rule`
- `tests/test_gateway_security.py::test_the_gateway_imports_neither_the_dispatcher_nor_authz[__init__.py]`
- `tests/test_gateway_security.py::test_the_gateway_imports_neither_the_dispatcher_nor_authz[adapters/__init__.py]`
- `tests/test_gateway_security.py::test_the_gateway_imports_neither_the_dispatcher_nor_authz[adapters/common.py]`
- `tests/test_gateway_security.py::test_the_gateway_imports_neither_the_dispatcher_nor_authz[adapters/github.py]`
- `tests/test_gateway_security.py::test_the_gateway_imports_neither_the_dispatcher_nor_authz[adapters/ingest.py]`
- `tests/test_gateway_security.py::test_the_gateway_imports_neither_the_dispatcher_nor_authz[adapters/jira.py]`
- `tests/test_gateway_security.py::test_the_gateway_imports_neither_the_dispatcher_nor_authz[adapters/poll.py]`
- `tests/test_gateway_security.py::test_the_gateway_imports_neither_the_dispatcher_nor_authz[adapters/slack_http.py]`
- `tests/test_gateway_security.py::test_the_gateway_imports_neither_the_dispatcher_nor_authz[adapters/slack_socket.py]`
- `tests/test_gateway_security.py::test_the_gateway_imports_neither_the_dispatcher_nor_authz[client.py]`
- `tests/test_gateway_security.py::test_the_gateway_imports_neither_the_dispatcher_nor_authz[client_dispatch.py]`
- `tests/test_gateway_security.py::test_the_gateway_imports_neither_the_dispatcher_nor_authz[config.py]`
- `tests/test_gateway_security.py::test_the_gateway_imports_neither_the_dispatcher_nor_authz[consume.py]`
- `tests/test_gateway_security.py::test_the_gateway_imports_neither_the_dispatcher_nor_authz[envelope.py]`
- `tests/test_gateway_security.py::test_the_gateway_imports_neither_the_dispatcher_nor_authz[ingresses.py]`
- `tests/test_gateway_security.py::test_the_gateway_imports_neither_the_dispatcher_nor_authz[routing.py]`
- `tests/test_gateway_security.py::test_the_gateway_imports_neither_the_dispatcher_nor_authz[serve.py]`
- `tests/test_gateway_security.py::test_the_gateway_imports_neither_the_dispatcher_nor_authz[store.py]`
- `tests/test_gateway_slack_integration.py::test_a_replayed_slack_delivery_is_refused`
- `tests/test_gateway_store.py::test_a_commit_for_a_delivery_never_fetched_is_refused_and_nothing_applied`
- `tests/test_gateway_store.py::test_a_duplicate_actor_registration_is_refused_while_the_holder_is_live`
- `tests/test_gateway_store.py::test_every_claim_is_listed_with_its_instance_and_time`
- `tests/test_gateway_store.py::test_retention_expires_committed_then_pending_then_held`
- `tests/test_gateway_store.py::test_the_lease_refuses_a_second_peer_under_a_live_name_and_admits_the_same_peer`
