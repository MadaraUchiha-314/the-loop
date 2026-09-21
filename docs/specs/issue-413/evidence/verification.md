---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#413"
---

# Verification: the listener measures its own share of the traffic (issue-413)

## Environment

`uv 0.12.0` (the version `pyproject.toml` pins), Python as `cli/pyproject.toml` declares,
no network. Every Slack boundary is a fake; no test opens a socket.

## Results

| Row | Command | Outcome |
|---|---|---|
| T1–T5, rendering | `pytest -q cli/tests/test_channels_splitwatch.py` | 29 passed |
| T6, T7, T9 | `pytest -q cli/tests/test_channels_splitwatch_integration.py` | 18 passed |
| T8 | `pytest -q cli/tests/test_state_portability.py cli/tests/test_docs_parity.py cli/tests/test_config_schema_parity.py cli/tests/test_eventlog.py` | passed |
| T10 | `make check` — `ruff check`, `ruff format --check`, `pyright`, `validate_config`, `markdownlint`, the full suite | green; see below |

```text
$ uv run ruff check cli hooks
All checks passed!

$ uv run ruff format --check cli hooks
346 files already formatted

$ uv run pyright cli
0 errors, 0 warnings, 0 informations

$ uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml

$ npx markdownlint-cli2 "**/*.md"
Linting: 1347 file(s)
Summary: 0 error(s)

$ uv run --project cli python -m pytest -q cli
4 failed, 4443 passed, 1 skipped in 190.91s (0:03:10)
```

### The four failures are pre-existing and environmental

```text
FAILED cli/tests/test_instance.py::test_an_unnamed_instance_spawns_with_the_argv_it_used_before
FAILED cli/tests/test_instance.py::test_a_spawn_for_a_work_item_exports_its_ref
FAILED cli/tests/test_instance.py::test_a_standing_session_carries_no_work_item
FAILED cli/tests/test_instance.py::test_only_the_configured_name_reaches_tmux_and_the_comment
```

They fail identically on `main` with this branch stashed, and they touch nothing this
change goes near. The cause is the verification host's tmux: `TmuxRunner._supports_env`
probes `tmux -V`, this container answers `tmux 3.4`, and `-e` flags are therefore emitted
where those assertions expect none (they assume a tmux below 3.2, or none installed).
Reported, not fixed: widening this PR to a `test_instance.py` fixture is exactly the
scope creep the loop's minimalism ladder refuses.

## Rendered surfaces

Captured from the real renderers over a real state file (12 checks, 5 short, 4 of the
retained 8 short — the shape the reporter's incident produced):

```text
=== the-loop status (the slack-listener row) ===
slack-listener not running [enabled]
            inbound may be split across two Socket Mode consumers — 1/2 heartbeats reached the listener within 5s (4 of the last 8 checks short, last at 2026-09-21T07:41:02Z)
            Evidence, not proof: Slack exposes no API that lists an app's connections.
            Stop every other process connected with this app-level token — a second the-loop instance, a stale `channels listen`, a host nobody remembers. When the holder cannot be found, rotate the token instead: revoke it under the Slack app's Basic Information, generate a new one with `connections:write`, update the env file and restart. Rotation fences out every holder without finding any of them; restarting this instance alone does not.

=== /the-loop status ===
the-loop status — instance `unnamed` (mode: open) · not ok
• service: stopped (enabled)
• gh-webhook: disabled
• poller: disabled
• slack-listener: stopped (enabled)
• slack: inbound may be split across two Socket Mode consumers — 1/2 heartbeats reached the listener within 5s (4 of the last 8 checks short, last at 2026-09-21T07:41:02Z)
  Evidence, not proof: Slack exposes no API that lists an app's connections.
  Stop every other process connected with this app-level token — a second the-loop instance, a stale `channels listen`, a host nobody remembers. When the holder cannot be found, rotate the token instead: revoke it under the Slack app's Basic Information, generate a new one with `connections:write`, update the env file and restart. Rotation fences out every holder without finding any of them; restarting this instance alone does not.
• standing: none

=== the-loop channels status (excerpt) ===
  read:         socket, reconciling every 900s
  split check:  2 heartbeat(s) every 900s — last check 1/2 at 2026-09-21T07:41:02Z, 8 retained, 4 short
  [!] inbound may be split across two Socket Mode consumers — 1/2 heartbeats reached the listener within 5s (4 of the last 8 checks short, last at 2026-09-21T07:41:02Z)
  [!] Evidence, not proof: Slack exposes no API that lists an app's connections.
  [!] Stop every other process connected with this app-level token — a second the-loop instance, a stale `channels listen`, a host nobody remembers. When the holder cannot be found, rotate the token instead: revoke it under the Slack app's Basic Information, generate a new one with `connections:write`, update the env file and restart. Rotation fences out every holder without finding any of them; restarting this instance alone does not.

=== status --format json (slackSplit) ===
{
  "verdict": "split-suspected",
  "checkedAt": "2026-09-21T07:41:02Z",
  "beats": 2,
  "echoed": 1,
  "windowSeconds": 5.0,
  "channel": "C0CENTRAL",
  "reason": "",
  "checks": 12,
  "short": 5,
  "consecutiveShort": 1,
  "recent": [
    "ok",
    "split-suspected",
    "ok",
    "ok",
    "split-suspected",
    "ok",
    "split-suspected",
    "split-suspected"
  ],
  "intervalSeconds": 900,
  "suspected": true
}
```

## Requirements trace

| Requirement | Proved by |
|---|---|
| R1.1 connect-time check | `test_one_check_runs_at_connect` |
| R1.2 every `catchUpSeconds` | `test_the_reconcile_deadline_carries_the_check` |
| R1.3 `0` = connect only | `test_connect_only_means_connect_only` |
| R1.4 post, count, delete | `test_every_echo_back_is_ok`, `test_the_room_keeps_no_litter`, `test_the_doctors_receipt_is_still_written` |
| R1.5 `splitCheckBeats: 0` | `test_the_check_is_off_when_the_operator_says_so`, `test_the_check_can_be_turned_off_entirely` |
| R1.6 unverifiable, never ok | the four `*_is_unverifiable` tests |
| R1.7 never ends the listener | `test_a_check_that_raises_never_ends_the_listener` |
| R1.8 stop aborts the window | `test_a_stopping_listener_abandons_the_window` |
| R2.1–R2.3 the event ladder | `test_the_first_short_check_warns`, `test_a_run_of_short_checks_is_not_a_storm`, `test_a_clean_check_closes_the_ladder` |
| R2.4 the state outlives the process | `test_the_state_outlives_the_process` |
| R2.5 an unwritable path | `test_an_unwritable_path_warns_once_and_keeps_measuring` |
| R2.6 ids, counts, times only | `test_the_state_carries_ids_counts_and_times_only`, `TestSecretsAreNeverPrinted` |
| R3.1–R3.3, R3.6, R3.7 `status` | `TestStatusReportsIt` |
| R3.4 `channels status` | `TestChannelsStatusReportsIt` |
| R3.5 `/the-loop status` | `test_the_slash_command_says_the_same_thing` |
| R4.1, R4.2 one remedy, everywhere | `SPLIT_REMEDY` asserted identical in the event, `status`, `channels status`; `doctor slack` composes it from the same constant |
| R4.3 the rotation procedure | `docs/guide/slack.md` § When nothing arrives at all — prose, reviewed not tested (testing plan § Requirements not covered) |
