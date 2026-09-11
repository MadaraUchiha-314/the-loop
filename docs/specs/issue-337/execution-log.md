---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#337"
phase: needs-review
status: in-progress
---

# Execution Log: an Execute button (and a Start button) on the Slack messages that expect the keyword, the outcome shown on the message, and a `channels status` that says how to turn buttons on

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-09-11 | — | Tier 3 (`human-approves-pr`; below `humanSignOffMinTier: 4`): two Block Kit buttons whose press rides the existing pipeline under the existing `control.command` grant, an edit of the pressed message, a longer status line; no schema key, no new grant, no new scope. Brainstorming skipped: the ticket and the owner's comment are the requirement. No authorized `the-loop execute` reaches this cloud session, so the selection is recorded here and every phase is walked |
| requirements-definition | 2026-09-11 | | [`requirements.md`](requirements.md) — four requirements, seven abuse cases |
| design | 2026-09-11 | | [`design.md`](design.md) — the renderer's `commands`, `report_press`, the status steps; [`decision-117`](../../decisions/decision-117.md) |
| test-planning | 2026-09-11 | | [`testing-plan.md`](testing-plan.md) — thirteen rows, six applicable |
| tasks-breakdown | 2026-09-11 | | [`tasks.md`](tasks.md) — seven tasks |
| implementation | 2026-09-11 | | On `claude/github-issue-337-8kq481` |
| verification | 2026-09-11 | | [`evidence/verification.md`](evidence/verification.md) — rows T1, T2, T8, T10, T12; [`evidence/security-review.md`](evidence/security-review.md) — seven abuse cases, seven closed |
| needs-review | 2026-09-11 | | PR raised; awaiting the owner (tier 3: `human-approves-pr`) |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| | | |

## Progress entries

### 2026-09-11 — implemented, verified, ready for review

- **Phase:** implementation → verification → needs-review
- **Did:** tasks 1–7, red first (`test_channels_buttons.py` did not import against
  `a8acc96`; the four scenarios failed on the absent buttons and the missing
  `chat_update` path). `channels/slack.py`: `COMMAND_BUTTONS`, `BUTTON_NAMES`,
  `PHASE_SELECTION_MARKER` (pinned to the hook's constant); `control_keywords` on the
  config with `command_buttons` / `keyword` / `command_buttons_for`;
  `expected_commands` keyed on the checklist marker; `render_blocks(commands=)`
  rendering one primary button per command with the configured keyword as its value;
  `render_reply_blocks`; `say(blocks=)`; `report_press` rebuilding the pressed message's
  blocks (link buttons kept, pressed set removed on success and kept on failure, a
  context line from fixed words) through `chat.update`, best-effort, with
  `channel.press_reported` / `channel.press_report_failed`. `channels/inbound.py`:
  `_record` returns the ledger's `PostResult`, `_deliver` returns `(delivered, error)`,
  `process_reply` carries `url` / `error`, `handle_socket_action` reports a processed
  press on the message it sat on, `process_kickoff` replies with the Start button.
  `commands/channels_cmd.py`: `_button_lines` — both sets, and only the steps that
  still apply. The two event types in `eventlog.py`. The guide (a *Buttons* section, two
  table rows, the limits bullet, the status excerpt), the option, command, capability,
  README, collaboration-reference and template docs; the manifest's one comment (pinned
  to the guide); decision-117.
- **Checkpoint/tests:** `make check` — see `evidence/verification.md`. New tests: 30
  unit (`test_channels_buttons.py`), 4 scenarios (`test_channels_integration.py`).
  Existing assertions changed: three, all in `test_channels.py` — the pins of a
  *processed* outcome dict, which now also carries `url` / `error`.
