---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#549"
---

# Self-review: the Slack collaboration experience

The operator's review policy (`the-loop critic policy`) sets 2 self-review rounds and
1 critic round, stopping early when a round finds nothing new. Both self-review rounds
ran. Each was a fresh read of the diff against `requirements.md` and `design.md`, by a
reviewer that had not written the code. Every finding was reproduced before it was
fixed, and every fix has a regression test that fails on the code before the fix.

## Review cycles

| Round | Reviewer | Scope | Outcome | Findings → disposition |
|-------|----------|-------|---------|------------------------|
| 1a | self (fresh subagent) | delivery, state, status, preamble | new findings | 5 found, 5 fixed (+1 smaller, fixed) |
| 1b | self (fresh subagent) | rendering, defuse, placement, gates, identity | new findings | 3 found, 3 fixed |
| 2 | self (fresh subagent) | the round-1 fixes, and the rest of the diff | new findings | 4 found, 4 fixed |

Fixes: `2079a303` (round 1) and the round-2 commit that carries this record.

## Round 1 findings

**R1-1 (high): a nested link became a live broadcast or mention.** `[lbl]([a](!channel))`
went through `defuse` with the inner link intact, and the mrkdwn step then drew it as
`<!channel|a>`. Anyone who could comment on the issue could page the channel.
**Fixed:** `mrkdwn` draws `<url|label>` only for `http`, `https` and `mailto` targets,
and `defuse` breaks any `](` that opens an unsafe target.

**R1-2 (high): the splitter hung on a code block whose fence line was longer than a
part.** With an empty body, the block's text was dropped instead. **Fixed:** an info
string too long to repeat goes into the body as text, and a cut always moves forward.

**R1-3 (medium): some `javascript:` link forms were left as links.** These were links
with a title, with nested brackets in the label, with a space before the target, and
reference definitions inside a quote or with the target on the next line (abuse
case 4). **Fixed:** they render as text.

**R1-4 (medium): a rate-limited edit of the progress message posted a second one.**
**R1-5 (medium): a rate-limited edit of a reply posted a copy at the end of the thread.**
**Fixed, both:** `chat.update` retries a 429. It falls back to a fresh post only when
Slack says the message cannot be edited (`message_not_found`, `cant_update_message`,
`edit_window_closed`). Any other failure raises, so the outbox retries the edit and
nothing is posted twice.

**R1-6 (medium): every long-form reply carried the mentions** in its `text` fallback
(R7.4). **Fixed:** a part's fallback is the short form without its preamble.

**R1-7 (medium): one failed directory lookup meant nobody was ever mentioned for that
wait.** **Fixed:** a wait whose mentions resolved to nobody is not recorded as
announced, so the next message of the wait tries again. An identity that never
resolves still mentions nobody (abuse case 6).

**R1-8 (low): when an old record aged out of the delivery memory, a progress edit
re-posted its whole long form.** **Fixed:** the records of live progress messages are
kept past the cap (refined in R2-2).

**R1-9 (low): a 429 when closing a gate left its buttons on the message.** **Fixed:** the
close retries.

## Round 2 findings

**R2-1 (high): the R1-2 fix was incomplete.** A fence marker of thousands of backticks
still left no room in a part. It split the body one character per part: 8,000 posts
from a 20 KB comment. **Fixed:** a block whose fence marker is over a quarter of a part is
split as plain lines, every character kept, each part within the budget.

**R2-2 (low): the cap kept the wrong record.** It kept only a progress message's newest
record, but that is the edit in flight, which skips its own record. The edit needs the
one before it. **Fixed:** the newest two records per live progress message are kept.
The number of kept records is still bounded by the number of phases.

**R2-3 (low): the R1-9 change moved the client lookup outside the `try`.** A missing
token while closing a gate then raised past the record. **Fixed:** it is back inside,
logged and recorded as `channel.gate_closed` with the error.

**R2-4 (low): the short form was built a second time** to get the parts' fallback. That
logged `channels.short_form_missing` twice and doubled the R3.4 metric. **Fixed:** the
fallback is derived from the short form already built.

## Checked and found sound

- **Gate presses:**
  - the allow-list is checked before the graph;
  - a stale press is refused;
  - a press in a room resolves the right work item.
- **Identity:** `identity_key` case-folds owner and repo only.
- **Status reaction:** only the reaction the-loop added is ever removed.
- **Delivery memory:** a replay skips what already landed, and every timestamp is
  recorded before the next call.
- **`--summary`:** wired through the CLI, API, OpenAPI, MCP tool, facades and both
  trackers.
- **Event ids:** an id is minted once, in `publish`.
- **Removed and deprecated:** nothing imports `digest.py`, and the deprecated config
  keys still validate.
- **Injection:** `<!subteam^…>`, `<@U…>`, pre-escaped `&lt;!channel&gt;`, and pipes in a
  safe URL all come out inert.

## CI parity

`uv run pre-commit run --all-files` after round 2: 7,370 passed and 2 skipped.
`test_session_secrets_integration.py::test_issue_485_a_spawned_server_and_its_pane_hold_no_secret`
failed once under full-suite load. It passes when run alone. It spawns a server process,
and this PR touches no session or secrets code, so it is recorded as an unrelated flake,
not skipped.
