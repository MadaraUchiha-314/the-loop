---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#549"
---

# Critic review: the Slack collaboration experience

The operator's review policy sets 1 critic round. The configured critic is `codex`
(`gpt-6.1-sol`, run by `the-loop critic run codex`). The round's prompt excluded the
findings self-review had already fixed (`self-review.md`).

## Review cycles

| Attempt | Scope | Outcome |
|---------|-------|---------|
| 1 | the whole diff | **timed out** at 900 s; nothing returned |
| 2 | the core files, 1,800 s limit | **timed out**; nothing returned |
| probe | "reply ok" | ok in 4 s: the critic works, but the whole diff is too large for one call |
| 3 (the round) | three focused calls, in parallel: (a) defuse, mrkdwn, shortform; (b) delivery and the posted memory; (c) render | ok in 68 s, 23 s and 39 s: 7 findings |

The round is recorded as 1 critic round, split three ways by file so that each call
fits within the limit.

## Findings → disposition

| # | Where | Severity | Finding | Disposition |
|---|-------|----------|---------|-------------|
| C1 | `shortform.py` built form | medium | A URL of more than 580 characters pushed the built short form past 600 | **Fixed**: a link longer than half the cap is left to the "Open on GitHub" button |
| C2 | `delivery.py` | high (as reported) | A crash, or a response lost after Slack accepted a post but before its ts was recorded, re-posts it on retry | **Accepted, not fixed.** `chat.postMessage` has no idempotency key. The design's guarantee is "a retry posts only what is not recorded", and each ts is recorded right after its call. The window is one call wide. Closing it would need a history search before every post, at the cost of a call per message. |
| C3 | `delivery.py` | medium | When a middle reply was deleted, its replacement was posted at the end, so the thread read `[B′, A′]` | **Fixed**: from the missing reply on, every part is posted fresh in order, and the old replies after it are deleted |
| C4 | `render.py` fence scan | medium | A line such as "```KEEP" inside a code block closed it, and the split lost that line | **Fixed**: only a bare fence (the fence character alone) closes a block |
| C5 | `render.py` `table_as_code` | medium | A data row that looks like a rule (`\| --KEEP \|`) was dropped | **Fixed**: only the second line can be the rule line |
| C6 | `render.py` `table_as_code` | medium | A ragged table (one wide row, many short ones) cost width × rows to pad | **Fixed**: such a table is kept as written, in linear time |

Each fix has a regression test that fails on the code before the fix.
