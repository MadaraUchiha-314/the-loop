<!-- Written per the `the-loop:writing` skill. -->

# Decision 154: Slack gets a short form the agent writes, and a declared room gets the whole text in its thread as Slack markdown

- **Status:** accepted
- **Date:** 2026-11-19
- **Deciders:** MadaraUchiha-314 (the answers on PR #550, the approvals), the-loop
  (the mechanism)
- **Work item:** [issue-549](https://github.com/MadaraUchiha-314/the-loop/issues/549)
- **Spec:** [`docs/specs/issue-549/`](../specs/issue-549/)
- **Supersedes:** [decision-118](decision-118.md), the structural digest above
  `maxChars`

## The short version

Every Slack message from the-loop now has two parts:

- **The short form.** The agent writes it, for a phone, and it is the message.
- **The long form.** The whole text. In a declared room it goes in the message's
  thread, as Slack `markdown` blocks, never cut. In the central channel, where each
  work item already lives in one thread and Slack cannot nest threads, it is not
  posted at all, and the short form links to GitHub.

The digest, `maxChars` and `longMessages` are retired. Link previews are off. Work-item
refs compare without regard to the case of the GitHub owner or repository, so gate
messages and their Approve buttons reach the work item's own conversation.

## Context

decision-118 condensed long text to fit a cap, so that a phone reader got the ask
first. In use, the cut still lost words, tables became pointers, and mrkdwn could not
draw tables under the cap either. The owner asked for the whole text on Slack and, at
the same time, for a short phone-sized message (issue-549).

Slack's `markdown` block now draws standard markdown, tables and task lists included,
up to 12,000 characters per message. That removes the reason to translate GitHub
markdown ourselves.

## Decision

1. **Two forms per message.** The short form is the agent's summary (`--summary` on
   `the-loop comment` and `the-loop ask`). For a runtime event it is the fixed lead.
   With neither, it is built from the first question or sentence, and the gap is
   logged.
2. **Placement is a fixed rule.**
   - **Room:** the short form is the top-level message, and the long form goes in its
     thread.
   - **Central channel:** the short form only, as a reply in the work item's thread.
   - **Mention thread in a room:** both forms, in that thread.
3. **The long form is Slack markdown.** It is defused first (markers stripped,
   broadcasts and mentions neutralised, unsafe link schemes made text). Then it is
   split between top-level blocks into parts that fit one message. An oversized
   table or code block falls back to a code block split at lines.
4. **Delivery is idempotent and preview-free.** Each event carries an id, and the
   parts posted for it are remembered, so a replay resumes after the last part that
   landed. Every post turns unfurls off.
5. **`maxChars` and `longMessages` are deprecated and ignored.** They stay valid in
   the schema, and a config that sets them loads with a warning.
6. **Ref identity is case-insensitive for the GitHub owner and repository,** and the
   graph verbs keep the registered spelling.

## Consequences

- A room carries the whole conversation. The central channel carries headlines only.
- Phase starts and ends move from messages to one status reaction and a recap line
  after a gap.
- The Slack gateway's allow-list gains `reactions.remove` and `chat.delete`. No new
  bot scope is needed.
- How Slack treats defused sequences inside a `markdown` block, and unfurls on edit,
  is not documented, so both are checked live at verification.

## Alternatives rejected

- **A higher cap on the digest.** Words are still lost, and tables are still not drawn.
- **The long form in the central channel**, as the next reply in the item's thread.
  The owner chose short only there.
- **A "show more" control.** Slack has no collapsible block that the app controls.
- **Table blocks for tables.** The `markdown` block draws tables without a cell-by-cell
  conversion.
