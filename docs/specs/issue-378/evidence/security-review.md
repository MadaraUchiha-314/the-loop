---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#378"
---

<!-- Authored per the the-loop:writing skill. -->

# Security review: a work item's whole life is told to every channel, and Slack can begin one

> The `security-review` node's record, against `requirements.md` § Security
> considerations. See `skills/the-loop/reference/security.md`.

## The boundaries this work item touches

1. **A new inbound instruction**: `/the-loop new <text>`, where the text is prose that
   becomes an issue's title and body. It enters through the slash-command pipeline's
   existing order — allow-list, trigger dedup, parse, grant — and its repository is
   resolved by the kickoff's grammar against the operator's declared set.
2. **New outbound events**: three lifecycle rows composed from ids and fixed words,
   fanned out by the bus to subscribed channels, never recorded on the ledger.
3. **A new conversation shape**: a declared room as the conversation. It changes where
   the-loop *posts*; what it *reads*, and from whom, is unchanged.

Risk tier stays **3**: the two schema files change only a description string (as
issue-338 did), no route, grant, scope or credential path is added, and nothing widens who
may speak or what a message may become.

## Abuse cases, and where each is closed

| # | Abuse case | Closed by | Asserted in |
|---|---|---|---|
| A1 | `new` text reaches a repository argument, a path or an argv | `resolve_target` → `DeclaredRepo.declared`; the ledger receives a config string | `test_new_refuses_what_the_kickoff_refuses` (four refusals create nothing), `test_new_opens_the_work_item_and_its_thread` (the declared slug) |
| A2 | An unlisted member files issues | authorized before the text is read | `test_new_from_an_unlisted_member_creates_nothing` |
| A3 | A channel without the grant opens work items | `FAMILY_GRANTS["create"] == "work-item.create"` | `test_new_needs_the_create_grant` |
| A4 | A replayed payload files twice | the trigger ring | `test_new_acts_once_per_trigger` |
| A5 | A lifecycle event leaks text | fixed words + ids; nothing read from artifacts or comments | `test_lifecycle_text_is_fixed_words_and_ids`, `test_a_closed_issue_is_announced_before_its_room_is_forgotten` (text asserted) |
| A6 | A transition writes a ledger comment under the operator's credential | `record=False` forced in `publish_lifecycle`; the catalog rows are unrecorded | `test_the_lifecycle_rows_are_subscribable_never_publishable_never_recorded`, `test_publish_lifecycle_never_records_and_never_raises` |
| A7 | The closure lands in a room since claimed by another item | published before the clear | `test_a_closed_issue_is_announced_before_its_room_is_forgotten` |
| A8 | The room mode lets somebody reach the work item who could not before | inbound attribution and authorization untouched | `test_a_reply_under_a_room_message_reaches_the_work_item` (same allow-list), the issue-375 inbound suite unmodified |
| A9 | A forged room record posts elsewhere | a record whose channel is not the home is moved to the home, as a thread record is | `test_a_thread_declared_into_a_room_moves_to_the_room_as_a_room` |

## Fail-closed checks

- No `channels` section → no lifecycle event is built (`test_publish_lifecycle_builds_nothing_without_a_channels_section`).
- No grant → no `new`; no declared repository → no creation; an unreadable declaration →
  the central channel (`home_for` unchanged).
- A broken provider loader hides no other channel and loads nothing itself.

## Verdict

**Pass.** No finding open; no security-relevant decision needed from a human; below the
tier-4 named sign-off threshold.
