---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#496"
---

# T2 / T7 — integration scenarios and the three budgets

> Captured 2026-10-19 on `feat/issue-496-gateway`, from `cli/` with `THE_LOOP_CLI_CONFIG` unset (this machine's own instance sets it; one unrelated lifecycle test reads it).

## Commands and outcomes

```text
cd cli && uv run python -m pytest -q tests/test_gateway_*_integration.py
49 passed in 7.49s
cd cli && uv run python -m pytest -q --dispatch-lag=0.5 tests/test_gateway_*_integration.py
49 passed in 19.41s
```

The lag run first failed one scenario (`a stopped instance finds its backlog in order`): it waited five seconds for three deliveries whose follow-up writes the lag slows; it now waits on the deferred outcomes being settled with a generous budget (commit 1e6e57a). Every scenario carries a Gherkin docstring with its `Requirement:` link.

## The scenarios (`the-loop scenarios --format markdown --glob 'cli/tests/test_gateway_*_integration.py'`)

| # | Feature | Scenario | Requirement | Location |
|---|---|---|---|---|
| 1 | the gateway owns the webhook routes under the providers' own contracts | a signed GitHub delivery is stored, then acknowledged | docs/specs/issue-496/requirements.md#requirement-1 (R1.3), R2.1, R2.4, | cli/tests/test_gateway_adapters_integration.py:69 |
| 2 | the gateway owns the webhook routes under the providers' own contracts | a webhook with a wrong signature is refused and stores nothing | docs/specs/issue-496/requirements.md §Security considerations, abuse case 1 | cli/tests/test_gateway_adapters_integration.py:103 |
| 3 | the gateway owns the webhook routes under the providers' own contracts | an event about no work item is dropped and recorded as unbound | docs/specs/issue-496/requirements.md#requirement-2 (R2.3), R5.10 | cli/tests/test_gateway_adapters_integration.py:128 |
| 4 | every event reaches its consumers raw; the instance judges | an injected start keyword from an unauthorized actor is dropped on the instance | docs/specs/issue-496/requirements.md §Security considerations, abuse case 3; | cli/tests/test_gateway_adapters_integration.py:171 |
| 5 | the gateway owns the webhook routes under the providers' own contracts | GitHub redelivers a comment and the gateway stores one row | docs/specs/issue-496/requirements.md#requirement-2 (R2.6) | cli/tests/test_gateway_adapters_integration.py:207 |
| 6 | the gateway owns the webhook routes under the providers' own contracts | a Jira comment through the gateway is stored under its key's subject | docs/specs/issue-496/requirements.md#requirement-1 (R1.4), R5.1 | cli/tests/test_gateway_adapters_integration.py:234 |
| 7 | fail closed | a missing secret variable leaves that ingress off | docs/specs/issue-496/design.md §Security design, fail-closed | cli/tests/test_gateway_adapters_integration.py:267 |
| 8 | many instances, one queue each | a driver and a reviewer on two instances each receive their own queue | docs/specs/issue-496/requirements.md#requirement-4 (R4.1, R4.5), R5.3, | cli/tests/test_gateway_claims_integration.py:65 |
| 9 | many instances, one queue each | a start by a registered actor lands on that actor's instance only | docs/specs/issue-496/requirements.md#requirement-5 (R5.5), R4.1 | cli/tests/test_gateway_claims_integration.py:121 |
| 10 | many instances, one queue each | a pull request event with no binding is routed by actor and the instance | docs/specs/issue-496/requirements.md#requirement-5 (R5.7, R5.8) | cli/tests/test_gateway_claims_integration.py:158 |
| 11 | many instances, one queue each | a stopped instance finds its backlog in order | docs/specs/issue-496/requirements.md#requirement-4 (R4.4), R2.8, R3.2, | cli/tests/test_gateway_claims_integration.py:195 |
| 12 | many instances, one queue each | the same instance resuming after a stop receives what was routed to it meanwhile | docs/specs/issue-496/requirements.md#requirement-3 (R3.9), R4.4 | cli/tests/test_gateway_claims_integration.py:249 |
| 13 | every event reaches its consumers raw; the instance judges | an issue comment through the gateway spawns on the instance with the | docs/specs/issue-496/requirements.md#requirement-1 (R1.3), R2.1, R3.4, | cli/tests/test_gateway_client_integration.py:51 |
| 14 | every event reaches its consumers raw; the instance judges | a crash between dispatch and commit redelivers once and the dispatcher | docs/specs/issue-496/requirements.md#requirement-3 (R3.6, R3.7) | cli/tests/test_gateway_client_integration.py:99 |
| 15 | every event reaches its consumers raw; the instance judges | an injected start keyword from an unauthorized actor is dropped on the instance | docs/specs/issue-496/requirements.md §Security considerations, abuse case 3 | cli/tests/test_gateway_client_integration.py:156 |
| 16 | every event reaches its consumers raw; the instance judges | a Jira comment through the gateway rings the instance's doorbell unchanged | docs/specs/issue-496/requirements.md#requirement-5 (R5.1, R5.6) | cli/tests/test_gateway_client_integration.py:186 |
| 17 | one classifier, two transports | a Slack delivery is classified by slack.dispatch_envelope on the instance | docs/specs/issue-496/requirements.md#requirement-5 (R5.6) | cli/tests/test_gateway_client_integration.py:237 |
| 18 | instances pull their own queue from the gateway | a long-poll returns within a second of an append | docs/specs/issue-496/requirements.md#requirement-3 (R3.3); | cli/tests/test_gateway_consume_integration.py:27 |
| 19 | instances pull their own queue from the gateway | an empty long-poll answers empty when wait elapses | docs/specs/issue-496/requirements.md#requirement-3 (R3.3) | cli/tests/test_gateway_consume_integration.py:57 |
| 20 | instances pull their own queue from the gateway | a fetch by one of fifty instances reads only its own queue | docs/specs/issue-496/requirements.md non-functional Scalability (R4.1) | cli/tests/test_gateway_consume_integration.py:73 |
| 21 | instances pull their own queue from the gateway | an event with no consumer waits on unassigned until a claim routes it | docs/specs/issue-496/requirements.md#requirement-2 (R2.2), R5.2, R5.3 | cli/tests/test_gateway_consume_integration.py:102 |
| 22 | an instance with a gateway block runs no ingress of its own | an instance with a gateway block runs no ingress of its own | docs/specs/issue-496/requirements.md#requirement-3 (R3.8), R10.3 | cli/tests/test_gateway_hosted_integration.py:49 |
| 23 | compatibility | an instance without a gateway block hosts the receiver, poller and | docs/specs/issue-496/requirements.md non-functional Compatibility; R14.2 | cli/tests/test_gateway_hosted_integration.py:98 |
| 24 | an instance with a gateway block runs no ingress of its own | GET /api/v1/gateway describes the client for the dashboard card | docs/specs/issue-496/requirements.md#requirement-10 (R10.3) | cli/tests/test_gateway_hosted_integration.py:127 |
| 25 | an instance with a gateway block runs no ingress of its own | a gateway and an instance share one machine on loopback | docs/specs/issue-496/requirements.md#requirement-14 (R14.1, R14.2, | cli/tests/test_gateway_hosted_integration.py:162 |
| 26 | the gateway polls the providers the instance used to poll | the gateway poller produces the same delivery ids the instance poller produces | docs/specs/issue-496/requirements.md#requirement-1 (R1.5), R7.1 | cli/tests/test_gateway_poll_integration.py:81 |
| 27 | the gateway polls the providers the instance used to poll | a webhook and a poll of the same comment store one row | docs/specs/issue-496/requirements.md#requirement-7 (R7.3, R7.4) | cli/tests/test_gateway_poll_integration.py:112 |
| 28 | the gateway polls the providers the instance used to poll | an instance's commit outcome ends or keeps the presence offering | docs/specs/issue-496/requirements.md#requirement-3 (R3.4), R1.5 | cli/tests/test_gateway_poll_integration.py:158 |
| 29 | the gateway polls the providers the instance used to poll | a work item that left the listing is stored as a webhook-shaped closure | docs/specs/issue-496/requirements.md#requirement-1 (R1.5) | cli/tests/test_gateway_poll_integration.py:196 |
| 30 | the gateway is one process that follows its own config | editing gateway-config.yaml starts a poller without a restart | docs/specs/issue-496/requirements.md#requirement-8 (R8.4) | cli/tests/test_gateway_process_integration.py:76 |
| 31 | the gateway is one process that follows its own config | a bad edit keeps the previous configuration running | docs/specs/issue-496/requirements.md#requirement-8 (R8.5) | cli/tests/test_gateway_process_integration.py:115 |
| 32 | the gateway is one process that follows its own config | changing the listen port while running is applied on the next restart | docs/specs/issue-496/requirements.md#requirement-8 (R8.6) | cli/tests/test_gateway_process_integration.py:142 |
| 33 | fail closed | a missing secret variable leaves that ingress off and says so in health | docs/specs/issue-496/design.md §Security design, fail-closed | cli/tests/test_gateway_process_integration.py:175 |
| 34 | fail closed | a non-loopback bind without exposed refuses to start | docs/specs/issue-496/requirements.md#requirement-14 (R14.3); §Security | cli/tests/test_gateway_process_integration.py:206 |
| 35 | at-least-once with a bound | a delivery that fails three times is dead-lettered and committed | docs/specs/issue-496/requirements.md#requirement-3 (R3.6) | cli/tests/test_gateway_process_integration.py:226 |
| 36 | bounded growth (abuse case 6) | ten thousand duplicate deliveries store one row | docs/specs/issue-496/requirements.md §Security considerations, abuse case 6 | cli/tests/test_gateway_process_integration.py:256 |
| 37 | the lifecycle verbs mean what the service's do | the-loop gateway start, status, instances and stop run a real process | docs/specs/issue-496/requirements.md#requirement-9 (R9.1, R9.2), R14.2 | cli/tests/test_gateway_process_integration.py:301 |
| 38 | the lifecycle verbs mean what the service's do | a second gateway on one state root is refused by the pidfile lock | docs/specs/issue-496/requirements.md#requirement-9 (R9.1) | cli/tests/test_gateway_process_integration.py:378 |
| 39 | one Slack app serves every instance through the gateway | a Slack envelope is stored before it is acknowledged | docs/specs/issue-496/requirements.md#requirement-2 (R2.4, R2.5), R1.2, R2.7 | cli/tests/test_gateway_slack_integration.py:123 |
| 40 | one Slack app serves every instance through the gateway | the doctor's heartbeat feeds the split check, not a queue | docs/specs/issue-496/design.md §gateway/adapters (slack_socket.py) | cli/tests/test_gateway_slack_integration.py:150 |
| 41 | one Slack app serves every instance through the gateway | a store failure withholds the ack | docs/specs/issue-496/requirements.md#requirement-2 (R2.4) | cli/tests/test_gateway_slack_integration.py:165 |
| 42 | one Slack app serves every instance through the gateway | a Slack envelope is acknowledged within three seconds with two thousand rows stored | docs/specs/issue-496/requirements.md#requirement-2 (R2.5); testing plan T7 | cli/tests/test_gateway_slack_integration.py:182 |
| 43 | one Slack app serves every instance through the gateway | the HTTP events route verifies the v0 signature and answers url_verification | docs/specs/issue-496/requirements.md#requirement-7 (R7.2), R6.4 | cli/tests/test_gateway_slack_integration.py:224 |
| 44 | one Slack app serves every instance through the gateway | a replayed Slack delivery is refused | docs/specs/issue-496/requirements.md §Security considerations, abuse case 2 | cli/tests/test_gateway_slack_integration.py:252 |
| 45 | one Slack app serves every instance through the gateway | a socket and an HTTP route on one app never double-deliver | docs/specs/issue-496/requirements.md#requirement-7 (R7.3) | cli/tests/test_gateway_slack_integration.py:271 |
| 46 | one Slack app serves every instance through the gateway | a button press and a slash command reach the queue as interactive and slash_commands | docs/specs/issue-496/requirements.md#requirement-5 (R5.9), R6.4 | cli/tests/test_gateway_slack_integration.py:290 |
| 47 | one classifier, two transports | dispatch_envelope hands each envelope shape to the handler the listener used | docs/specs/issue-496/requirements.md#requirement-5 (R5.6) | cli/tests/test_gateway_slack_integration.py:331 |

## T7 — the three budgets, measured

`scratchpad/verify/t7_budgets.py` drives the real store and API in-process:

| Budget (testing plan) | Measured | Verdict |
|---|---|---|
| A Slack envelope stored and acknowledged within 3 s with 2 000 rows stored | 0.0284 s | pass |
| Ten thousand duplicate deliveries store one row and finish within 10 s | 0.692 s, 1 row | pass |
| A long-poll returns within 1 s of an append | 0.0021 s | pass |
| A fetch by one of fifty instances reads only its own queue | 3 rows (its backlog), 0.0037 s; query plan `SEARCH d USING INDEX deliveries_queue (instance=? AND seq>?)` | pass |
