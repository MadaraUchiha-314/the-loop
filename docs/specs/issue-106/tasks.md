---
type: tasks
phase: tasks-breakdown
workItem: "issue-106"
status: draft
approvedBy: []
collaborators: [engineer]
overrides: {}
---

# Tasks: authorized execution control + one state root

> Phase 3 of 3 (requirements → design → tasks). DAG — a task starts once its
> dependencies are checked.

- [x] **T1 — the vocabulary.** `the_loop/control.py`: `ControlConfig`
  (`enabled`, `requireStartCommand`, `keywords`, `ghBinary`), `parse_command`
  with whole-token matching and ambiguity refusal, `command_comment` body
  builder. *(AC1.1, AC1.3, AC1.4, AC1.7, AC4.2)* — depends on nothing.
- [x] **T2 — the durable record.** `the_loop/control.py`: `ControlRecord` +
  `ControlStore` (file per work item under `<sessions>/control/`, atomic
  writes, `start_requested`). *(AC2.5, AC3.6)* — depends on T1.
- [x] **T3 — paused sessions.** `sessions/registry.py`: `paused` status,
  `pause()`/`resume()`, live lookup (`active|paused`), `session.paused` /
  `session.resumed` events. *(AC3.1, AC3.7, AC6.2)* — depends on nothing.
- [x] **T4 — state root.** `the_loop/state.py`: `StateLayout` +
  `layout_from_config`; consumers fall back to it (registry dir, control dir,
  poll state, event log, pidfile); legacy poll-state fallback with a one-time
  warning. *(AC5.1–AC5.6)* — depends on nothing.
- [x] **T5 — dispatcher control path.** `webhook/dispatcher.py`: `ControlConfig`
  on `RoutingConfig` (hot-reloading), `_control_command`, `_apply_control`,
  `_close_session` factored out of the close branch, paused-delivery drop,
  close-a-paused-session. *(AC1.2, AC1.5, AC1.6, AC3.2–AC3.5, AC3.8, AC6.1)* —
  depends on T1, T2, T3.
- [x] **T6 — spawn gate.** `webhook/dispatcher.py`: `_should_spawn` requires a
  start request when `requireStartCommand`; label check recomputed from the
  payload so the poll path's comment events are gated identically;
  `control.rejected` on a refusal. *(AC2.1–AC2.4, AC2.6, AC2.7)* — depends on T5.
- [x] **T7 — poller arming.** `poller/poller.py` + `commands/poll.py`: the
  poller takes the control config/store and does not arm presence spawns for an
  item nobody started. *(AC2.1, AC2.3)* — depends on T2, T6.
- [x] **T8 — comment helper.** `the_loop/comments.py`: `post_issue_comment`
  (best-effort `gh`, injectable runner); `announce.py` refactored onto it.
  *(AC4.2–AC4.4)* — depends on nothing.
- [x] **T9 — CLI control actions.** `commands/sessions_cmd.py`:
  `start|stop|pause|resume` sharing one implementation — local effect (spawn via
  a dispatcher built from config for `start`), control record, paper-trail
  comment, `--no-comment`; `list` gains the control column and `--status
  paused`. *(AC4.1, AC4.5–AC4.7)* — depends on T2, T3, T5, T8.
- [x] **T10 — event catalog.** `eventlog.py`: `control.command`,
  `control.rejected`, `control.ambiguous`, `session.paused`, `session.resumed`;
  `dispatch.dropped` reason list extended. *(AC6.2)* — depends on nothing.
- [x] **T11 — config surface.** `.the-loop/cli-config.schema.json` (`state`,
  `routing.control`), `.the-loop/cli-config.yaml`, `cli/README.md`. *(AC5.6,
  AC6.1)* — depends on T1, T4.
- [x] **T12 — tests.** Unit + Gherkin-documented integration tests per the
  design's testing strategy. *(all ACs)* — depends on T1–T10.
- [x] **T13 — docs.** Capability docs (`webhook-triggers`, `cli`,
  `interactive-sessions`), decision record, execution log, upgrade note for the
  `requireStartCommand` default. *(AC6.3)* — depends on T1–T11.
