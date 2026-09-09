---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#334"
phase: needs-review
status: in-progress
---

# Execution Log: drive the loop from Slack — the keywords in the thread, a slash command for the rest, and one guide

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-09-09 | — | Tier 3 (`human-approves-pr`; below `humanSignOffMinTier: 4`): a new inbound shape on the Slack channel behind the existing allow-list and grant model, two catalog rows, a packaged manifest, a guide; both schema copies change in one description string (an `autonomy.sensitivePaths` match). Brainstorming skipped: the ticket's four asks are the requirement, and the answer to its questions is recorded in decision-116. No authorized `the-loop execute` reaches this cloud session, so the selection is recorded here and every phase is walked |
| requirements-definition | 2026-09-09 | | [`requirements.md`](requirements.md) — four requirements, nine abuse cases |
| design | 2026-09-09 | | [`design.md`](design.md) — two catalog rows, one module, one transport branch, a manifest; [`decision-116`](../../decisions/decision-116.md) |
| test-planning | 2026-09-09 | | [`testing-plan.md`](testing-plan.md) — thirteen rows, six applicable |
| tasks-breakdown | 2026-09-09 | | [`tasks.md`](tasks.md) — six tasks |
| implementation | 2026-09-09 | | On `claude/github-issue-334-k9yw0i` |
| verification | 2026-09-09 | | [`evidence/verification.md`](evidence/verification.md) — rows T1, T2, T8, T10, T12; [`evidence/security-review.md`](evidence/security-review.md) — nine abuse cases, nine closed |
| needs-review | 2026-09-09 | | PR raised; awaiting the owner (tier 3: `human-approves-pr`) |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#336](https://github.com/MadaraUchiha-314/the-loop/pull/336) | tasks 1–6: the whole work item | open |

## Progress entries

### 2026-09-09 — the downtime gap closed at review

- **Phase:** needs-review
- **Did:** the owner asked how events are accounted for while the-loop is down. Answered
  on the PR (poll mode: cursors, nothing lost; the ledger: durable; socket mode: Slack's
  few retries, then a gap) and closed the gap: `slack.catch_up` runs `poll_once` when
  the listener connects (`channel.caught_up`); `poll_once` refuses only `off`, so
  `channels poll` reconciles beside a listener; `handle_socket_event` drops a
  redelivered message at or before the thread's cursor as `duplicate`. R2.6 added to the
  requirements, the design and the capability doc; a *Downtime* section in the guide.
- **Checkpoint/tests:** `Scenario: A Socket Mode listener catches up on what was posted
  while down`; `test_poll_once_runs_in_socket_mode_as_a_reconciliation`; the four
  channel suites and the event catalog green; ruff, pyright.
- **Next:** the owner's review.
- **Blockers:** none.

### 2026-09-09 — review question answered

- **Phase:** needs-review
- **Did:** the owner asked on the PR whether Socket Mode means the-loop needs a webhook
  server Slack calls, and then whether it means one long-lived connection every event
  rides on (yes: `apps.connections.open` → one `wss://` socket, pinged, auto-reconnected
  by the SDK, one listener per instance; answered on the PR and added to the guide). Answered on the PR: no — Socket Mode is an outbound WebSocket the
  listener opens, Slack pushes commands down it, the answer is an outbound POST to the
  `response_url`; nothing inbound, no Request URL. Added a *No webhook server, no
  Request URL* paragraph to the guide's *Run it* step so the next reader does not have
  to ask.
- **Checkpoint/tests:** markdownlint clean; the manifest pin green.
- **Next:** the owner's review.
- **Blockers:** none.

### 2026-09-09 — implemented, verified, ready for review

