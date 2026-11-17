---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#533"
---

# Verification: opt-in session credentials, never on argv

Raw output for the activities in [`testing-plan.md`](../testing-plan.md) § Verification
results. Run on Linux, tmux 3.7c, from `cli/` at the branch head. The
`THE_LOOP_*` session variables were unset, matching CI (see § Environment note).
All test values are dummies; nothing here is a real credential.

## Unit (T1, T8)

```console
$ cd cli && uv run python -m pytest -q tests/test_envstate.py tests/test_tmux_runner.py \
    tests/test_sessioncreds.py tests/test_session_environment.py tests/test_api_session_credentials.py
235 passed in 1.75s
```

## Integration (T2)

Real tmux on a private `TMUX_TMPDIR`, with the server started by the spawn. `-rs`
reports no skips.

```console
$ cd cli && uv run python -m pytest -q -rs tests/test_session_credentials_integration.py \
    tests/test_session_secrets_integration.py
4 passed in 5.68s
```

Scenarios:

- `a spawned session inherits an opted-in credential that no argv or tmux environment holds`:
  pane env, `ps -eo args`, server cmdline and environ, `show-environment -g` and `-t`,
  directory mode, and the file gone.
- `a second session on the same server does not inherit the credential`.
- `rotating the source value marks the session stale`: then respawn reads fresh.
- issue-482's `a spawned server and its pane hold no secret`, unchanged.

## Regression (T10)

```console
$ cd cli && env -u THE_LOOP_CLI_CONFIG -u THE_LOOP_INSTANCE -u THE_LOOP_WORK_ITEM \
    uv run python -m pytest -q
6867 passed, 3 warnings in 233.80s (0:03:53)

$ make validate
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
VALID   skills/the-loop/templates/gateway-config.yaml
… (all VALID)
```

## Static checks (T12)

```console
$ make lint format-check typecheck
All checks passed!                      # ruff
Summary: 0 error(s)                     # markdownlint
517 files already formatted             # ruff format
0 errors, 0 warnings, 0 informations    # pyright
```

## Environment note

The first full-suite runs inside this agent session reported 25 failures. Three were
this change's, and are fixed:

- the authored `.the-loop/cli-config.schema.json` was not synced;
- the new option needed per-key doc headings (docs parity);
- the new state directory was unclassified (state portability).

The other 22 came from the session itself. Its `THE_LOOP_CLI_CONFIG` pointed the
poller, status and instances tests at the operator's live config and running poller.
Unsetting the variables, as CI does, makes them pass.
