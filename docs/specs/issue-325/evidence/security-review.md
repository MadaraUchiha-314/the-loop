# Security review — issue-325

> Mechanism: the-loop checklist (`security.review.mechanism: auto`; no security-review
> skill is invocable from this session's plugin set). Tier 3: below
> `security.review.humanSignOffMinTier: 4`, so no named human sign-off is required; the
> owner's PR approval is the gate.

## Threat model recap

The change adds one **write** to Slack — `reactions.add`, reaction-only, under the bot
token the channel already posts with — on a message the inbound pipeline has already
accepted. It sits *after* every refusal (bot drop, allow-list, grant) and changes nothing
about what a message becomes, who may speak, or where the record lands. The API
arguments are Slack's own `channel` and `ts` and an emoji name from the operator's config,
validated against a fixed grammar; no message text reaches the call. The one new scope,
`reactions:write`, is needed for this decoration alone; without it every reaction is a
logged no-op and the channel behaves exactly as 13.4.0.

## Abuse cases — disposition

| # | Abuse case | Closed by | Evidence |
|---|------------|-----------|----------|
| A1 | An unlisted member or a bot posts in a bound thread, hoping for a 👀 that confirms the bot reads it | every `_drop` returns before `react` is reachable; the acknowledgment follows the last refusal | `test_channels.py::test_a_dropped_message_gets_no_reaction[bot]`, `[empty-allow-list]`, `[unlisted-member]`; `test_an_unauthorized_kickoff_gets_no_reaction` |
| A2 | An authorized member's control keyword on a channel without the grant is acknowledged as if accepted | the grant check precedes the acknowledgment; `unpublishable-event` is a drop | `test_a_dropped_message_gets_no_reaction[unpublishable]` |
| A3 | Slack refuses the reaction (`missing_scope`, a rate limit) and the refusal costs the record or the delivery | `react` catches every exception, records `channel.reaction_failed` and returns; the pipeline's outcome, the ledger post and the delivery are unchanged | `test_channels.py::test_a_refused_reaction_changes_no_outcome`, `test_react_never_raises_and_records_the_failure`; `test_channels_integration.py::test_a_slack_that_refuses_the_reaction_never_fails_the_delivery` |
| A4 | A crafted emoji name in config becomes an API argument | `SlackReactionConfig.from_mapping` refuses any name outside `^[a-z0-9_+-]{1,100}$` per state with a warning; the schema carries the same pattern | `test_a_malformed_reaction_name_is_refused_and_the_state_skipped` (`eyes; rm -rf /`, `WARNING`); `test_a_non_mapping_reactions_block_keeps_the_defaults` |
| A5 | The reaction client raises or hangs and stalls the pipeline | every exception is caught (A3); the SDK's own 30-second timeout bounds a hang, the same exposure the ledger write has on a GitHub outage; no retry | `test_react_never_raises_and_records_the_failure`; the SDK timeout is the client's default and is not overridden |
| A6 | The event log leaks the message text or the token through the new events | both events carry ids, the state and the emoji name; `error` is `str(exc)` from the SDK, which names the API error and not the token | `test_reaction_events_carry_no_text_or_token` (`xoxb-supersecret`, `the secret answer` absent from a log carrying both new types) |

## Checklist

- [x] AuthN/AuthZ unchanged: `process_reply` and `process_kickoff` still drop a bot, an empty allow-list and an unlisted member before any classification; `react` is called only after the grant check (A1, A2).
- [x] The grant still bounds what a message may become; the acknowledgment reads the outcome and never influences it.
- [x] Input validation: the emoji name is validated at load (grammar + schema pattern); `channel` and `ts` are values Slack returned to the-loop's own read; the message text is never an argument (A4).
- [x] Secrets: the token is read at call time through `_client()` and never held; a missing token is a debug-level no-op; neither new event carries it (A6).
- [x] Fail closed, restated: `channels.slack.enabled: false` (the default), no channel id, no token, `reactions.enabled: false`, a state `""` — each means no call. The feature adds no grant and widens no authorization.
- [x] Best-effort contract: no exception from `react` can reach the pipeline; the record-before-delivery order (D6) is kept; no cursor moves because of a reaction (A3, A5).
- [x] Scope: `reactions:write` is documented as needed for this feature alone; the failure mode without it is one warning per accepted message, loud by design.
- [x] Evidence redaction: every token in the tests and the evidence is a fixture string; no workspace, channel or member id in the evidence is real.

## Outcome

**Pass** on the autonomous checklist. No human sign-off required at tier 3; the pull
request's review is the human gate.