- **Self-review:** three passes over the diff. Pass one found that the keyword parse ran
  outside the config parser's `try`, so a malformed `routing.control` could have raised
  out of `from_mapping` — guarded, falling back to the shipped keywords with a warning;
  that a config built directly (not through `from_mapping`) carried no keywords and so
  no buttons — the field now defaults to the shipped keywords; and that the status
  block read *To turn buttons on* under a head that said *on* when only the token was
  missing — reworded to *Still needed*. Pass two verified three design claims against
  the code: `report_press` runs only on a `processed` outcome (a dropped press edits
  nothing); the outcome line never reads `reply.text` or the payload's button text; the
  command button precedes the Approve pair. Pass three read the docs against the code:
  the guide's `channels status` excerpt matches the printed strings word for word; the
  manifest comment in the guide matches the packaged file (the pin is green). Nothing
  else new. One observation outside scope, for a follow-up if wanted: a `comment.agent`
  mirror shows its HTML markers (`<!-- the-loop:… -->`) literally in Slack — pre-existing
  for every mirrored agent comment, and the Execute button sits on such a message.
- **Next:** the owner's review.
- **Blockers:** none.

### 2026-09-11 — spec chain drafted

- **Phase:** requirements-definition → tasks-breakdown
- **Did:** read the ticket and the owner's comment; read `channels/{slack,inbound,
  events,base,bus,publishers,github}.py`, `commands/channels_cmd.py`,
  `graph/hooks/selection.py`, `control.py`, the channel test suites, the guide, the
  option and command docs, the issue-334 spec and decisions 103, 111 and 116 at
  `a8acc96` (13.9.0). Established that a press already enters the pipeline as the
  member's reply carrying the button's value (`handle_socket_action`), so an Execute
  button is a value of `the-loop execute` under the `control.command` grant and no new
  authority; that the phase-selection checklist reaches Slack as a `comment.agent`
  mirror carrying its own marker, which is what the renderer can key on; that the
  kickoff reply is the message that expects `the-loop start`; and that the app-level
  token is genuinely required (Slack delivers a press only to an acknowledging
  connection or a public Request URL). Wrote the four artifacts and the decision.
- **Checkpoint/tests:** baseline — `test_channels.py`, `test_channels_integration.py`,
  `test_bus.py`, `test_eventlog.py` green at `a8acc96`.
- **Next:** task 1 (the config and the renderer), red first.
- **Blockers:** none.

## Verification results

> Only when this work item declared `test-planning` away. It did not: results live in
> [`testing-plan.md`](testing-plan.md).

| What was verified | Command | Outcome | Evidence |
|-------------------|---------|---------|----------|
| — | — | — | see `testing-plan.md` |

## Design critic review

> Not selected for this work item.

| Round | Critic (`<harness>/<model>`) | Outcome | Findings → disposition | Link |
|-------|-----------------------------|---------|------------------------|------|
| | | | | |

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Findings → disposition | Link |
|-------|-----------------------------|----------|---------|------------------------|------|
| 1 | self | the-loop (this session) | three new findings | the keyword parse could raise out of `from_mapping` — guarded; a directly-built config carried no keywords — defaulted; the status wording — reworded | this log |
| 2 | self | the-loop (this session) | zero new findings | three design claims verified against the code (report only on `processed`; the line never copies text; button order) | this log |
| 3 | self | the-loop (this session) | zero new findings (converged) | the docs read against the code; one out-of-scope observation noted | this log |
| — | critic | — | unavailable — `reviews.critics` is empty in this repository's config; does not count toward `criticReviewCount` | — | — |
| 4 | security | the-loop checklist | pass; no human sign-off at tier 3 | A1–A7 closed | [`evidence/security-review.md`](evidence/security-review.md) |

## Security review (gate)

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`; no security-review
  skill is invocable from this session's plugin set)
- **Outcome:** pass — [`evidence/security-review.md`](evidence/security-review.md), seven abuse cases closed
- **Human sign-off:** not required (tier 3 < `humanSignOffMinTier: 4`); the owner's PR approval is the gate

## Final validation evidence

