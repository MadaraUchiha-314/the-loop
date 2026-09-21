---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#413"
status: in-review            # draft | in-review | approved — locked with design.md at the PR
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: the listener measures its own share of the traffic

> Derived from [`bugfix.md`](bugfix.md) and [`design.md`](design.md). Planned at
> `test-planning`, results recorded at `verification` (below).

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `SplitWatch.run_cycle` against a fake client: every beat echoed → `ok`; a beat withheld → `split-suspected`; every posted heartbeat deleted; the window aborts on the stop event | `make test` (`tests/test_channels_splitwatch.py`) |
| T2 | Unit | yes | the escalation ladder: warning on the first short check, silence until the `ESCALATE_EVERY`th, `channel.split_cleared` and a reset on the next clean one | `make test` (`tests/test_channels_splitwatch.py`) |
| T3 | Unit | yes | `SplitState` round-trips through the file; `recent` keeps `RETAINED` newest; `suspected()` is true while any retained check is short and false after a full clean window; a corrupt or absent file reads as `None` | `make test` (`tests/test_channels_splitwatch.py`) |
| T4 | Unit | yes | the refusals: no channel, no bot token, a channel that resolves to nothing, and a client that raises — each `unverifiable` with a reason, never `ok`, never raising | `make test` (`tests/test_channels_splitwatch.py`) |
| T5 | Unit | yes | `_split_check_beats` clamps: non-integer and negative → default with a warning; `0` → off; above the cap → the cap | `make test` (`tests/test_channels.py`) |
| T6 | Integration | yes | `run_socket_listener` end to end over the fake Socket Mode client: a cycle at connect, one per reconcile deadline, `observe` fed from the heartbeat branch, `channel.heartbeat` still emitted for the doctor, and a raising cycle that does not end the listener | `make test` (`tests/test_channels_splitwatch_integration.py`) |
| T7 | Integration | yes | the surfaces: `status` prints the report and carries `slackSplit` in JSON while suspected, prints nothing when clean or unwritten, and leaves `ok` and the exit code unmoved; `channels status` prints `[!]` when short and the cadence line when not; `/the-loop status` carries the same line | `make test` (`tests/test_channels_splitwatch_integration.py`) |
| T8 | Contract (catalog + docs + schema parity) | yes | both event types are in `EVENT_TYPES`; the new config key is in the schema and documented; `slack_split` is classified in `GENERATED_PATHS` and `docs/cli/state.md`; `test_docs_parity`, `test_config_schema_parity` and `test_state_portability` stay green | `make test` |
| T9 | Security / redaction | yes | no token value, and no part of one, appears in the state file, either event record, or any rendered line — asserted on the clean, short and unverifiable paths | `make test` (`tests/test_channels_splitwatch_integration.py`) |
| T10 | Regression (full suite) | yes | every suite stays green; ruff, ruff format, pyright, markdownlint, `validate_config` | `make check` |
| T11 | End-to-end against real Slack | no | needs a workspace and a deliberate second consumer; the incident transcript in the ticket is the field evidence, and T6 reproduces the split by withholding an echo | |
| T12 | UI / visual | n/a — no product UI | | |
| T13 | Accessibility | n/a — CLI text only | | |
| T14 | Migration / upgrade | yes | an existing deployment needs no migration: the config key is additive with a working default, and an absent state file renders nothing | with T7/T10 |
| T15 | Manual exploratory | no — every surface is asserted directly | | |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.4 | a cycle posts exactly `beats` messages, counts the echoes it observed, and deletes each `ts` it got back |
| T1 | R1.4 | one echo withheld → `verdict: split-suspected`, `echoed` one short of `beats` |
| T1 | R1.8 | a stop event set during the window ends the wait inside one poll interval and writes nothing |
| T2 | R2.1 | the first short check emits `channel.split_suspected` at `warning` with beats, echoed, window, channel and `consecutiveShort: 1` |
| T2 | R2.2 | short checks 2…5 emit nothing; check 6 emits again |
| T2 | R2.3 | a clean check after a short one emits `channel.split_cleared` at `info` and resets the counter |
| T3 | R2.4 | the state written by one cycle is the state the next process reads |
| T3 | R2.4, design § Data models | `recent` holds the newest 8; the 9th append drops the oldest |
| T3 | R3.1, R3.2 | `suspected()` true on a clean check that follows a short one; false once 8 clean checks have passed |
| T3 | R2.5 | an unwritable path warns once and the cycle still returns its state |
| T4 | R1.6 | no `channels.slack.channel` → `unverifiable`, reason names the key, nothing posted |
| T4 | R1.6 | a name that resolves to no conversation → `unverifiable`, nothing posted |
| T4 | R1.5 | `splitCheckBeats: 0` → `for_config` returns `None`, nothing posted, no state written |
| T4 | R1.7 | a client whose `chat_postMessage` raises → `unverifiable` with the exception text, no raise out |
| T5 | R1.4 | `splitCheckBeats: "many"` and `-1` → the default, one warning each; `9` → the cap |
| T6 | R1.1 | the listener runs one cycle between `catch_up` and its first tick |
| T6 | R1.2 | with `catchUpSeconds` reached, the next cycle runs beside the reconcile |
| T6 | R1.3 | `catchUpSeconds: 0` → exactly one cycle, at connect |
| T6 | R1.4, R2.1 | a heartbeat arriving on the socket handler is observed by the watch **and** emitted as `channel.heartbeat`, so `doctor slack` still reads it |
| T6 | R1.7 | a `run_cycle` that raises is logged and the listener keeps serving envelopes |
| T7 | R3.1 | a written short state → one `slack` report in `the-loop status` naming beats, echoed, the recent window and the remedy |
| T7 | R3.2 | a clean state, and no state file at all → no report |
| T7 | R3.3 | `status --format json` carries `slackSplit` with the same counts |
| T7 | R3.4 | `channels status` prints `[!]` while suspected and the cadence + last verdict otherwise |
| T7 | R3.5 | `render_status` (the slash command) carries the same sentence |
| T7 | R3.6 | every rendered report contains the evidence-not-proof caveat |
| T7 | R3.7 | a suspected split leaves `status`'s `ok` `true` and its exit code `0` |
| T7 | R4.1, R4.2 | the remedy string in the event, `status`, `channels status` and `doctor slack` is byte-identical and names both stopping and rotating |
| T8 | R2.1, R2.3 | `channel.split_suspected` and `channel.split_cleared` are in `EVENT_TYPES` |
| T8 | R1.4 | `channels.slack.read.splitCheckBeats` is in the schema and has a documented Type and Default |
| T8 | R2.4 | `StateLayout.slack_split` is classified local in code and in `docs/cli/state.md` |
| T9 | bugfix § Security | neither token value appears in the state file, the two event records, or any line of the three rendered surfaces |
| T10 | all | `make check` green |

