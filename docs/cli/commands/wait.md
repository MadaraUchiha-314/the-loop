# `wait`

Declare what a session waits for, and until when. A session uses it when it waits on
something that is not a person: CI, another session, a build it started.

```bash
the-loop wait --work-item github:OWNER/REPO#N --for "CI on PR 12" --until 30m
```

## What it does

1. **Records the wait** as a `session.wait_declared` event with the condition and the
   time the wait ends.
2. **Lets the turn end.** The Stop gate allows the one stop that ends the turn the wait
   was made in, with the reason `declared-wait`
   ([issue-551](https://github.com/MadaraUchiha-314/the-loop/issues/551)).
3. **Prints when the wait ends**, and that it covers only this turn's stop.

When the wait ends, the session is idle from that moment, and the idle watcher treats it
as any idle session.

A wait covers **one stop**. If a new turn starts and the session still waits, it declares
the wait again. One wait cannot excuse every later stop until it ends.

## Flags

| Flag | Default | Meaning |
|------|---------|---------|
| `--work-item` | required | The session's own work item: `github:…` or `jira:<site>/<KEY>-<n>`. |
| `--for` | required | What the session waits for, in a few words. At most 200 characters. Shown on the status surfaces. |
| `--until` | required | How long the wait lasts: a whole number and one unit, as in `45s`, `30m` or `2h`. |

## What it refuses

Each refusal exits non-zero, says why, and records nothing.

- A duration over the operator's wait limit, `routing.watchdog.maxWaitSeconds`
  (default 3600 seconds).
- Text that is not a duration, such as `30` or `soon`.
- An empty condition, or one over 200 characters.
- A work item whose pointer is on a human-owned node. the-loop already waits for a person
  there. Use [`ask`](/cli/commands/ask) to ask a question.
- A work item that is not the session's own: a ref other than `THE_LOOP_WORK_ITEM` in a
  session the daemon spawned, or a ref with no live session in the registry.

## Notes

- It runs through the control-plane service when one answers, as
  [`ask`](/cli/commands/ask) does. A session the daemon spawned never runs it in-process.
- To wait on a person, use [`ask`](/cli/commands/ask). A declared wait pages nobody.
