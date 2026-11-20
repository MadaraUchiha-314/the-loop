# End to end: real hooks, real tmux, stub harness (T4)

Run on 2026-11-20 at `82db8f0a`, from `cli/`, with `THE_LOOP_CLI_CONFIG`,
`THE_LOOP_INSTANCE` and `THE_LOOP_WORK_ITEM` unset. A daemon-spawned session exports
those, and with them set some unrelated status tests read the live daemon.

| Row | Command | Result |
|---|---|---|
| T4 | `uv run python -m pytest -q tests/test_idle_watchdog_e2e.py` | 1 passed in 8.44s |

Five consecutive runs during implementation took 8.88, 8.88, 8.34, 8.44 and
8.44 seconds, all passing.

## What the run does

1. Starts its own control-plane service on a free loopback port with a temporary
   config, state root, registry and event log. No ingress is enabled.
2. Starts a private tmux server on its own socket and a stub harness in a pane.
3. Asserts, in order:
   - the stop is refused, naming the node, with the pointer past an approved
     human gate (the P3 regression, end to end);
   - after the hook's attempt cap the stop is allowed and `session.turn_ended`
     carries `gate-gave-up`;
   - past the idle threshold, the real watcher pastes the nudge into the pane, and
     the turn-start hook records `session.turn_started`;
   - the budget runs out: two `session.nudged`, one `session.stalled`, then
     nothing over further cycles;
   - a later prompt starts a turn and the next cycle records `session.stall_ended`.

## Isolation

The test drops every `THE_LOOP_*` and `TMUX*` variable from its children, asserts
the service's `/health` reports the test's own state root before any pane exists,
and reaches tmux only through a shim that carries the private socket. The
operator's sessions were the same before and after each run.

## Limit of this proof

Event records carry real timestamps and only the watcher's clock is moved, so the
run proves order and counts, not the reported idle durations. Those are covered by
the unit tests of the derivation.
