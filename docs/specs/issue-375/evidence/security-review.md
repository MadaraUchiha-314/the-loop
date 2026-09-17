---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#375"
---

<!-- Authored per the the-loop:writing skill. -->

# Security review: a work item names the room it is worked in

> The `security-review` node's record, against `requirements.md` § Security
> considerations. See `skills/the-loop/reference/security.md`.

## The boundary this work item touches

Two, and both are narrow by construction:

1. **A new instruction a comment can carry.** `the-loop add-channel <type>@<target>` joins
   a fixed vocabulary of control keywords, reached only after the ingress guards that
   already exist (self-authored marker, authorized actor, scope) and then the command
   path's own **named-and-allowlisted-actor** re-check.
2. **A new way a message is attributed to a work item.** A message in a declared room is
   processed as a message on the declaring work item — through the *same* pipeline, with
   the *same* allow-list, classification, grants, ledger record and delivery.

Nothing here changes who may speak, who may direct the loop, or what a message may become.

## Abuse cases, and where each is closed

| # | Abuse case | Closed by | Asserted in |
|---|---|---|---|
| A1 | Payload text from an `add-channel` body reaches a path, an argv or an API call | `parse_channel_ref`: fixed shape, fixed type table, per-type target regex; refusal is `None`, never a repaired value. `parse_channel_refs` stops at the first non-ref token | `test_workchannels.py::test_anything_else_is_refused_not_repaired`, `test_control.py::test_nothing_but_a_channel_reaches_the_caller` |
| A2 | Two work items claim one room, so a message goes to the wrong one | `ChannelTakenError` on write; `declared_by` returns `""` for a contested room on read, so the failure is silence rather than misdelivery | `test_workchannels.py::test_a_contested_room_is_attributed_to_nobody`, `test_workchannels_integration.py::test_a_channel_another_work_item_holds_is_refused` |
| A3 | A work-item collaborator or an unlisted member declares a room, redirecting a work item's conversation | Declaring is an **action**: `Dispatcher.handle`'s named-and-allowlisted check runs before `_apply_channel`, and a collaborator cannot issue any control command | `test_workchannels_integration.py::test_an_unauthorized_author_declares_nothing` |
| A4 | An authorized user declares a channel outsiders are in, to expose a work item's conversation | **Accepted, and stated.** An authorized user can already read and relay any work item; this is not a new capability. What the declaration cannot do is let those outsiders *speak*: inbound authorization is `channels.slack`'s principals, unchanged | `test_channels_declared_integration.py::test_an_unauthorized_member_in_the_room_is_still_dropped` |
| A5 | Declaring the operator's central channel re-attributes every other work item's thread there | A thread **binding** wins over the room, so only messages no binding claims are attributed. What is suppressed there is the kickoff, deliberately — a declared room must not open issues | `test_channels_declared_integration.py::test_a_bound_thread_wins_over_the_room`, `::test_declaring_the_central_channel_stops_it_opening_work_items` |
| A6 | A room with months of history is declared and replays into the session | First-sight baselining, copied from the kickoff read: with no cursor the newest ts is recorded and nothing is returned | `test_channels_declared_integration.py::test_the_poll_read_baselines_a_room_before_delivering_anything` |

## Data handled

A channel id, the declarer's login, a timestamp and the declaring comment's URL — all of
them already present elsewhere in the same portable record, all of them the operator's
workspace's rather than the repository's, which is why the section sits in the operator's
file and not in `work-item-state.json`. No token, no secret and no message content is
stored by this change.

## Residual risk

**A declaration is cleared when the work item ends**, which frees the room for the next
one — so a room is never silently retained. Until then, an authorized user who declares a
room they should not have declared has moved a conversation; `the-loop remove-channel`
undoes it on the next event, and the thread already opened stays where it is (visible,
not hidden). This is the same reversibility the collaborator roster has.

**No new network call, scope or credential.** The Slack app manifest is unchanged: the
existing `chat:write` and `*:history` scopes already cover posting in and reading a channel
the bot is a member of. An operator must invite the bot to the room — a step the
declaration cannot take and does not fake; a room the bot is not in simply fails to post,
reported like any other post failure.

## Sign-off

No finding requires a change. The one accepted risk (A4) is a property of authorized
users, not of this feature, and is documented on the command's page and in the capability
doc rather than left implicit.
