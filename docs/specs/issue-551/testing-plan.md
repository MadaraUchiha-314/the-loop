---
type: testing-plan
phase: test-planning
workItem: issue-551
status: approved
approvedBy: ["MadaraUchiha-314"]
overrides: {}
---

# Testing plan: a session never goes idle unnoticed

> Derived from the approved [`requirements.md`](requirements.md) and
> [`design.md`](design.md), before `tasks.md`. Authored at `test-planning` and
> completed at `verification`.
>
> **This file is executable content.** Review it like code. Credentials appear by
> reference only.

## The short version

The proof rests on three rows.

- **T1 (unit)** proves the two pure decisions: the state of a session, and the stop
  check. Every arrow of the design's state diagram and every step of the stop-check
  order has a test.
- **T2 (integration)** drives the watcher with a fake clock and a fake tmux runner
  through eleven named scenarios.
- **T4 (end to end)** runs the real hook scripts and the real watcher against a real
  tmux session that hosts a stub harness.

One thing cannot be proved before merge: a stall on a real harness, because the
daemon that drives this session runs the released code. T11 says how that is
reported after merge.

Check that each abuse case has a row in T8, and that the commands are ones you would
let an agent run.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | Session-state derivation, one test per transition (R4, R7). Stop-check order, steps 1–6, with "one wait covers one stop" (R3). Duration parsing and the minimum-wait raise (R6.5, R6.6). The nudge budget of a node visit (R4.3, R4.4). The claim envelope's `assignment` and `next` (R1). Config defaults and validation. Event names registered. | `cd cli && uv run python -m pytest -q tests/test_session_state.py tests/test_stop_check.py tests/test_durations.py tests/test_graph_claim_assignment.py tests/test_configschema.py tests/test_eventlog.py` |
| T2 | Integration (scenario) | yes | The watcher, the dispatcher and the claim path together, with a fake clock, a recording tmux runner and recording channels. Each test has a Gherkin docstring and a `Requirement:` link. | `cd cli && uv run python -m pytest -q tests/test_watchdog_integration.py tests/test_ask_deadline_integration.py tests/test_inbound_readonly_integration.py tests/test_gate_pointer_integration.py` |
| T3 | Contract (OpenAPI) | yes | The four changed or new endpoints and the changed responses are in `docs/api-specs/openapi/the-loop.v1.yaml`, and the routes match it. | `cd cli && uv run python -m pytest -q tests/test_api_contract_parity.py` |
| T4 | End-to-end (real tmux, stub harness) | yes | The shipped hook scripts, the service and the watcher in one run. A stub harness in a tmux pane fires the turn-start and Stop hooks as a harness would. Covers: a refused stop, a stop allowed after the cap, a nudge pasted into the pane, the notice, the stall's end. | `cd cli && uv run python -m pytest -q tests/test_idle_watchdog_e2e.py` |
| T5 | UI / visual | yes | The mock-up as locked. The rendered notice, reminder and "default taken" texts from T2 match its wording. | mock-up rendered with headless Chromium; wording asserted in T2 |
| T6 | Snapshot | n/a — message wording is asserted through the strings in T2. A byte snapshot of channel payloads would break on unrelated field changes. | | |
| T7 | Performance | yes (bounded) | One watcher cycle over 50 sessions and a 50,000-line event log finishes within 2 seconds, so a 30-second tick never overlaps itself. | part of T1 (`tests/test_session_state.py -k cycle_budget`) |
| T8 | Security / abuse case | yes | One negative test per abuse case 1–7 of `design.md` § Security design, plus: a hook verb naming another work item is refused; the nudge contains no ticket, comment or default text. | `cd cli && uv run python -m pytest -q -k "abuse or unauthorized or foreign_work_item or nudge_is_fixed"` |
| T9 | Accessibility | yes (narrow) | Every new Slack message's `text` fallback is its short form, and each state is named in words. | part of T2 |
| T10 | Migration / upgrade | yes | A config with neither new block loads with the defaults. A hook from this plugin against a CLI without `stop-check` falls back to `check` and still applies the P3 fix. An event log written before this change yields "not watched" and no nudge. A state file holding a `lastBlock` from an old comment clears on the next advance. | part of T1/T2 (`tests/test_harness_gate.py`, `tests/test_session_state.py -k legacy`) |
| T11 | Manual exploratory | n/a at verification — a stall on a real harness needs the daemon to run this code, which happens only after merge and release. T4 proves the path with a stub harness. After merge, the first real nudge or "default taken" on a work item is reported on the ticket with its event-log lines. | | |
| T12 | Skill and docs | yes | The skill no longer says a daemon session ends at a boundary (R2.2), and lists the legitimate stops (R2.3). The docs parity tests pass. | `grep -rnE "next session starts fresh\|ending the session at a phase" skills/ commands/ docs/capabilities/` returns nothing (the `\|` is this table's escape for a plain pipe); `cd cli && uv run python -m pytest -q tests/test_docs_parity.py` |
| T13 | Full suite and lint (CI parity) | yes | Nothing else regresses; markdown, types and lint pass. | `uv run pre-commit run --all-files` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1–R1.4, R1.6 | envelope carries the assignment and `next` for an agent node; `continue: false` and the gate's name for a human node; the last node only after routed skips; absent when the pointer did not move |
| T1 | R3.1–R3.7 | each stop-check step; a `wait` human gate before the pointer counts as passed; a `block` agent node before the pointer refuses; unresolvable item allows |
| T1 | R3.2.3, R4.7, R4.8 | a wait made in this turn allows one stop; the same wait does not allow the next; a wait over the limit is refused; idle starts at the wait's end |
| T1 | R4.1–R4.6, R4.9 | working → waiting → idle → stalled → notified → working; the budget carries across idle periods on one node and resets when the pointer moves or a person's event is delivered |
| T1 | R6.5, R6.6 | a short wait is raised to the minimum and reported; `--after` without `--default` fails |
| T1 | R7.1–R7.3 | the `session` object of `check` and the attention rows for each state |
| T1 | NFR events, config | all nine event names registered; defaults; a non-positive value fails validation |
| T2 | R1.1, R1.2 | `Scenario: a claim returns the next assignment and says to continue` |
| T2 | R1.5 | `Scenario: an advance the daemon drives delivers the assignment once` |
| T2 | R3.3, P3 regression | `Scenario: a stop with work owed is refused past an approved gate` |
| T2 | R3.2.2 | `Scenario: a stop with an open ask is allowed` |
| T2 | R3.6, R3.8 | `Scenario: the gate gives up after its attempts and records why` |
| T2 | R4.1–R4.4 | `Scenario: an idle session is nudged, then a person is told once` |
| T2 | R4.5, R7.5 | `Scenario: a stall ends when the session takes a turn, and the notice is edited` |
| T2 | R4.10 | `Scenario: a restart repeats no nudge and no notice` |
| T2 | R4.12 | `Scenario: a switched-off watchdog sends nothing and the gate still holds` |
| T2 | R5.1, R5.6 | `Scenario: a comment does not block an agent node` |
| T2 | R5.2 | `Scenario: a met exit gate still advances on a comment` |
| T2 | R5.3 | `Scenario: a human gate still classifies the comment it receives` |
| T2 | R6.1, R6.2, R6.10 | `Scenario: a default is taken at its deadline, once, across a restart` |
| T2 | R6.3, R6.4 | `Scenario: an answer cancels the default`; `Scenario: an answer after the default still reaches the session` |
| T2 | R6.7 | `Scenario: a question with no default is reminded once` |
| T2 | R7.4 | `Scenario: the stall notice is a short form in the work item's conversation` |
| T3 | R1.6, R4.7, R6.1, R7 | contract parity for the ask, wait, stop-check, turn-start, claim, check and attention shapes |
| T4 | R3, R4, R4.11 | hook → service → event log → watcher → tmux pane, with no ingress running |
| T8 | abuse 1–7, R6.8 | one test each, as named in `design.md` § Security design |
| T12 | R2.1–R2.4, R6.9 | the skill text |

## Verification environment

- **Repositories:** this repository only, at the pull request's branch.
- **Offline (T1–T3, T5, T7–T10, T12, T13):** no services. Run `uv sync --locked`
  once, then the commands in the matrix from the repository root, as CI does.
- **End to end (T4):**
  - **Needs:** `tmux` on the path. The test skips with a stated reason where it is
    missing, and a skip leaves T4 unticked.
  - **Isolation:** the test starts its own control-plane service on a free port with
    a temporary state root, and its own tmux server on a private socket. It never
    touches the operator's daemon, registry, event log or tmux sessions.
  - **Stub harness:** a small script under `cli/tests/` that reads pasted prompts and
    runs the plugin's hook scripts from this checkout at turn start and turn end.
  - **Bring-up and tear-down:** inside the test's fixtures. The tmux server and the
    service are killed on exit, also after a failure.
- **Credentials:** none. No row calls GitHub or Slack; channels are recording fakes.
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T7, T10 | test summary and the named cases; the red-to-green run for the P3 regression | `unit.md` |
| T2, T9 | run output and the scenario table | `integration.md` |
| T3 | contract parity output | `contract.md` |
| T4 | run output, plus the event-log lines of one run (refs only, no hostnames) | `e2e.md` |
| T5 | screenshot of the locked mock-up | `ui/mockup.png` |
| T8 | run output with the abuse case each test covers | `security-tests.md` |
| T12 | the grep and the parity output | `documentation-check.md` |
| T13 | pre-commit summary | `ci-parity.md` |

## Verification activities

- [ ] T1 — `cd cli && uv run python -m pytest -q tests/test_session_state.py tests/test_stop_check.py tests/test_durations.py tests/test_graph_claim_assignment.py tests/test_configschema.py tests/test_eventlog.py`
- [ ] T2 — `cd cli && uv run python -m pytest -q tests/test_watchdog_integration.py tests/test_ask_deadline_integration.py tests/test_inbound_readonly_integration.py tests/test_gate_pointer_integration.py`
- [ ] T2 — `uv run the-loop scenarios --root "$PWD" --glob 'cli/tests/test_*_integration.py' --format markdown` (the scenarios above appear)
- [ ] T3 — `cd cli && uv run python -m pytest -q tests/test_api_contract_parity.py`
- [ ] T4 — `cd cli && uv run python -m pytest -q tests/test_idle_watchdog_e2e.py`
- [ ] T5 — render `docs/specs/issue-551/design/messages.html` with headless Chromium and save the screenshot
- [ ] T8 — `cd cli && uv run python -m pytest -q -k "abuse or unauthorized or foreign_work_item or nudge_is_fixed"`
- [ ] T10 — the migration cases pass within T1/T2 (named in `unit.md`)
- [ ] T12 — `grep -rnE "next session starts fresh|ending the session at a phase" skills/ commands/ docs/capabilities/` returns nothing; `cd cli && uv run python -m pytest -q tests/test_docs_parity.py`
- [ ] T13 — `uv run pre-commit run --all-files`

## Verification results

_Not yet executed._

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| | | | |

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed: an approval never silently
> discards a reviewer's suggestions, and the feedback travels with the document
> it concerns rather than living in a side-channel tracker.

### 2026-11-20 — approved

**@MadaraUchiha-314** wrote:

approved
