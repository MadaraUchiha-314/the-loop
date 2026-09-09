# Security review — issue-334

> Mechanism: the-loop checklist (`security.review.mechanism: auto`; no security-review
> skill is invocable from this session's plugin set). Tier 3: below
> `security.review.humanSignOffMinTier: 4`, so no named human sign-off is required; the
> owner's PR approval is the gate.

## Threat model recap

The change adds a **new inbound shape** to the Slack channel: a slash command, delivered
on the Socket Mode connection the listener already holds, carrying the invoking member's
id, a free-text `text`, a `channel_id`, a `trigger_id` and a `response_url` — all
untrusted. It differs from a thread reply in two ways that are the whole security design:
it is **not bound to a thread**, so the work item it acts on is an argument; and two of
its verb families act on **this process's host** (a scheduled restart, a tmux session)
rather than on a ticket. The mitigations, in the order the handler applies them: the
allow-list before anything is parsed; a fixed vocabulary with per-token grammars and no
interpolation; a grant per family, none on by default; a bounded target for work-item
verbs; the ledger (never the handler) as the executor of a work-item verb; the core
facade (never a shell) for the other two; an answer only to Slack's own host; a trigger
acted on once. No schema key is added, and a 13.8.0 config gains nothing it did not
already grant.

## Abuse cases — disposition

| # | Abuse case | Closed by | Evidence |
|---|------------|-----------|----------|
| A1 | An unlisted member (or anyone, with an empty allow-list) invokes `/the-loop` | `handle_slash_command` checks `config.authorized_users` before the text is read; the drop answers nothing | `test_channels_commands.py::test_an_unlisted_member_is_dropped_before_parsing`, `test_an_empty_allowlist_denies_everyone`, `test_a_disabled_channel_acts_on_nothing`; `test_channels_integration.py::test_an_unlisted_members_slash_command_leaves_nothing` |
| A2 | An authorized member invokes a verb whose grant the channel lacks | `FAMILY_GRANTS[family]` against `config.publish` before any act; the answer names the grant, nothing runs | `test_a_verb_without_its_grant_is_refused_and_named` (three families) |
| A3 | A work-item verb names a repository this instance was never configured for, making the operator's credential comment there | `may_target`: `kickoff.repo` ∪ `polling.sources[].repos` ∪ the managed set ∪ the bound conversations; a read that raises contributes nothing | `test_a_foreign_repository_is_refused_and_nothing_is_recorded`, `test_may_target_kickoff_repo_and_poll_sources`, `test_may_target_a_bound_conversation_and_a_managed_item`, `test_a_failing_read_contributes_nothing` |
| A4 | Text beyond the vocabulary — a second keyword, a shell metacharacter, prose, a second address — reaches a record, an argv or a name | `parse_invocation` refuses extra tokens and second keywords whole; the recorded line is composed from `control.keyword(verb)` and validated tokens | `test_parse_refuses_unknown_and_extra_tokens` (`start #7; rm -rf /`, `start stop #7`), `test_parse_reads_one_instance_address`, `test_the_recorded_line_is_built_from_the_keyword_not_the_text` |
| A5 | A crafted `response_url` off Slack's host makes the-loop POST somewhere else | `webhook_responder` sends only to `https://hooks.slack.com/`; anything else is refused and logged | `test_an_off_host_response_url_is_never_posted_to` (`https://evil.example/hook`, empty) |
| A6 | A malformed standing name, login or instance name reaches a tmux name, a file name or a comment | `standing.NAME_RE`, `collaborators.parse_logins`, `instance.NAME_RE` at parse time | `test_parse_refuses_a_malformed_standing_name` (`sup;rm`, 41 chars, uppercase), `test_parse_refuses_a_malformed_login`, `test_parse_reads_one_instance_address` (`instance:Not_Valid`) |
| A7 | A restart argv carries payload text | the handler passes one boolean and the path this process read to `core.lifecycle.schedule_restart`, which builds the fixed argv | `test_restart_and_upgrade_schedule_through_the_facade` |
| A8 | The event log leaks the command text, a token or the response URL | `channel.command_received` carries the resolved ref / the standing name / `instance`; `channel.command_completed` the outcome; `channel.dropped` the reason and the member id | `test_command_events_carry_ids_never_text` (`xoxb-supersecret`, `the-secret-thing`, `hooks.slack.com` absent) |
| A9 | The same `trigger_id` is delivered twice and a work-item verb is recorded twice | a process-local ring of 256 triggers, consulted before parsing | `test_a_duplicate_trigger_is_dropped` |

## Checklist

- [x] AuthN/AuthZ: the allow-list is the `slack` ids of `routing.authorizedUsers`, read before the text (A1); every verb family is a grant, off by default (A2); a disabled channel acts on nothing.
- [x] Through the ledger, never around it: a work-item verb publishes `control.command` and stops at the unmarked record; the handler starts, spawns and delivers nothing — `test_a_work_item_verb_records_the_composed_line_unmarked` asserts `lifecycle.calls == []` and `standing.calls == []`, and the integration scenario asserts `deliveries == []`.
- [x] Input validation: a fixed vocabulary, whole tokens, one grammar per token kind (A4, A6); the target parsed by `resolve_work_item` and bounded by `may_target` (A3); a URL accepted only on this instance's own GitHub host.
- [x] Secrets: no token is read by the handler; the answer goes through the SDK's `WebhookClient`; no event carries text, a token or the URL (A8).
- [x] Fail closed, restated: `channels.slack.enabled: false`, `read.mode` other than `socket` (no transport), an empty allow-list, a missing grant, an unknown target, an unparsable ref, `#N` with no `kickoff.repo` — each means nothing happens.
- [x] Best-effort contract: the ledger's refusal and the facade's exceptions are outcomes and answers (`test_a_failing_ledger_is_a_recorded_outcome`, `test_a_raising_facade_is_answered_not_raised`); a failed or raising responder never changes the outcome (`test_a_failed_answer_keeps_the_outcome`, `test_a_raising_responder_never_escapes`); the listener's `except Exception` stays around the handler.
- [x] At most once: the trigger ring (A9); the listener acknowledges before handling so Slack does not retry.
- [x] Scope: one new bot scope (`commands`) and two for private channels (`groups:history`, `message.groups`) — declared in the manifest, needed for nothing else.
- [x] Evidence redaction: every token, member id, channel id and URL in the tests is a fixture; nothing here is real.

## Outcome

**Pass** on the autonomous checklist. No human sign-off required at tier 3; the pull
request's review is the human gate.
