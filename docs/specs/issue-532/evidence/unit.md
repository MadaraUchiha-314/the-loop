# Unit + integration evidence — issue-532 (T1, T2, T8)

Command (from `cli/`):

```
pytest -q tests/test_graph_gateway_notify.py tests/test_graph_gateway_notify_integration.py
```

## Red — on `main`'s `bootstrap.py` (fix reverted)

The integration test reproduces the ticket's error verbatim.

```
WARNING  the-loop.graph:sideeffects.py:391 notification not delivered: slack: no bot token — export THE_LOOP_TEST_532_BOT_TOKEN (an xoxb- bot token with chat:write, and channels.history for reads), or point this instance at a gateway with slack.post.enabled
FAILED tests/test_graph_gateway_notify.py::test_the_runtime_config_carries_the_gateway_block
FAILED tests/test_graph_gateway_notify.py::test_the_runtime_config_carries_the_instance_name
FAILED tests/test_graph_gateway_notify_integration.py::test_a_graph_notification_posts_through_the_gateway_first_time
3 failed, 4 passed in 0.47s
```

## Green — with the fix

```
7 passed in 0.43s
```

Seven cases: R1.1 (gateway path), R1.2 (instance name), R1.4/T8 (absent, `null`, non-mapping, empty-URL block → `none`; four cases), R1.3 (the real `notify` hook delivers through the gateway first time, outbox empty).
