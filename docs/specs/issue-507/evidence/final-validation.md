---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#507"
---

# Final validation: answer a Slack mention in the thread it came from

Every acceptance criterion in the ticket and in `bugfix.md` is covered by a test that ran
and passed, and the regression test was red on `origin/main`. This table summarises
`testing-plan.md`'s Verification results. The full suite, lint and types pass
([lint-and-typecheck.md](lint-and-typecheck.md)).

## Final validation evidence

| Acceptance criterion (ticket #507 → bugfix.md) | How it was proved | Where |
|------------------------------------------------|-------------------|-------|
| An agent comment answering a Slack-origin `work-item.reply` is posted with the originating thread's `thread_ts` (R1.1, R1.2, R3.3) | T2.1: mention in room thread `1700.000100`, then `comment.agent` → `chat.postMessage(C0TMP375, thread_ts=1700.000100)`; red on main | [integration.md](integration.md) |
| `channel.posted` names the thread the answer went to (R1.4) | T2.1: `PostResult.thread == 1700.000100`, the value the bus logs as `thread` | [integration.md](integration.md) |
| It holds until another thread's mention replaces it (R1.3, R2.1) | T2.2 (two answers, both in T); T2.3 (a mention in U moves the answer to U) | [integration.md](integration.md) |
| Conversation-starting events stay top-level and end it: gate prompts, phase changes (R2.3) | T2.5 `phase.started`, T2.6 `phase-approval-pending`: each posted top-level, and the next answer is top-level; `phase.progress` does not end it | [integration.md](integration.md) |
| A top-level mention is answered at the top level; nothing changes without a mention (R2.2, R2.4) | T2.4, T2.8 | [integration.md](integration.md) |
| RoomPolicy's own decisions stand (R1.5) | T2.7: the session-started cheat-sheet is still dropped with a reply thread set | [integration.md](integration.md) |
| Never worse than today: failures, other channels, undelivered replies (R3.1, R3.2) | T4 (save fails → delivered, top-level); abuse 2 (other channel → top-level); critic C1 (undelivered mention keeps the earlier thread); C3 (malformed values → `""`) | [unit.md](unit.md), [integration.md](integration.md) |
| Only an authorized speaker steers the answer (abuse 1) | T3: an unauthorized thread mention is refused and leaves no reply thread | [integration.md](integration.md), [security-review.md](security-review.md) |
| The ticket's open question (is there a setting or verb that follows a thread?) | Answered in `bugfix.md` and `docs/guide/slack.md`: there is none, and following the asker's thread is now the default | [documentation.md](documentation.md) |

Socket Mode and `read.mode: gateway` share this path: both hand Slack events to
`inbound.handle_socket_event` on the instance, and the post happens there too. No test
in this work item runs a gateway end to end. The design records that equivalence.
