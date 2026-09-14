# Evidence — the red root (task 1)

The new assertions, run against the **unfixed** tree (`e143259`, 17.0.0) before any of
the three layers existed. Captured verbatim.

```console
$ uv run --project cli python -m pytest -q cli/tests/test_channels_dm.py
ImportError while importing test module '/home/user/the-loop/cli/tests/test_channels_dm.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.11/importlib/__init__.py:126: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
cli/tests/test_channels_dm.py:27: in <module>
    from the_loop.channels.slack import (
E   ImportError: cannot import name 'CONVERSATION_KINDS' from 'the_loop.channels.slack'
=========================== short test summary info ============================
ERROR cli/tests/test_channels_dm.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.13s
```

```console
$ uv run --project cli python -m pytest -q cli/tests/test_channels_dm_integration.py
  TypeError: run_socket_listener() got an unexpected keyword argument 'catch_up_override'
=========================== short test summary info ============================
FAILED cli/tests/test_channels_dm_integration.py::test_the_listener_warns_once_about_the_dm_subscription
FAILED cli/tests/test_channels_dm_integration.py::test_a_probe_that_raises_never_keeps_the_listener_from_listening
FAILED cli/tests/test_channels_dm_integration.py::test_the_listener_reconciles_on_its_deadline_and_survives_a_raising_cycle
3 failed, 2 passed, 1 warning in 5.52s
```

## The two that passed, and why that is the point

`test_a_message_im_envelope_reaches_the_inbound_pipeline` and
`test_zero_disables_the_reconcile_and_keeps_the_connect_read` pass **before** the fix,
deliberately:

- The first asserts **R1.2** — the listener's filter is kind-agnostic and must stay that
  way. It passing on the unfixed tree is the ticket's own finding restated as a test:
  the pipeline was never the problem, the subscription was. It is a guard against a
  future "fix" that adds a DM branch.
- The second asserts **R3.2**'s `0` case, which is 16.0.1's behaviour — one catch-up
  read at connect. It passes before the change because that behaviour is today's, and it
  is what stops the reconcile from silently becoming mandatory.

Nothing in the red root asserts the manifest half at the unit level *and* passes: the
manifest assertion (`test_the_manifest_subscribes_every_conversation_kind`) sits in the
module that could not import, and it is the first thing task 2 turns green.