## Requirements not covered by an automated test

- **R4.3** (the rotation procedure in the Slack guide) is prose; its presence is checked
  by review, not by a test. A test asserting that a paragraph exists would pin wording
  without pinning correctness.
- **A real second consumer.** T6 reproduces the split by withholding an echo, which is
  what a split does to this process; that the *cause* is Slack's load balancing is the
  incident transcript's evidence and Slack's documented behaviour, neither of which a
  test in this repository can restate.

## Verification environment

`make check` on the repository checkout: `uv` (pinned `>=0.12,<0.13`), Python as
`cli/pyproject.toml` declares, no network. Every Slack interaction is a fake client; no
test opens a socket.

## Evidence to capture

- the full `make check` transcript (`evidence/verification.md`);
- the rendered `the-loop status`, `channels status` and `/the-loop status` output for a
  suspected split, captured from the tests;
- the security review (`evidence/security-review.md`) and the documentation record
  (`evidence/documentation.md`).

## Activities checklist

- [x] test matrix agreed and traced to requirements
- [x] tests written before the code they cover (TDD)
- [x] `make check` green
- [x] evidence recorded under `evidence/`
- [x] results table below completed at `verification`

## Results

Recorded at the `verification` node — see
[`evidence/verification.md`](evidence/verification.md).

| Row | Command | Outcome | Artifact |
|-----|---------|---------|----------|
| T1–T5 | `uv run --project cli python -m pytest -q cli/tests/test_channels_splitwatch.py` | pass | `evidence/verification.md` |
| T6, T7, T9 | `uv run --project cli python -m pytest -q cli/tests/test_channels_splitwatch_integration.py` | pass | `evidence/verification.md` |
| T8 | `uv run --project cli python -m pytest -q cli/tests/test_docs_parity.py cli/tests/test_config_schema_parity.py cli/tests/test_state_portability.py cli/tests/test_eventlog.py` | pass | `evidence/verification.md` |
| T10 | `make check` | pass | `evidence/verification.md` |
