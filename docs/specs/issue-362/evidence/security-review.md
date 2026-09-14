---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#362"
---

# Security review: a DM is a channel like any other

**Verdict: pass, with no unresolved findings.** Reviewed against the six abuse cases of
[`bugfix.md`](../bugfix.md) § Security considerations, plus one case raised during this
review (AC7) that the design already answered.

This change **widens what the bot may read** — two new OAuth scopes — so the widening is
the subject, not an aside. It also adds a diagnostic that calls Slack and prints part of
what it learns, and a loop that re-reads a channel on a timer. Each is examined below.

## The abuse cases

| # | Case | Boundary | Verdict | Where it is proved |
|---|------|----------|---------|--------------------|
| AC1 | `im:history` lets the bot read every DM in the workspace | Slack's scope model | **Not possible.** `im:history` grants history only for conversations the bot is a **member of**, and a bot cannot be a member of a DM between two humans — the only IMs it can read are its own. `mpim:history` is the same for group DMs it was invited to. The scope is also opt-in per installation: an operator who never reinstalls the app gains nothing and loses nothing | Slack's OAuth scope semantics; the manifest is inert until an operator imports and reinstalls it |
| AC2 | Subscribing to `message.im` makes the-loop *act* on messages from a conversation it did not before | the inbound allow-list | **Unchanged authority.** A new *event* is not a new *authority*. `inbound` authorizes every message against `routing.authorizedUsers` before classification, a reply is bound to a thread the-loop itself opened, and a top-level message needs the `work-item.create` grant. An unauthorized author in a DM is dropped exactly as in a public channel — and always was, since the catch-up read has been processing those same DM messages all along | `test_channels_dm_integration.py::test_a_message_im_envelope_reaches_the_inbound_pipeline` (the event reaches the *unchanged* pipeline); the allow-list's own negative tests in `test_channels_integration.py`, untouched |
| AC3 | The doctor leaks the bot token or the channel's contents | `channels status` / the probe | **Pass.** The probe's result carries the conversation kind, the *names* of granted scopes and the findings — never a message, a member, or a token. `x-oauth-scopes` is a response header carrying no secret. `status` keeps printing token **presence** only | `test_probe_prints_no_token_value` (asserts the token string is absent from the whole serialized result) and `test_status_probe_prints_the_confirmed_finding` (asserts it is absent from stdout) |
| AC4 | The probe becomes a way to make the-loop call an arbitrary Slack endpoint | the probe's call list | **Pass.** Exactly two calls, both fixed: `conversations.info` on the operator's **own configured** channel id, and `auth.test` with no argument. No value comes from a message, a button, a ticket or a CLI argument | `test_probe_calls_only_conversations_info_and_auth_test` asserts the recorded call list verbatim |
| AC5 | The periodic reconcile replays a gate answer or opens a second issue | the shared cursors | **Pass.** A reconcile *is* `inbound.poll_once` — the same function the connect-time catch-up and `the-loop channels poll` already call. It advances the per-thread cursor under the state file's lock and drops anything at or before it as `duplicate`; the kickoff cursor works the same way. Running it more often changes the frequency, not the semantics | the existing `test_a_socket_listener_catches_up_after_downtime` in `test_channels_integration.py` (a second catch-up processes nothing; a redelivery is `duplicate`), which is now the reconcile's proof as well |
| AC6 | `catchUpSeconds: 1` turns the reconcile into an unthrottled API loop | the schema and the parser | **Pass.** `minimum: 0` in the schema, and the parser clamps any non-zero value below 60 to 60 with a warning rather than honouring it — a config that bypasses the schema (built in-process, hand-edited) is clamped too | `test_catch_up_seconds_below_the_floor_is_clamped_to_60` (parametrized 1 / 30 / 59) |
| AC7 | *(raised in review)* A finding discloses your workspace's shape to whoever can read the terminal or the log | the finding's content | **Accepted, no change.** A finding names the channel id the operator configured, the kind Slack reports for it, and scope/event names from a fixed table. All four are already in the operator's own config or in the shipped manifest. It is printed to the operator's own stdout and the instance's own log, at the same trust level as `channels status`'s existing output | `test_a_dm_without_im_history_is_a_finding_that_names_all_four_facts` enumerates exactly what a finding contains |

## Availability, which is the direction that matters here

The defect itself is the security-relevant part, and it runs the *other* way. A human's
**"request changes"** on an approval gate, typed in a DM, was not read for hours — while
the **Approve button** beside it was read instantly, because an interactivity payload is
not a message event. A control that arrives late while its counterpart arrives at once is
a real asymmetry in a review gate, and closing it **restores** a control rather than
relaxing one. The periodic reconcile bounds the same asymmetry for every future cause.

## Fail-quiet, deliberately

Three places where this change chooses to say **nothing** rather than risk saying
something wrong, each with a test:

- unreadable `x-oauth-scopes` → no finding (`test_unreadable_scopes_are_never_a_finding`);
- an ambiguous prefix with one candidate scope granted → no finding
  (`test_a_public_prefix_is_never_a_finding_when_either_candidate_is_granted`);
- a probe that raises, or cannot run → a skip reason, exit 0, and the listener still
  listens (`test_probe_skips_without_a_token_a_channel_or_on_an_api_error`,
  `test_a_probe_that_raises_never_keeps_the_listener_from_listening`).

This is the right default for a *diagnostic*: a warning that fires on a working
configuration is one operators learn to route around, which would cost the real finding
its audience. It is **not** the default anywhere the change touches an authorization
decision — there is no such place, because the allow-list, the grants and the cursors are
all untouched.

## Not in scope, and why that is safe

No new grant, no new state, no new config version, no new network endpoint reachable from
outside, and no change to who may do what. `the-loop` still exposes no Request URL
(decision-116 D5); the probe and the reconcile are both **outbound** calls on the
operator's own credentials.
