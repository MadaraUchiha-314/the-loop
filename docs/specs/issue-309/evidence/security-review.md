# Evidence: security review (T13)

Tier 4 (`autonomy.tiers`), and `security.review.humanSignOffMinTier: 4` — so this
records the harness's own review against the abuse cases in `requirements.md`, and the
**named human security sign-off is still outstanding**. It is requested in the pull
request's briefing.

## Why this work item is a security review at all

It lets a chat message do three things it could not do before: **answer a human gate**,
**run a control keyword**, and **create a work item**. Each is a new way for untrusted
text to reach an action. The design's answer is that none of them reaches an action
directly — each becomes a comment the ledger's own ingress judges with the guards that
already exist — and the review below asks, per abuse case, whether that is actually true
in the code.

## The abuse cases, and what closes each

| # | Abuse case | Verdict | Where it is closed, and what proves it |
|---|------------|---------|----------------------------------------|
| A1 | An unlisted Slack member replies, presses a button, or posts top-level | closed | `process_reply` and `process_kickoff` check the member id against `ids_for(principals, "slack")` before anything else runs; empty denies all. `test_empty_allowlist_denies_every_reply`, `test_unlisted_member_id_is_denied`, the stranger/bot rows of `test_a_top_level_dm_becomes_a_labelled_issue_bound_to_its_thread`, the `USTRANGER` press in `test_an_approve_button_press_enters_the_pipeline_as_that_members_reply` |
| A2 | An authorized member types a control keyword on a channel without the grant | closed | classification precedes the grant check and `unpublishable-event` is a drop, never a downgrade — the text reaches neither the ticket nor the agent. `test_a_control_keyword_without_the_grant_is_dropped_not_delivered`, `test_without_a_grant_a_reply_is_session_input_and_nothing_more` (an "approved" at a gate without `gate.feedback`) |
| A3 | A work-item collaborator (not authorized) forges an envelope naming an authorized person | closed | `graphlink._attributed` rewrites only when the **poster** is in `authorized` and the named login is too. `test_an_envelope_reattributes_only_between_authorized_people`, and the `dana` row of `test_a_slack_reply_with_the_gate_grant_is_recorded_unmarked_and_classified_on_ingress` |
| A4 | An unauthorized GitHub user posts an enveloped comment | closed | Both ingresses drop the comment on `authorizedUsers` before anything reads the envelope — unchanged guards, asserted: the `attacker` row of the same scenario (`Router.route` returns `None`) |
| A5 | A relayed `control.command` bypasses the control seam | closed | The record is a plain comment; the pipeline executes nothing (`deliveries == []`) and the only executor is `Dispatcher.handle`'s named-actor seam, reached through `parse_command` on the record. `test_a_slack_control_keyword_with_the_grant_is_executed_by_ingress_not_the_pipeline`, `test_a_control_keyword_with_the_grant_is_recorded_unmarked_for_ingress` |
| A6 | A kickoff with the grant but no repo | closed | `kickoff_enabled` needs both; `process_kickoff` drops `kickoff-disabled` before any write, and `GitHubLedger._create` refuses an empty repo independently. `test_kickoff_needs_the_grant_and_a_repo`, `test_a_kickoff_without_a_repo_records_nothing`, the `no_repo` row of the kickoff scenario |
| A7 | A kickoff issue arms itself, or names its own labels | closed | Labels come from `kickoff.labels` only (the message's `labels: evil` line is body text); the body is unmarked (armable) but enveloped. `test_a_kickoff_record_is_an_issue_with_only_configured_labels` |
| A8 | A message claims to be someone | closed | The envelope's actor is `principal_for(principals, channel, member_id)` — config, never text. `test_principal_for_resolves_from_config_never_from_the_message`, the actor assertions in `test_a_relayed_record_is_unmarked_with_the_words_intact` |
| A9 | A crafted Block Kit action with an unknown value | closed | `handle_socket_action` reads only `the-loop:`-prefixed action ids and treats `value` as text through `process_reply` — same authorization, same grants. The `the-loop cleanup` press (dropped as `unpublishable-event`) and the foreign action id (`ignored`) in the button scenario |
| A10 | A channel makes the bus echo its own message back | closed | `has_envelope` short-circuits `Router._publish`, `Poller._publish` and `publish_comment`. `test_the_router_never_republishes_a_bus_record`, `test_publish_comment_skips_enveloped_records_and_unknown_kinds`, the poller row of `test_the_poller_publishes_agent_and_human_comments_once_each`, the enveloped row of the comment-mirror scenario |

## Two things a reviewer should look at hardest

1. **The unmarked record is posted under the operator's own credential.** That is what
   makes ingress treat a relayed gate answer as an authorized comment — and it means
   *the pipeline's* member-id check is the only thing between a Slack message and a
   comment that can approve a gate. The check is at the head of `process_reply`, before
   classification, and the allow-list comes from config alone. If a second inbound
   surface is ever added, it must run the same check before it records anything.
2. **Re-attribution narrows, never widens — by two conditions, not one.** The poster
   must be authorized (so a collaborator's forgery is inert) **and** the named login
   must be authorized (so an envelope cannot mint an approver). Dropping either
   condition would be a privilege escalation; both are asserted in
   `test_an_envelope_reattributes_only_between_authorized_people`.

## What was not changed, on purpose

- The webhook HMAC, the self-marker drop, `authorizedUsers` on both ingresses, the
  control seam's named-actor re-check and `classify-feedback`'s filter are all
  untouched. The record shapes were chosen so that they are what judges a relayed
  event.
- Secrets: tokens are still env-named and read at call time; nothing new is written
  to state, status output or the event log.

## Outcome

Ten abuse cases, ten closed by a mechanism in the diff and a negative test in the
suite. **Human sign-off:** required at tier 4 — requested in the PR.
