---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#410"
status: in-review            # draft | in-review | approved — locked with design.md at the PR
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: roll running sessions onto a refreshed environment

> Derived from [`requirements.md`](requirements.md) and [`design.md`](design.md).
> Planned at `test-planning`, results recorded at `verification` (below).

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `envstate`: `declared` re-parses the file and never consults `os.environ`; `fingerprint` is stable, truncated and reveals nothing; `compare` names only the differing variables, in name order; `process_environ` reads this test's own pid and returns `None` for a pid that cannot be read | `make test` (`tests/test_envstate.py`) |
| T2 | Unit | yes | `TmuxRunner.respawn_in` builds `respawn-pane -k -t … -c … -e …` with the resume argv, and `spawn_in` folds `env_provider`'s names in behind `_supports_env`, with the-loop's own three names last | `make test` (`tests/test_tmux_runner.py`) |
| T3 | Integration | yes | `restart_sessions` end to end over a registry and a fake runner: one row per outcome (`restarted`, `skipped`, `failed`, `unverified`, `stale`), the exit code each implies, and `--dry-run` touching nothing | `make test` (`tests/test_sessions_restart_integration.py`) |
| T4 | Integration | yes | `environment_drift` and the `status` line: drift counted from live panes, no line when clean, JSON carrying the same facts, `ok` unmoved | `make test` (`tests/test_sessions_restart_integration.py`) |
| T5 | Contract (CLI ↔ docs parity) | yes | the new subcommand and its options are documented; `test_docs_parity` stays green | `make test` |
| T6 | Security / redaction | yes | no declared **value** appears in any message, event-log record or rendered `status`, on any path including every failure path | `make test` (`tests/test_sessions_restart_integration.py`) |
| T7 | End-to-end against real tmux | yes | a real pane respawned in place on a real tmux: the session keeps its name, the new process carries the new value, the old one is gone | `docs/specs/issue-410/evidence/verification.md` (recorded transcript) |
| T8 | Regression (full suite) | yes | every suite stays green; ruff, ruff format, pyright, markdownlint, `validate_config` | `make check` |
| T9 | UI / visual | n/a — no product UI | | |
| T10 | Snapshot | n/a — messages asserted directly (T3) | | |
| T11 | Accessibility | n/a — CLI text only | | |
| T12 | Migration / upgrade | yes | no config key, no state file and no registry field is added, so an existing deployment needs no migration; a deployment with no `env.file` spawns exactly as before (asserted in T2) | with T2/T8 |
| T13 | Manual exploratory | no — T7 covers the only surface the fakes cannot reach | | |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1 | `declared` re-reads the file after it is rewritten, and returns the **new** value while `os.environ` still holds the old |
| T1 | R1.7 | a config naming no `env.file` → `declared` returns `None`, distinct from a file that declares nothing |
| T1 | R5.2 | `fingerprint` of two different values differs, of the same value matches, and its output contains no part of the input |
| T1 | R2.1 | `compare` over equal mappings → `()`; over one differing name → exactly that name |
| T1 | R2.3 | `process_environ(<this pid>)` finds a variable this test exported; `process_environ(<unused pid>)` → `None`, no exception |
| T2 | R1.4 | `respawn_in` argv carries `-k`, the target, the recorded cwd and `--resume <id>` |
| T2 | R4.1 | `spawn_in` with a provider emits `-e NAME=VALUE` for each declared name |
| T2 | R4.2 | `spawn_in` with no provider emits exactly today's argv |
| T2 | R4.3 | a tmux below 3.2 emits no `-e` at all and still spawns |
| T2 | R5.1 | the-loop's own `THE_LOOP_*` names survive an env file that declares them |
| T3 | R1.1, R1.2 | `--all` restarts every live session; a ref restarts that one and leaves the others running |
| T3 | R1.3 | neither `--all` nor a ref → refusal naming both, nothing respawned |
| T3 | R1.5 | a session with no resumable conversation is skipped and its pane is still alive afterwards |
| T3 | R1.6 | a registered but dead session is `skipped: not running`, never spawned |
| T3 | R1.7 | no `env.file` → exit 2, no pane touched |
| T3 | R2.2 | a session whose environment still differs after the respawn → row names the variables, exit 1 |
| T3 | R2.3 | an unreadable environment → `unverified`, exit 0 |
| T3 | R2.4 | `--dry-run` reports the same selection and calls no respawn |
| T3 | R1.5, design § Error handling | a respawned pane that dies inside the probe window → `failed`, exit 1 |
| T4 | R3.1 | two of six running sessions stale → one `status` line naming 2, 6 and the fixing command |
| T4 | R3.2 | every session fresh → `status` prints no environment line |
| T4 | R3.3 | `status --format json` carries `sessionEnvironment` with the per-session rows |
| T4 | R3.4 | environments unreadable → no drift claimed, no failure |
| T4 | R3.5 | drift present → `ok` and the exit code are what they were without it |
| T6 | R5.1, R5.3 | every message, event record and status line from T3/T4 is asserted not to contain any declared value; a differing name appears by name and fingerprint |
| T7 | R1.4, R2.1 | a real `loop-*` session: same session name and window before and after, new pid, new value read back from `/proc` |
| T8 | all | `make check` green |

## Requirements not covered by an automated test

- **R5.1 on the logging path** is asserted over the messages, the event log and the
  rendered status (T6); the assertion is a substring search for each declared value, so
  it covers any path that reaches those three sinks and nothing beyond them. Direct
  `logger` output is read at review — `envstate` holds every value-handling line and is
  small enough to read in full.

## Verification environment

The suite's own fake tmux for T2–T6; a real tmux 3.4 on the development host for T7,
against a scratch `TMUX_TMPDIR` so nothing touches the operator's server.

## Verification results

Recorded at the `verification` gate in
[`evidence/verification.md`](evidence/verification.md).
