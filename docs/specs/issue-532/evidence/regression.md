# Regression evidence — issue-532 (T12)

Full CLI suite, from `cli/`, with the session's own `THE_LOOP_CLI_CONFIG`,
`THE_LOOP_INSTANCE` and `THE_LOOP_WORK_ITEM` unset and a scratch `HOME`, as CI runs it:

```
env -u THE_LOOP_CLI_CONFIG -u THE_LOOP_INSTANCE -u THE_LOOP_WORK_ITEM HOME=<scratch> pytest -q
```

```
6810 passed, 4 warnings in 221.45s (0:03:41)
```

A first run with those variables still set failed one test,
`test_ask_reply_integration.py::test_the_ask_verb_warns_when_the_bus_names_no_channel`.
That test assumes no CLI config with `channels`, but the variable pointed it at this
machine's daemon config. It fails the same way with the fix reverted, so the failure
comes from the environment, not this change.
