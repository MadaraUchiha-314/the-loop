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

## Round 2 — names instead of ids (the author's review of PR #376)

Accepting names touches the authorization surface for the first time in this work item,
so the review is repeated for it rather than assumed to carry over.

| # | Abuse case | Closed by | Asserted in |
|---|---|---|---|
| A7 | Somebody takes a freed Slack handle and inherits an allow-list entry naming it | **Accepted, on the author's explicit decision, with the cost stated to them first.** A handle authorizes whoever holds it; the-loop re-reads a stale directory and logs a warning naming both member ids when the mapping moves, and the option's documentation carries a `::: warning` block saying a member id is the only form that names one person for good | `test_a_handle_that_moved_is_warned_about`; `docs/config/cli/routing-options.md` |
| A8 | A name is resolved to the wrong channel, so a work item's conversation lands elsewhere | Resolution happens **once, at declaration**, and the id is stored. A wrong name is refused while a human is watching rather than discovered at the first post, and no later message depends on a lookup | `test_a_name_that_resolves_to_nothing_is_refused` |
| A9 | The local directory cache is edited to point a name at an attacker's channel | The cache serves *declaration and display*. What the ingress routes on is the id already in the work item's record, which a cache edit cannot reach; the worst a poisoned cache achieves is one declaration sent to the wrong room, visible in the thread the-loop posts into. It cannot reach the allow-list in the widening direction either — see A10 | — |
| A10 | The cache is edited to map an allow-listed handle onto an attacker's member id | **Real, and the reason the documentation prefers ids.** It requires write access to `<state.root>/local/` on the machine running the-loop — which is already shell access to the daemon, and therefore already game over (the CLI verbs' authorization *is* shell access). It is not a new boundary, but it is one more thing an id-only allow-list does not have | — |
| A11 | A member's display name is set to match an allow-listed handle | Closed outright: display names are **not indexed**. Only `users.list`'s `name` (the handle, unique per workspace) resolves | `test_only_the_handle_resolves_never_the_display_name` |
| A12 | A missing scope silently degrades authorization | Fails closed and says so: a directory read that raises resolves to `""`, caches nothing, and logs which scope is likely missing. An entry that cannot be resolved authorizes nobody | `test_a_failing_read_resolves_to_nothing`, `test_an_unresolvable_handle_authorizes_nobody` |

### The new scopes

`channels:read`, `groups:read`, `users:read` — all three **read-only**, all three listing
metadata the bot can already see by being in the workspace. None grants a write, a post,
a message read or a membership change. The cost is operational rather than security: an
existing install must be re-installed for them to take effect, which the guide and the
capability doc both say.

### What is now cached on disk

`<state.root>/local/slack-directory.json`: channel names → conversation ids, handles →
member ids. No token, no message content, no email, no display name. It is **local, not
portable** — a snapshot of one workspace as one machine read it — and re-derivable from
Slack at any time, so deleting it costs one API call.

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

No finding requires a change. Three risks are **accepted rather than closed**, each
stated where an operator will meet it:

- **A4** — an authorized user can declare a room outsiders are in. A property of being
  authorized, not of this feature; inbound authorization is unchanged.
- **A7** — a handle authorizes whoever holds it. Put to the author with the cost stated,
  chosen deliberately, and documented in a warning block beside the key.
- **A10** — write access to the directory cache can redirect a handle. Equivalent to
  shell access on the daemon host, which is already total; named here so the preference
  for member ids has its full reasoning on the record.

Two findings from this round **did** change the code: display names are not indexed
(A11), and the handle lookup re-reads a stale directory so its warning can actually fire.
