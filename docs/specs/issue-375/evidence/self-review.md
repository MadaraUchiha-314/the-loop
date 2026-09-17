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

## What I deliberately did not do

- **Resolve `#names`.** It would need a new OAuth scope on every existing install
  (`design.md` §1). The refusal says what to type instead.
- **Post a refusal comment.** The dispatcher's refusals are a reaction plus an event-log
  line for every control command; adding a comment path for this one would be
  inconsistent and is its own work item (`design.md` §2, §6).
- **Widen the Slack ingress to work-item collaborators.** It reads `channels.slack`'s
  principals today. Changing that is a permission change and has nothing to do with rooms.
