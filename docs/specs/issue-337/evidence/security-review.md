# Security review — issue-337

> Mechanism: the-loop checklist (`security.review.mechanism: auto`; no security-review
> skill is invocable from this session's plugin set). Tier 3: below
> `security.review.humanSignOffMinTier: 4`, so no named human sign-off is required; the
> owner's PR approval is the gate.

## Threat model recap

The change adds two Block Kit buttons — **Execute** and **Start** — to Slack messages
the channel already posts, and one outbound call (`chat.update` on the pressed message)
after a press is processed. A press is a `block_actions` payload whose `user.id`,
`actions[].action_id`, `actions[].value`, `message.blocks` and `message.ts` are untrusted.
There is **no new trust boundary**: the button's value enters the same pipeline a typed
reply enters (`handle_socket_action` → `process_reply`), through the same allow-list, the
same classification, the same `control.command` grant and the same unmarked ledger record
the ingress executes. No new grant, scope, config key or state file. The mitigations, in
the order they apply: the allow-list before the record; the value judged as text by
`parse_command`; the grant checked at press time; the outcome line composed from fixed
words and ids; the edit under the bot's own identity, best-effort; buttons rendered only
where a press can be received.

## Abuse cases — disposition

| # | Abuse case | Closed by | Evidence |
|---|------------|-----------|----------|
| A1 | An unlisted member presses Execute or Start | `process_reply`'s allow-list drops the press before the record; `report_press` runs only on `processed`; no reaction, no edit, no answer | `test_channels_buttons.py::test_an_unlisted_members_press_edits_nothing`; `test_channels_integration.py::test_an_unlisted_members_press_leaves_the_message_untouched` |
| A2 | A crafted `value` that is not a keyword, or prose around one, reaches a shell, an argv or a file | the value is text through `_classify` → `parse_command`; a non-keyword classifies as `work-item.reply` and is judged by that grant; nothing outside the pipeline reads it | `test_a_crafted_value_is_judged_as_text` (`rm -rf / && echo pwned` → `unpublishable-event`, nothing recorded, delivered or edited) |
| A3 | The `control.command` grant was withdrawn after the button was rendered | the grant is checked at press time, after classification — `unpublishable-event`, no record, no edit | `test_a_press_after_the_grant_was_removed_is_dropped_and_edits_nothing` |
| A4 | The edited message leaks the payload's text, the value or a token | `_press_line` composes fixed words, `BUTTON_NAMES[action_id]`, `<@member>`, the ref, the record URL and the ledger's error; never `reply.text` or the button's text | `test_the_press_report_never_echoes_the_value_or_a_token` (`rm -rf`, `Launch the missiles`, `xoxb` absent) |
| A5 | A payload names a message the bot did not post | Slack refuses `chat.update` (`cant_update_message`); recorded as `channel.press_report_failed`; the outcome stands | `test_a_refused_update_is_an_event_and_false` |
| A6 | A double press before the first edit lands | each press is judged independently and recorded like a repeated typed keyword; the gates and the dispatcher absorb repeats | `test_two_presses_are_judged_independently` (two records, two edits) |
| A7 | A button is rendered where no press can arrive (poll mode) and a press is lost silently | `command_buttons` is false without `read.mode: socket`; `render_blocks` receives `{}` | `test_no_command_button_without_socket_and_the_grant`, `test_command_buttons_need_socket_and_the_grant` |

## Checklist

- [x] AuthN/AuthZ: the allow-list is the `slack` ids of `routing.authorizedUsers`, applied by the unchanged pipeline before the record (A1); the button adds no authority the `control.command` grant did not already give.
- [x] Through the ledger, never around it: a press of Execute / Start is a `control.command` recorded unmarked and executed by the ledger's ingress — the integration scenario asserts `deliveries == []` and `parse_command(body).command == "execute"` / `"start"`; the Slack code starts, spawns and delivers nothing.
- [x] Input validation: the value is text through the ordinary classification (A2); the grant is re-checked at press time (A3); the outcome line is composed, not copied (A4).
- [x] Secrets: no token is read by the renderer or the report beyond the bot token the SDK client needs; no event carries text, a value or a token (`test_a_press_report_event_carries_the_action_never_text`, `test_a_refused_update_is_an_event_and_false`); `channels status` prints the app token's presence only (`test_status_prints_no_steps_when_buttons_are_on` asserts `xapp-supersecret` absent).
- [x] Fail closed, restated: `channels.slack.enabled: false`, `read.mode` other than `socket`, no `control.command` grant, a disabled keyword — each means no command button; a malformed `routing.control` falls back to the shipped keywords with a warning rather than taking the channel down.
- [x] Best-effort contract: `report_press` never raises — a refused edit is an event and `False`, a missing token is quiet (`test_report_press_without_a_token_is_quiet`); the reactions and the record are untouched.
- [x] Scope: no new bot scope — `chat:write` covers `chat.update`; the manifest changes in one comment only, pinned to the guide.
- [x] Evidence redaction: every token, member id, channel id and URL in the tests is a fixture; nothing here is real.

## Outcome

**Pass** on the autonomous checklist. No human sign-off required at tier 3; the pull
request's review is the human gate.
