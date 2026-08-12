# `ask`

Ask a human a question on the work item — the way a spawned agent escalates.

```bash
the-loop ask --work-item github:OWNER/REPO#N --question "Which auth mode?"
the-loop ask --work-item github:OWNER/REPO#N --question-file question.md
some-tool | the-loop ask --work-item github:OWNER/REPO#N --question-file -
```

## What it does

One verb, three effects — in this order:

1. **Posts the question** as a comment on the work item through your own `gh`
   (the issues endpoint serves PR conversations too), with the visible
   attribution line and the loop-prevention marker appended **centrally**. That
   stamping is the point ([issue-208](https://github.com/MadaraUchiha-314/the-loop/issues/208)):
   before this verb, every agent was trusted to remember the marker on every
   question, and one lapse turned its own comment into an event that resumed its
   own session.
2. **Records the wait** as a `session.awaiting_input` event — question text,
   the comment's URL, who asked. This is what makes the waiting session
   *observable*: [`GET /api/v1/attention`](/capabilities/control-plane) reports
   the work item as `awaiting-input`, and the dashboard's question card lights up.
3. **Leaves the answering to the reply route**: an operator answers either on the
   ticket (the poller forwards it, as ever) or straight into the session's pane
   via `POST /api/v1/sessions/reply`, which emits the `session.reply_sent` that
   closes the wait.

If `gh` fails, the exit code is 1 and the failure is printed — but the wait is
**still recorded** (`comment_posted: false`, level `warning`): the agent is
waiting whether or not GitHub was reachable, and the reply route can still carry
the answer.

## Flags

| Flag | Default | Meaning |
|------|---------|---------|
| `--work-item` | required | The ref the question goes to. |
| `--question` | — | The question text (markdown). |
| `--question-file` | — | Read the question from a file; `-` reads stdin. Exactly one of the two. |

## Notes

- Runs **in-process**, not through the control-plane service — deliberately, and
  unlike the other session verbs: this is the escalation path, the one verb that
  must keep working when no service is running (or in a cloud session that has
  no daemon at all).
- An empty question or malformed ref exits 2 and posts/records nothing.
- The stamp is idempotent: a question that already carries the marker is not
  double-stamped.
