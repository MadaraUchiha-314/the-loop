# Live Slack (T4)

Run on 2026-11-20 at `93ba24e5`, against the operator's workspace, in the channel
the author named (`<channel>`). Correction: that channel is this work item's room,
not a dedicated test channel. The test now refuses such a channel (see below). The bot token was passed by reference
(`THE_LOOP_SLACK_BOT_TOKEN`) and never printed.

```text
cd cli && THE_LOOP_LIVE_SLACK=1 THE_LOOP_LIVE_SLACK_CHANNEL=<channel> \
  THE_LOOP_LIVE_SLACK_REPORT=<path> \
  uv run python -m pytest -q -m live_slack tests/test_slack_live.py
1 passed, 1 skipped (the cleanup test, which runs only with THE_LOOP_LIVE_SLACK_CLEANUP=1)
```

## Read-back, as the test reports it (redacted: no ids, no names)

- **top block types:** ["section", "actions"]
- **part block types:** [["rich_text", "header", "rich_text", "table", "rich_text"], ["rich_text"]]
- **table drawn as a table block:** true
- **parts read back:** 2
- **part order:** ["(1/2)", "(2/2)"]
- **preview after post:** [false, false, false]
- **live sequences after post:** []
- **javascript link after post:** false
- **edit kept the message:** true
- **preview after edit:** [false, false, false]
- **reactions:** [["hourglass_flowing_sand"], ["gear"], []]

## What it shows

- **R2.1, R2.2: drawn natively.** Slack stores each `markdown` block as the blocks it
  drew from it: `rich_text`, `header` and `table`. The GitHub table arrived as a
  real Slack `table` block. The task list and nested lists arrived as `rich_text`.
- **R2.6: order and marks.** Two parts, read back in order, marked `(1/2)` and
  `(2/2)`. The 260-line code block split across them.
- **R5: no previews, on post or edit.** No message carries `attachments` after the
  post. None does after a `chat.update` edit either, although `chat.update` takes no
  unfurl flags. Design.md left this to be checked live.
- **Abuse cases 1, 2 and 4: defused.** The line read back as plain text:
  `Defused: <!here> <!channel> @U00000000 click (javascript:alert(1)) and
  <https://example.com|a label>.` No broadcast or user-mention element was created,
  and no link has a `javascript:` URL. No literal `&lt;` shows. That answers the
  open point from task 5 for prose; the sample code contained no `<`.
- **R8: one status reaction.** ⏳ (`hourglass_flowing_sand`), then ⚙️ (`gear`), then
  none. Each swap removed only the reaction it had added.

## Two findings that changed the test, not the feature

1. Slack converts `markdown` blocks on storage, so "every part reads back as a
   `markdown` block" was the wrong assertion. The test now asserts that every part
   holds blocks and that the table arrived as a `table` block.
2. `reactions.get` needs `reactions:read`, which the shipped manifest does not
   request. The test reads reactions from the message itself instead. The feature
   never reads reactions, so it needs no new scope.

The posted messages were first kept for the Slack client screenshots in T5. The
author asked on PR #550 that live checks never show in a channel people read, so:

- they were deleted (`THE_LOOP_LIVE_SLACK_CLEANUP=1`; only the room's opening
  message is left);
- the keep option was removed: the test always deletes what it posts;
- the test now stops before posting when the bot has posted anything but live
  checks in the channel. Run against this room again, it failed with that message
  and posted nothing.
