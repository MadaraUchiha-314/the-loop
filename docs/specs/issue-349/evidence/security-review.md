# Security review — issue-349

> The ready-to-ship security gate (`security.review.required`, mechanism `auto`).
> **Risk tier 3**, so `security.review.humanSignOffMinTier: 4` does not apply: the
> owner's PR approval is the gate, and no named security sign-off is required.
> Date: 2026-09-11.

## What actually changed, from a security point of view

One sentence, because the rest of this document is checking it: **an untrusted party can
now hand the-loop a value that decides which repository an issue is written to, and
the-loop now holds a member's unsent message at rest.** Everything else — the grant, the
allow-list, the declared set, the ledger path — is untouched.

Three properties carry the whole review:

1. **A pick is a selector, never a string.** The pressed value is matched against the
   record's own offered set **and** the currently declared set, and what reaches the
   event is `DeclaredRepo.declared` — the operator's own configuration string. The
   member's value is never passed through.
2. **The question sits below the allow-list.** `process_kickoff` authorizes before it
   resolves, and the fork is below that, so an unlisted member sees no question and
   learns no repository name — the disclosure rule issue-341 R2.6 set for the refusal,
   applied to the bigger disclosure a question is.
3. **Every fault moves toward refusing.** Unreadable state, unwritable state, an
   unparseable payload, an undateable record, a repository the operator has since
   removed, a grant the operator has since revoked: each ends in "nothing was created".
   The last of those is the one worth stating on its own — the channel's permission is
   **re-read when the press arrives**, so a pending record can never outlive the
   authority under which it was created.

## Abuse cases, and what closes each

| # | Abuse case | Control | Test |
|---|---|---|---|
| A1 | A crafted `block_actions` payload carries the picker's `action_id` and a value outside the offered set (`../../etc`, `o/r; rm -rf /`) | Gate 5 of `process_kickoff_answer`: the value must be in the record's `options`. The string is never interpolated, never a path, never an argument | `test_abuse_1_a_crafted_value_outside_the_offered_set_creates_nothing` |
| A2 | The value **is** a real declared repository, but was never offered for *this* message (e.g. answering an `ambiguous-repo` question with a repository the prefix did not match) | Gate 5 again: the record's own offered set is the bound, checked before the declared set. Two bounds, so neither is the only one standing | `test_abuse_2_a_declared_repository_never_offered_here_is_refused` |
| A3 | An **unauthorized** member presses the picker | Gate 2, above the record read: the same fail-closed `authorized_users` check every inbound goes through. Nothing created, record untouched, **no message edited, no reaction added, nothing posted** — so the presser is not even told a question exists. This is where decision-111 D1 ("a refusal leaves no mark") is kept exactly | `test_abuse_3_an_unauthorized_presser_learns_nothing`, `test_an_unauthorized_press_still_leaves_no_mark` |
| A4 | An **authorized** member presses the picker on someone else's question | Gate 3 (decision-122 D5): the issue is opened as the person who wrote the message, so only they may direct it | `test_abuse_4_an_authorized_member_cannot_direct_anothers_message` |
| A5 | An unauthorized member posts a top-level message, hoping to be shown the repository list | The fork is below `process_kickoff`'s authorization check. The message is dropped in silence, nothing is posted and nothing is held | `test_abuse_5_an_unlisted_members_message_is_asked_nothing` |
| A6 | The picker is pressed twice — a double tap, or Slack redelivering the press | The record is **claimed** (popped) inside the state lock and the create happens outside it, so the second press finds nothing. Exactly one issue | `test_abuse_6_two_presses_of_one_question_open_one_issue`, and scenario 96 end to end |
| A7 | A pick arrives for an expired question | `pending_for` / `claim` treat a record past `PENDING_TTL_SECONDS` as absent, and an **undateable** one as expired rather than eternal. The refusal names no repository | `test_abuse_7_an_expired_pick_names_no_repository`, `test_an_undateable_question_is_expired_not_eternal`, scenario 97 |
| A8 | A hostile message body — `<!channel>`, 200 `@here`s, Block Kit markup, 4000 characters — is used to style the question, ping the channel, or blow past Slack's limits | Nothing of the member's message is rendered into the question at all: it is fixed words plus declared slugs, and every option's text is capped at Slack's 75. The held text stays intact, because that is what the issue is made from | `test_abuse_8_a_hostile_message_neither_styles_nor_sizes_the_question` |
| A9 | The state file is corrupt or unwritable | `ChannelState.load` already resolves a corrupt file to empty. Nothing is pending, so a press answers nothing — the failure mode is "the question cannot be answered", never "an issue is created without one" | `test_abuse_9_an_unreadable_state_file_asks_rather_than_creates` |
| A10 | The operator revokes `work-item.create` (or leaves Socket Mode) while a question is outstanding, and the member then presses | Gate 1, above everything: `kickoff_picker` is **re-read at press time**, not trusted from when the question went out. This is the one gate a pending record could otherwise smuggle a member past, and it is the only place in the change where held state could have outlived a permission | `test_a_revoked_grant_is_re_read_at_press_time`, `test_leaving_socket_mode_revokes_the_answer_too` |

