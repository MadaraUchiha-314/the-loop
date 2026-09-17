---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#375"
---

<!-- Authored per the the-loop:writing skill. -->

# Self-review: a work item names the room it is worked in

> The `self-review` node's record: the diff re-read adversarially against the design,
> before any other reviewer sees it.

## What I went looking for

| # | Question | Answer |
|---|---|---|
| 1 | Can any part of a comment body reach a store, a path, an argv or an API call? | No. `parse_channel_ref` is total: it matches `<type>@<target>`, looks the type up in a fixed table, and matches the target against that type's regex. Every other input returns `None`. `parse_channel_refs` stops at the first token that is not a ref, so prose after a channel contributes nothing. `CollaborationChannel.from_dict` re-parses the stored `ref` rather than trusting the `type`/`target` beside it, so a hand-edited record cannot smuggle a value past the grammar either |
| 2 | Is a work item that declares nothing behaving exactly as it did before? | Yes, and a test pins it. `home_for` returns `config.channel` when nothing is declared; `_conversation`'s second case returns the existing binding untouched; `declared_work_item` answers `""` so the inbound path falls through to the pre-existing thread lookup; `fetch_channel_messages` returns `[]` when `targets()` is empty |
| 3 | Can a declaration deliver a message to the wrong work item? | Only through a contested room, which is refused on write **and** answered `""` on read. The one asymmetry worth naming: a binding wins over a room, which is what stops a declaration on the *central* channel re-attributing every other work item's thread in it |
| 4 | Can a message be processed twice, or dropped as a duplicate that was not one? | This was the one real bug the work found. `ChannelState.cursor(thread)` defaults to the thread's own root ts — correct for a reply, wrong for a message that **is** a root, which compares as already-seen. A room-attributed message equal to its own thread now uses the room's `channel:<id>` cursor, the same key the poll transport advances. Both directions are tested: first-sight baselining (nothing delivered) and repeated cycles (delivered once) |
| 5 | Does anything here widen who may speak? | No. Inbound authorization is `config.authorized_users`, untouched, and asserted directly in `test_an_unauthorized_member_in_the_room_is_still_dropped` rather than inherited from "we didn't change that file". Declaring is an action and goes through the dispatcher's named-and-allowlisted check, asserted in `test_an_unauthorized_author_declares_nothing` |
| 6 | Does the gate's new section risk being parsed as a phase? | No, and it is tested: the section contains no `- [ ]` line at all, which `_CHECK_LINE` is what reads |
| 7 | Does the new portable section survive the life cycle the others do? | `reset` clears it, the poller counts it as tracking, the dispatcher clears it on closure, and `state.py`'s `ATTRIBUTES` classifies it — the last of which is enforced by a test that fails when a file grows an unclassified key. That test caught the omission during implementation |

## What I changed after re-reading

- **The move's honesty.** The first draft's pointer message said "replies here still reach
  it" and a comment in `_conversation` claimed the old thread stayed mapped. Neither was
  true: a work item has one conversation, so the rebind orphans the old thread. The
  message now says replies there no longer reach it, the docstring says why the pointer
  exists at all, and the test asserts the old thread is unmapped rather than the opposite.
- **`declared_by`'s signature.** It took a `channel_type` parameter it used only to build
  a string the caller could have built. Removed.
- **The refusal message on `open`/`post` with no channel.** "no channel id configured" is
  no longer the whole truth — a work item can have a channel without the config having
  one — so both paths raise one message naming both routes. The existing test that
  asserted the old wording is updated rather than deleted, with a line saying why.

## Round 2 — the author's review of PR #376

The review overruled the narrowing this work item had chosen (*"Not an issue, we can
change the manifest. We should be able to do with channel name"*) and asked for two more
surfaces to accept names. What I went looking for the second time:

| # | Question | Answer |
|---|---|---|
| 8 | Does accepting names cost anything for a deployment that uses ids? | No, and it is asserted: an id short-circuits before any lookup in both `conversation_id` and `user_id`, `test_an_id_is_returned_without_a_lookup` pins the call count at zero, and `test_an_id_still_needs_no_directory_at_all` drives a whole post with no cache and no directory scopes |
| 9 | Can a lookup happen on the hot path? | No, by construction: what is stored is always an id (`CollaborationChannel.from_dict` **rejects** a record carrying a name), the central channel resolves once per `SlackBotChannel`, and only an allow-list **miss** on a handle reaches the directory. A message from a member whose id is listed costs a set membership test, as before |
| 10 | Can an unresolvable name widen anything? | No. Every failure is `""`, and `""` never matches a member id, so an allow-list entry that cannot be resolved contributes nothing. `test_an_unresolvable_handle_authorizes_nobody` asserts it rather than arguing it |
| 11 | Does a typo cost an API call per message? | No: a miss on a *fresh* map answers `""` without re-reading, so a refresh is at most one listing per TTL. `test_a_miss_on_a_fresh_map_does_not_re_read` pins the count |
| 12 | Did the two id regexes reject anything that used to work? | They did, and the suite caught it twice — `C9` in the channel tests and `C-OPS` in the standing-session tests. The rule is now the real invariant: Slack folds names to lowercase, so a token with no lowercase in it is an id, whatever its shape |

## Two bugs the tests caught, both mine

1. **`normalize_name` folded case before checking for an id**, so `dana` was upper-cased
   to `DANA`, matched `[CGD]…` as a conversation id, and resolved to nothing. The id
   checks now run on the text as given, which is also the only order that can work: the
   two kinds are distinguished *by* case.
2. **The "handle moved" warning could never fire.** `_lookup` served a cache hit at any
   age, so the cached and resolved ids were always equal by construction. Fixed with a
   `follow` flag that re-reads a stale map on a hit — for users only, because a
   conversation id is stable and a handle is not. Without it the accept-both feature was
   subtly broken in the other direction too: the mapping would have frozen at whatever
   the workspace said the first time this machine asked.

## What I deliberately did not do

- **Index display names.** The ask was for `@<slack-user-name>` — the handle, which
  Slack keeps unique. A display name is neither unique nor constrained, and
  `routing.authorizedUsers` has warned against exactly that since issue-309. Resolving
  one would have widened an authorization surface past what was asked for, so only the
  handle resolves. (An earlier draft of the directory indexed both; removed.)
- **Claim the handle caveat is solved.** The warning makes a reassigned handle loud, not
  safe. The option was put to the author with that cost stated; the documentation says
  it in a `::: warning` block rather than a footnote.
- **Post a refusal comment.** The dispatcher's refusals are a reaction plus an event-log
  line for every control command; adding a comment path for this one would be
  inconsistent and is its own work item (`design.md` §2, §6).
- **Widen the Slack ingress to work-item collaborators.** It reads `channels.slack`'s
  principals today. Changing that is a permission change and has nothing to do with rooms.
