---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#529"
---

# Unit tests (T1): the reply renderer

Run on the branch at 43c83f4 plus the ruff reformat, from `cli/`, with the session's
`THE_LOOP_*` variables unset. Those variables point the CLI at this machine's live
instance, and tests that read the ambient config fail under them. That happens on
`main` too, and is unrelated to this change.

## `uv run python -m pytest -q tests/test_channels_buttons.py`

```text
35 passed in 0.93s
```

Red → green: before task 1's code, the module failed at collection
(`ImportError: cannot import name 'COMMAND_DESCRIPTIONS'`).
