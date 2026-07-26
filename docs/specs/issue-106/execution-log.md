---
type: execution-log
workItem: "issue-106"
phase: implementation
status: in-progress
---

# Execution Log: authorized execution control + one state root

> Append-only log of progress for the user's visibility. Checked in alongside
> the spec at `docs/specs/issue-106/`.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-07-26 |  | Issue #106: the auto-execute label alone starts an autonomous session; there is no vocabulary an authorized user can use to start/stop/pause/resume, no CLI parity, and generated state is scattered across four defaults. |
| design | 2026-07-26 |  | Shared `control.py` vocabulary + durable store; `paused` as a live registry status; one interception point in the dispatcher; poller stops arming unstarted items; `state.py` root supplying every generated-path default. |
| tasks-breakdown | 2026-07-26 |  | 13-task DAG |
| implementation | 2026-07-26 |  | On `claude/github-issue-106-dgln9f` |
| needs-review |  |  |  |
| complete |  |  |  |

## Progress entries

### 2026-07-26 — investigation + spec drafted

- **Phase:** requirements-definition → design → tasks-breakdown
- **Did:** Traced both ingress paths against the issue. Found that the only
  gates today are `routing.authorizedUsers` (who) and the auto-execute label
  (which item) — nothing expresses *when*, so labelling is an irreversible
  trigger and a comment can only ever become harness input, never a daemon
  action. Designed a fixed, configured four-word vocabulary parsed downstream of
  the existing self-marker and authorization guards, a durable per-work-item
  control record that makes a start request survive restarts, `paused` as a
  live registry status, and one `state.root` supplying the defaults of every
  generated path (with a legacy fallback so the moved poll state never
  re-baselines a watched thread).
- **Next:** implement the DAG in `tasks.md`.

### 2026-07-26 — implementation complete

- **Phase:** implementation
- **Did:** All 13 tasks. New `the_loop.control` (vocabulary, parser, durable
  `ControlStore`), `the_loop.state` (one generated-state root), `the_loop.comments`
  (the shared `gh` comment poster the announcer now uses too). `paused` became a live
  registry status; the dispatcher gained one control interception point, a paused
  delivery gate, a `close_session` shared by the close event and `stop`, and a spawn
  gate that requires a recorded start; the poller stopped arming presence for
  unstarted items so `requireStartCommand` cannot burn the issue-80 retry budget; the
  CLI gained `sessions start|pause|resume|stop` with the paper-trail comment.
  Schema + both shipped cli-config YAMLs + `cli/README.md` document `state` and
  `routing.control`.
- **Tests:** 4 new files (`test_control.py`, `test_control_integration.py`,
  `test_control_cli.py`, `test_state.py`, `test_comments.py`) plus registry
  pause/resume cases. Existing spawn-mechanics tests opt out of the start gate
  explicitly (`control=ControlConfig(require_start_command=False)`) — the documented
  behaviour change is asserted by the new integration tests instead.
- **Next:** reviewer briefing on the PR; tier-4 → human approves.

### 2026-07-26 — review round 1 (owner, PR #107)

- **Phase:** needs-review
- **Feedback:** open question 3 answered — a start on a work item that is *not*
  armed must leave nothing standing: `start` (unlabelled) → label added → nothing
  should happen; only a start issued *while* the item is armed starts it.
  Also confirmed: everything here is for **commands** only; an ordinary comment
  from an authorized user keeps being auto-forwarded to a running harness.
- **Did:** Made the record asymmetric — an **arming** command (`start`/`resume`)
  is recorded only when it actually acts, a **disarming** one (`pause`/`stop`)
  always. A start is now refused *before* anything is written (the armed check
  moved ahead of the record), a resume with nothing to resume records nothing,
  and a CLI start whose spawn fails clears its own record. The gate learned to
  accept a start carried by *this* event, so the durable record is only ever
  consulted for later events (poll retry, redelivery). Requirements 2.4/2.5/3.6
  updated, plus the design, capability doc, README and event catalog.
- **Tests:** the owner's exact three-step sequence, the resume variant, the
  disarming counter-case, and the CLI equivalent.
