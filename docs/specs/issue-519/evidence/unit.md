---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#519"
---

# Unit, abuse-case and upgrade tests: outbound Slack through the gateway

Work item issue-519 — activities **T1**, **T8** and **T10** of `testing-plan.md`. Every command ran from `cli/` on the branch at the commit the results table names, with `THE_LOOP_CLI_CONFIG` unset (the daemon that spawned the session sets it, and a test that resolves the CLI config from the working directory then reads the operator's file instead).

## T1 — `uv run python -m pytest -q tests/test_gateway_slack_proxy.py tests/test_slack_gateway_client.py tests/test_slack_posting_path.py`

```text
............................................................             [100%]
60 passed in 1.03s
```

The three files are the red→green record of tasks 1–6: each task's commit message carries the red count (5 failed; 1 failed + 10 errors; 8 failed; 13 failed; 14 failed; 5 failed) and the green one.

## T8 — `uv run python -m pytest -q tests/test_gateway_slack_proxy.py tests/test_gateway_slack_proxy_integration.py -k abuse`

```text
....                                                                     [100%]
4 passed, 27 deselected in 0.48s
```

Selected (`--collect-only`):

```text
tests/test_gateway_slack_proxy.py::test_abuse_1_a_method_outside_the_allow_list_is_422_and_nothing_is_sent
tests/test_gateway_slack_proxy.py::test_abuse_5_posting_disabled_is_503_and_sends_nothing
tests/test_gateway_slack_proxy.py::test_abuse_5b_no_token_on_the_gateway_is_503_no_token
tests/test_gateway_slack_proxy.py::test_abuse_4_download_refuses_off_host_and_over_cap_before_any_fetch
```

Abuse case 1 (a method outside the allow-list), 4 (off-host and over-cap downloads refused before any fetch) and 5 (posting disabled, and no token on the gateway) are these four; abuse case 6 (a non-loopback bind without `exposed`) is the existing `test_a_non_loopback_bind_without_exposed_refuses_to_start` in `tests/test_gateway_process_integration.py`, run by T12; abuse cases 2–3 were withdrawn by the owner at the design review. The fail-closed set (a stale peer → `409`, bounds → `422` at the door, the proxy never reading a local token, no text in the log) is the `route` and `proxy` groups of T1 and the sixth scenario of T2.

## T10 — `uv run python -m pytest -q tests/test_gateway_slack_proxy.py -k migration`

```text
25 deselected in 0.06s
```

Selected:

```text
tests/test_gateway_slack_proxy.py::test_config_migration_a_20_9_0_file_without_slack_post_reads_posting_on
tests/test_gateway_slack_proxy.py::test_config_migration_an_instance_config_from_20_9_0_posts_with_its_local_token
```

No store change, so no schema migration: a `gateway-config.yaml` without `slack.post` reads posting on, and an instance config from 20.9.0 (a gateway block beside a local bot token) posts with its own token and never calls the gateway.