| Requirement | Proof |
|-------------|-------|
| R1.1 | `test_the_checklist_mirror_earns_an_execute_button_with_the_keyword_as_value`, `test_expected_commands_reads_the_marker_on_agent_comments_only`, `test_the_marker_is_the_selection_hooks`; `Scenario: An Execute press records what a typed the-loop execute records, and the message says so` |
| R1.2 | `test_reply_blocks_carry_the_start_button`; `Scenario: A kickoff reply carries Start and its press records the start keyword` |
| R1.3 | the two scenarios above (`parse_command(body).command == "execute"` / `"start"`, unmarked, the envelope names the person, `deliveries == []`); `test_an_unlisted_members_press_edits_nothing` |
| R1.4 | `test_command_buttons_need_socket_and_the_grant`, `test_no_command_button_without_socket_and_the_grant`, `test_a_disabled_keyword_renders_no_button` |
| R1.5 | `test_keyword_reads_the_configured_vocabulary`, `test_a_renamed_keyword_is_the_buttons_value`, `test_the_button_tables_agree`, `test_render_blocks_puts_command_buttons_before_the_approval_pair` |
| R2.1, R2.2 | `test_report_press_rewrites_the_message_with_the_outcome`, `test_a_failed_press_keeps_the_buttons_and_says_why`, `test_the_press_line_says_what_each_kind_did`, `test_a_message_without_blocks_gets_its_text_and_the_line`; `Scenario: A press whose record the ledger refused keeps its button and says why` |
| R2.3 | `test_a_refused_update_is_an_event_and_false`, `test_report_press_without_a_token_is_quiet`, `test_an_unlisted_members_press_edits_nothing`; `Scenario: An unlisted member's press edits nothing` |
| R2.4 | `test_an_approve_press_is_reported_too` |
| R2.5 | the first scenario's reaction assertion (`eyes`, `white_check_mark` on the pressed message); the issue-325 suites unchanged |
| R2.6 | `test_the_press_report_never_echoes_the_value_or_a_token`, `test_a_press_report_event_carries_the_action_never_text` |
| R3.1, R3.2 | `test_status_names_both_button_sets_and_the_missing_steps`, `test_status_prints_no_steps_when_buttons_are_on`, `test_status_prints_only_the_steps_that_apply` |
| R3.3 | `docs/guide/slack.md` § The buttons (markdownlint clean) |
| R4.1 | `test_docs_parity.py`, `test_config_schema_parity.py`, `test_eventlog.py::test_every_emitted_event_type_is_documented`, the manifest pin; the docs table below |
| A1–A7 | `evidence/security-review.md` |

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`channels.md`](../../capabilities/channels.md) | the rendering bullet (the Execute and Start buttons, their condition, the configured keyword as value); a new *press outcome* bullet (the edit, landed vs failed, dropped edits nothing, the status steps and why the token is required); the observability bullet (two event types); two design links | issue-337 row |
| [`standing-sessions.md`](../../capabilities/standing-sessions.md), [`control-plane.md`](../../capabilities/control-plane.md) | unchanged — a press on a standing session's thread is a reply, as before; the control plane is not touched | — |

## Documentation

| Document | What changed |
|----------|--------------|
| `docs/guide/slack.md` | the intro and diagram name the buttons; the `channels status` line in *Run it*; two rows in the modes table; the phase-selection paragraph says *press Execute*; a new *The buttons* section (the table of four buttons, a press is the typed reply, the outcome edit, why the app-level token is required, the `channels status` excerpt); the *Limits* bullet |
| `docs/config/cli/channels-options.md` | the `control.command` row of the `publish` table names the buttons; the `read.mode` paragraph names the Execute / Start buttons, the outcome edit and the status steps, and links the guide section |
| `docs/cli/commands/channels.md` | the `status` bullet describes the `buttons:` block and its steps; the `listen` line names the buttons |
| `README.md` | the `channels listen` line names the buttons |
| `skills/the-loop/reference/collaboration.md` | the channels paragraph names the Execute / Start buttons and the outcome edit |
| `skills/the-loop/templates/cli-config.yaml`, `.the-loop/cli-config.yaml` | the `read.mode` comment says only `socket` receives a press and points at `channels status` |
| `cli/the_loop/channels/slack-app-manifest.yaml` | the interactivity comment names the new buttons (byte-identical to the guide's copy; the pin is green) |
| `docs/decisions/decision-117.md`, `decisions.md` | the decision and its index row |
| `skills/the-loop/SKILL.md`, `reference/workflow.md`, `reference/automation.md` | unchanged — the operating model itself did not change (a press is a keyword recorded on the ledger and executed there) |
