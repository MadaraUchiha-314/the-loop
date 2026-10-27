# Full check — T12

`make check` (lint, format-check, typecheck, validate, test), exit 0:

```text
All checks passed!
Summary: 0 error(s)
511 files already formatted
6789 passed, 2 warnings in 232.68s (0:03:52)
```

## Environment note

The first run, inside the daemon-spawned session, failed 22 tests in `test_poll_status.py`, `test_poll_command.py`, `test_instances_cmd.py`, `test_lifecycle_cmd.py`, `test_critics.py` and `test_ask_reply_integration.py`: the session inherits `THE_LOOP_CLI_CONFIG`, `THE_LOOP_INSTANCE` and `THE_LOOP_WORK_ITEM`, so those tests read the operator's live config and gateway. None touches `record-feedback`. With the three variables unset the same 22 pass, and the full run above is green.
