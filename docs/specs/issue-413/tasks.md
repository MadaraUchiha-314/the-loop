---
type: tasks
phase: tasks-breakdown
workItem: "github:MadaraUchiha-314/the-loop#413"
status: derived              # tasks.md has no approval gate (issue-281)
---

<!-- Authored per the the-loop:writing skill. -->

# Tasks: the listener measures its own share of the traffic

> Phase 4 of 4. Derived mechanically from [design.md](design.md) and
> [testing-plan.md](testing-plan.md). A DAG: tasks at the same indent are independent.

- [x] **1. `the_loop/channels/splitwatch.py`** — `SPLIT_REMEDY`, `SPLIT_CAVEAT`,
      `SplitState`, `SplitWatch` (`for_config`, `observe`, `run_cycle`), `read_state`,
      `split_state_path`, `split_lines`. Never raises; writes ids, counts and timestamps
      only. _Requirements: R1.4–R1.8, R2.1–R2.6, R4.1, R4.2_ _Test: T1, T2, T3, T4_
  - [x] **1a.** `tests/test_channels_splitwatch.py` — the cycle, the escalation ladder,
        the rolling window, and every refusal. _Test: T1, T2, T3, T4_
- [x] **2. `doctor.central_channel`** — the private resolver made public, and
      `consumer_verdict_text` extended with `SPLIT_REMEDY`, so the doctor and the watch
      say the same sentence. _Requirements: R4.1, R4.2_ _Test: T7_
- [x] **3. `state.StateLayout.slack_split`** — `<root>/local/slack-split.json`, plus its
      `GENERATED_PATHS` entry (local). _Requirements: R2.4_ _Test: T8_
- [x] **4. `eventlog.EVENT_TYPES`** — `channel.split_suspected`,
      `channel.split_cleared`. _Requirements: R2.1, R2.3_ _Test: T8_
- [x] **5. `SlackChannelConfig.split_check_beats`** — the field, `_split_check_beats`'s
      clamping, and the schema entry. _Requirements: R1.4, R1.5_ _Test: T5, T8_
- [x] **6. `run_socket_listener` wiring** — build the watch, feed `observe` from the
      heartbeat branch beside the existing emit, run a cycle at connect and on each
      reconcile deadline, guarded so a cycle never ends the listener.
      _Requirements: R1.1, R1.2, R1.3, R1.7, R1.8_ _Test: T6_
- [x] **7. `status` reports it** — `slackSplit` in `lifecycle.status_all`, `split_line`,
      the `lifecycle_cmd` rows, and `channels.commands.render_status`; `ok` untouched.
      _Requirements: R3.1, R3.2, R3.3, R3.5, R3.6, R3.7_ _Test: T7_
- [x] **8. `channels status` reports it** — the `split check:` line and the `[!]`
      finding. _Requirements: R3.4, R3.6_ _Test: T7_
- [x] **9. Tests** — `tests/test_channels_splitwatch_integration.py` covering T6, T7 and
      the redaction assertions of T9. _Test: T6, T7, T9_
- [x] **10. Docs** — `docs/config/cli/channels-options.md` (the key),
      `docs/cli/commands/status.md` and `docs/cli/commands/channels.md` (the new lines),
      `docs/cli/commands/doctor.md` (the remedy), `docs/cli/state.md` (the state file),
      `docs/guide/slack.md` (the rotation procedure, R4.3),
      `docs/capabilities/channels.md` and `docs/capabilities/observability.md` (the
      capability). _Requirements: R4.3_ _Test: T8_
- [x] **11. Evidence** — verification, security review, self-review, documentation.
      _Test: T9, T10_