- **Phase:** implementation → verification → needs-review
- **Did:** tasks 1–6, red first (`test_channels_commands.py` did not import against
  `e54592d`; the four scenarios failed on the missing module). Two catalog rows
  (`instance.command`, `standing.command`; publishable, not subscribable, not recorded);
  three event types and four drop reasons; `channels/commands.py` — `parse_invocation`
  (a fixed vocabulary from the configured keywords, three instance verbs, four standing
  verbs, one grammar per token), `resolve_work_item` (four ref shapes, the issue-331 host
  rule, a URL only on this instance's host), `may_target` (`kickoff.repo` ∪ poll repos ∪
  the managed set ∪ the bound threads, every read best-effort), `handle_slash_command`
  (authorize → duplicate → parse → grant → act → answer; a work-item verb publishes
  `control.command` through the bus and stops at the ledger record; instance and standing
  verbs call the core facade), `render_status`, `webhook_responder` (Slack's host only),
  `manifest_text`; the `slash_commands` branch of `run_socket_listener`; the packaged
  `slack-app-manifest.yaml`; `channels manifest` and the `commands:` line of `channels
  status`; the guide `docs/guide/slack.md` and the option, command, capability, template
  and reference docs; decision-116.
- **Checkpoint/tests:** `make check` — see `evidence/verification.md`. New tests: 47 unit
  (`test_channels_commands.py`), 4 scenarios (`test_channels_integration.py`). Existing
  assertions changed: two, both in `test_bus.py` — the issue-309 pins of the publishable
  set (now six) and of "every publishable event is recorded" (the two command grants are
  not, by design).
- **Self-review:** three passes over the diff. Pass one found that a disabled channel
  (`channels.slack.enabled: false`) would still have been *parsed* by an embedder calling
  the handler directly, though the listener never runs for one; added the
  `channel-disabled` drop before authorization, with a test. Pass two verified three
  design claims against the code: the acknowledgment precedes the handling in the
  listener (so Slack's deadline is met whatever the facade takes); `channel.command_received`
  is emitted only after the target passed its own validation, so its `target` field is a
  ref, a grammar-bounded name or `instance` — never text; `webhook_responder`'s prefix
  includes the trailing slash, so `hooks.slack.com.evil.example` cannot match. Pass three
  read the docs against the code: the "One catalog" bullet of `channels.md` still said
  four publishable events and "the four publishable ones recorded" — corrected; the
  `read.mode` option page did not say slash commands need `socket` — added; the
  control-plane capability did not list the command as a client of the facade — added.
  Nothing else new.
- **Next:** the owner's review.
- **Blockers:** none.

### 2026-09-09 — spec chain drafted

- **Phase:** requirements-definition → tasks-breakdown
- **Did:** read the ticket; read `channels/{events,base,bus,github,inbound,slack}.py`,
  `control.py`, `core/{lifecycle,standing,instance}.py`, the channel test suites, the
  channel option and command docs, the issue-309/321/325 specs and decisions 100, 103
  and 111 at `e54592d` (13.8.0). Established that ask 1 of the ticket is already true
  by grant (`control.command` in `channels.slack.publish` — the thread path records
  the keyword unmarked and the ingress executes it) and undocumented, and that asks
  2–3 share one gap: every inbound Slack message is bound to a thread, so nothing can
  address the instance or a work item that has no thread yet. Verified that the
  phase-selection gate's checklist regex reads only unquoted lines, so an `execute`
  from Slack signs the ticket's ticks (R1.3). Confirmed the Socket Mode client hands
  `slash_commands` envelopes to the same listener and that `slack_sdk` ships
  `WebhookClient` for the `response_url`. Wrote the four artifacts and the decision.
- **Checkpoint/tests:** baseline — `test_channels.py`, `test_channels_integration.py`,
  `test_docs_parity.py`, `test_eventlog.py`, `test_config_schema_parity.py` green
  (142 passed).
- **Next:** task 1 (the catalog and the event types) and task 2 (the parser), red first.
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
| 1 | self | the-loop (this session) | one new finding | a disabled channel's handler still parsed — `channel-disabled` drop added before authorization, tested | this log |
| 2 | self | the-loop (this session) | zero new findings | three design claims verified against the code (ack before handling; `target` never text; the responder's prefix) | this log |
| 3 | self | the-loop (this session) | three doc corrections, zero code findings (converged) | the catalog bullet, the `read.mode` clause, the control-plane client bullet | this log |
| — | critic | — | unavailable — `reviews.critics` is empty in this repository's config; does not count toward `criticReviewCount` | — | — |
| 4 | security | the-loop checklist | pass; no human sign-off at tier 3 | A1–A9 closed | [`evidence/security-review.md`](evidence/security-review.md) |

## Security review (gate)

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`; no security-review
  skill is invocable from this session's plugin set)
- **Outcome:** pass — [`evidence/security-review.md`](evidence/security-review.md), nine abuse cases closed
- **Human sign-off:** not required (tier 3 < `humanSignOffMinTier: 4`); the owner's PR approval is the gate

## Final validation evidence

| Requirement | Proof |
|-------------|-------|
| R1.1, R1.2 | `Scenario: A slash command start records what a thread keyword records` (the typed keyword's record: unmarked, `parse_command` → `start`, envelope names the person); `test_channels.py::test_a_control_keyword_with_the_grant_is_recorded_unmarked_for_ingress` (pre-existing, pinned) |
| R1.3 | the phase-selection gate's `_CHECK_LINE` regex reads only unquoted lines (verified at `e54592d`); stated in the guide § Limits |
| R1.4 | `test_channels.py::test_a_control_keyword_without_the_grant_is_dropped_not_delivered` (pre-existing); the guide's modes table names the grant |
| R2.1 | the `slash_commands` branch of `run_socket_listener` (ack, then `handle_slash_command`); `test_channels_status_says_which_command_families_are_granted` (the `off (read.mode is poll …)` line) |
| R2.2 | `test_parse_help`, `test_parse_instance_verbs`, `test_parse_standing_verbs`, `test_parse_work_item_verbs_from_the_configured_keywords`, `test_parse_collaborator_commands_take_one_login`, `test_parse_reads_one_instance_address`, `test_parse_refuses_*`, `test_usage_names_every_family` |
| R2.3 | `test_resolve_work_item_shapes`, `test_resolve_refuses_what_is_not_a_work_item`, `test_resolve_bare_numbers_need_kickoff_repo`, `test_resolve_applies_the_resolved_host` |
| R2.4 | `test_may_target_kickoff_repo_and_poll_sources`, `test_may_target_a_bound_conversation_and_a_managed_item`, `test_a_failing_read_contributes_nothing`, `test_a_foreign_repository_is_refused_and_nothing_is_recorded` |
| R2.5 | `test_parse_refuses_a_malformed_standing_name`, `test_parse_refuses_a_malformed_login`, `test_parse_reads_one_instance_address` |
| R3.1 | `test_an_unlisted_member_is_dropped_before_parsing`, `test_an_empty_allowlist_denies_everyone`; `Scenario: An unlisted member's slash command leaves nothing` |
| R3.2 | `test_the_catalog_carries_the_two_command_grants`, `test_the_family_grants_are_catalog_rows`, `test_a_verb_without_its_grant_is_refused_and_named`; `test_bus.py` (the updated pins) |
| R3.3 | `test_a_work_item_verb_records_the_composed_line_unmarked`, `test_the_recorded_line_is_built_from_the_keyword_not_the_text`, `test_collaborator_and_execute_verbs_relay_like_any_other`; the first scenario |
| R3.4 | `test_command_events_carry_ids_never_text`; `test_eventlog.py` (the catalog knows the three types) |
| R3.5 | `test_status_renders_the_facade_document`, `test_render_status_without_standing_sessions`, `test_restart_and_upgrade_schedule_through_the_facade`, `test_standing_verbs_call_the_facade`; `Scenario: A slash command status answers from the facade`, `Scenario: A slash command starts a standing session` |
| R3.6 | `test_a_failing_ledger_is_a_recorded_outcome`, `test_a_raising_facade_is_answered_not_raised`, `test_a_standing_refusal_is_the_answer`, `test_a_failed_answer_keeps_the_outcome`, `test_a_raising_responder_never_escapes`, `test_a_duplicate_trigger_is_dropped` |
| R4.1 | `test_the_manifest_is_packaged_and_printed`, `test_the_guide_reproduces_the_packaged_manifest` |
| R4.2 | `docs/guide/slack.md` (markdownlint clean; in the guide sidebar) |
| R4.3 | `test_the_docs_list_every_publishable_event`, `test_docs_parity.py`, `test_config_schema_parity.py`, `make validate`; the docs table below |
| A1–A9 | `evidence/security-review.md` |

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`channels.md`](../../capabilities/channels.md) | the "One catalog" bullet (six publishable, four recorded); a current-behaviour bullet for the slash command (authorize first, the vocabulary, the three grants, the ledger for work-item verbs, the facade for the rest, the bounded target, Socket Mode only, the manifest); the observability bullet (three event types, four drop reasons); two design links | issue-334 row |
| [`standing-sessions.md`](../../capabilities/standing-sessions.md) | a paragraph under *How you interact with one*: starting and stopping from Slack under `standing.command`, refining decision-100 without adding a fourth way to talk | issue-334 row |
| [`control-plane.md`](../../capabilities/control-plane.md) | a current-behaviour bullet: the slash command as one more thin client of the facade for the ticket-less verbs | — (no history table entry; the behaviour is the channel's) |

## Documentation

| Document | What changed |
|----------|--------------|
| `docs/guide/slack.md` (new) + `docs/.vitepress/config.mts` | the Slack integration guide — setup from the manifest, the two tokens, the config, the modes-of-interaction table, starting a work item and a standing session, the control plane from Slack, the slash command in full, through-the-ledger, limits, why not Workflow Builder; added to the guide sidebar |
| `docs/config/cli/channels-options.md` | a pointer to the guide; the private-channel and `commands` scopes beside the bot token; two rows in the `publish` table; a clause under `publish` and under `read.mode`; a new *The slash command* section (no new option heading — no schema key was added) |
| `docs/cli/commands/channels.md`, `docs/cli/commands/index.md` | the `manifest` action, the slash command in `listen`, the `commands:` line of `status`, the flags row |
| `README.md` | one line in the CLI block: `channels listen` with the slash command, pointing at the guide |
| `skills/the-loop/reference/collaboration.md` | the channels paragraph names the slash command and the guide; the stale *two places* identity line (it still named the retired `channels.slack.authorizedUsers`) corrected to one |
| `skills/the-loop/templates/cli-config.yaml`, `.the-loop/cli-config.yaml` | the two grants in the `publish` comment |
| `.the-loop/cli-config.schema.json`, `cli/the_loop/schemas/cli-config.schema.json` | the `publish` description names the two grants (byte-identical copies; one string, no new key) |
| `docs/decisions/decision-116.md`, `decisions.md` | the decision and its index row |
| `skills/the-loop/SKILL.md`, `reference/workflow.md`, `reference/automation.md` | unchanged — the operating model itself did not change (a keyword from Slack is still recorded on the ledger and executed there); `automation.md` describes the control seam the record reaches, not the channels |
