# `ask`

Ask a human a question on the work item — the way a spawned agent escalates.

```bash
the-loop ask --work-item github:OWNER/REPO#N --question "Which auth mode?"
the-loop ask --work-item github:OWNER/REPO#N --question-file question.md
some-tool | the-loop ask --work-item github:OWNER/REPO#N --question-file -
```

## What it does

One verb, three effects — in this order:

1. **Posts the question** as a comment on the work item under the daemon's GitHub token
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
3. **Leaves the answering to a person**: an operator answers either on the
   ticket (the daemon forwards it, and records `session.ask_answered` when the author
   is authorized) or straight into the session's pane via
   `POST /api/v1/sessions/reply`, which emits `session.reply_sent`. Either record
   closes the wait.

If the post fails, the exit code is 1 and the failure is printed — but the wait is
**still recorded** (`comment_posted: false`, level `warning`): the agent is
waiting whether or not GitHub was reachable, and the reply route can still carry
the answer.

## Asking without blocking

Give the question a default and a deadline when a person's view is worth having but not
worth waiting for
([issue-551](https://github.com/MadaraUchiha-314/the-loop/issues/551)):

```bash
the-loop ask --work-item github:OWNER/REPO#N --question "Rename the flag to --until?" \
    --default "Yes, rename it" --after 30m
```

- The posted question states the default and the time it is taken. The command prints
  the same time, and tells the session to carry on with work that does not depend on
  the answer.
- **An authorized answer before the deadline wins.** It is delivered as usual and the
  default is not taken. A reply from someone who is not authorized changes nothing.
- **At the deadline** the daemon tells the session to proceed with its default, posts
  "default taken" where the question was asked, and closes the ask
  (`session.ask_default_taken`). This is not an approval: no human gate accepts a
  default as its answer.
- **An answer after the deadline** still reaches the session, as a comment, so it can
  correct course.
- **The minimum wait** is the operator's
  [`routing.asks.minDefaultWaitSeconds`](/config/cli/routing-options#asks-mindefaultwaitseconds)
  (default 30 minutes). A shorter `--after` is raised to it, and both the output and
  the question say so.

A question asked without `--after` waits for a person, however long that takes. It gets
**one reminder** where it was asked, after
[`routing.asks.reminderSeconds`](/config/cli/routing-options#asks-reminderseconds)
(default 2 hours), and no more.

## Flags

| Flag | Default | Meaning |
|------|---------|---------|
| `--work-item` | required | The ref the question goes to: `github:…`, or `jira:<site>/<KEY>-<n>`, where the Jira ledger records it on the ticket with the visible self-marker. |
| `--question` | — | The question text (markdown). |
| `--question-file` | — | Read the question from a file; `-` reads stdin. Exactly one of the two. |
| `--default` | — | The answer to take if nobody objects. A channel that takes button presses offers it as a one-tap reply. |
| `--after` | — | How long to wait before the `--default` answer is taken: `45s`, `30m` or `2h`. It needs `--default`. A wait under `routing.asks.minDefaultWaitSeconds` is raised to it, and the output says so. The question states the default and the time; an authorized answer before that time cancels it. |

## Notes

- Runs through the [control-plane service](/cli/service) when one answers, because
  the service holds the credentials
  ([issue-482](https://github.com/MadaraUchiha-314/the-loop/issues/482)). With no
  service it runs in-process, with a note: this is the escalation path, and it must keep
  working in a cloud session that has no daemon. A session the daemon spawned holds no
  credential, so there it exits 2 without a service.
- An empty question or malformed ref exits 2 and posts/records nothing. So does
  `--after` without `--default`, and an `--after` that is not a duration.
- The stamp is idempotent: a question that already carries the marker is not
  double-stamped.