Ten raised, ten closed.

## The checklist

| Item | Verdict |
|---|---|
| New attack surface | One: a `block_actions` payload with a new `action_id`. It enters through `handle_socket_action`, which already accepts payloads from the same transport, and is judged by five gates before anything is written — the first of them the channel's own permission, re-read at press time. |
| New authority | **None.** `kickoff_picker` = `read.mode: socket` **and** the `work-item.create` grant that reaching the kickoff already requires. No grant, no scope, no config key, no schema change. |
| Untrusted input reaching a command argument | No. The pressed value is matched, not passed; `DeclaredRepo.declared` is what reaches the event, as `resolve_target`'s output already did. |
| Authentication / authorization | Unchanged mechanism, applied in a new place. Fail-closed: an empty `authorized_users` denies everyone. |
| Secrets | None read, stored or rendered. The question is fixed words plus declared slugs; the event log carries ids and counts only. |
| New data at rest | Yes — see residual risk 1. |
| Injection (command, path, template) | The value never becomes a path or an argument. The rendered question interpolates no member text. |
| Denial of service | `PENDING_CAP` (50) bounds the map; a flood of questions costs one dict entry each and evicts the oldest. The reads are one key in a file the pipeline already loads. |
| Logging / disclosure | `channel.kickoff_asked` carries channel, actor, thread, outcome name and a **count** — never the message text and never a repository name. A refused press writes a fixed line from `KICKOFF_REFUSALS` onto the question, naming no repository, no other member and no config value — and only for a presser who already passed the allow-list and can therefore already read that question. |
| Fail closed | Every fault path refuses. Asserted, not asserted-to. |

## Residual risks

1. **the-loop now holds a member's unsent message text at rest**, which it never did.
   It lives in `<state.root>/channels/slack.json` — a file that already holds Slack
   thread and member ids, is explicitly **local, never portable**, and is not tracked by
   any repository. It is bounded twice (24 hours, 50 records) and removed the moment the
   question is answered. The exposure is: anyone who can read that file on the host can
   read messages that were never filed. That is the same party who can already read every
   thread binding and, in practice, the bot token's environment — so it widens what a
   host compromise yields without widening who can compromise the host. Shortening the
   TTL is a one-constant change if a reviewer wants it tighter.

2. **The question is one more message in the channel than a refusal was** — and it
   enumerates the declared repositories as options rather than as prose. It reaches only
   members who have already passed `routing.authorizedUsers`, which is the same audience
   the refusal's candidate list already reached, so the *set of people* who can learn the
   repository names is unchanged. What changes is that they learn it by tapping rather
   than by reading. Noted rather than mitigated: it is the feature.

3. **`poll`-mode operators get none of this** and are told so by `channels status` rather
   than by a member who did not get a question. Not a security risk — a usability
   asymmetry, recorded here because decision-122 D1 accepted it deliberately and a
   reviewer should be able to disagree with it in one place.

## Verdict

**Pass.** No new authority, no new grant, no untrusted string reaching a command, ten
abuse cases closed by ten negative tests, and one new class of data at rest that is
bounded, local, re-authorized on use, and named above.
