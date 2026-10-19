# `progress`

Tell the room where a long session is — and keep working. The non-blocking sibling of
[`ask`](/cli/commands/ask).

```bash
the-loop progress --work-item github:OWNER/REPO#N --text "Wiring the retry into the poller; tests next."
the-loop progress --work-item github:OWNER/REPO#N --text-file status.txt
some-tool | the-loop progress --work-item github:OWNER/REPO#N --text-file -
```

## What it does

Every other event the-loop publishes fires at a boundary — a gate, a block, a question,
the end — so a session that runs for hours is silent, and a phone cannot tell hard work
from a stuck loop from a dead poller ([issue-340](https://github.com/MadaraUchiha-314/the-loop/issues/340)).
`ask` is the only mid-flight signal, and it *blocks*. `progress` returns at once:

1. **Checks the work item opted in.** Only an item carrying the
   [`progress.label`](/config/cli/progress-options#label) (default `the-loop: progress`)
   emits anything, read from its tracker at the moment of the call — add the label to
   start the reports, remove it to stop them, no config edit and no restart. Any other
   item gets a one-line note and exit 0, so an agent can call the verb unconditionally.
2. **Applies the rate limit.** At most one report per work item per
   [`progress.minIntervalSeconds`](/config/cli/progress-options#minintervalseconds). A
   report sooner than that is not sent; the note says how many seconds remain, so the
   agent's next report is the newest one.
3. **Cuts it short.** One or two lines, at most
   [`progress.maxChars`](/config/cli/progress-options#maxchars) characters.
4. **Emits `session.progress`.** Every channel that subscribes to it hears it. In a
   Slack room it edits **one live line in place** rather than adding a message per
   report, so a long run shows where it is without burying the gates.

It is a signal, not a record: nothing is written on the ticket (the full detail already
goes there), and the event is **not** in any default subscription. Opt a channel in:

```yaml
channels:
  slack:
    subscribe: [session.awaiting_input, session.progress]
```

## Flags

| Flag | Default | Meaning |
|------|---------|---------|
| `--work-item` | required | The ref the report is about: `github:…`, or `jira:<site>/<KEY>-<n>`. |
| `--text` | — | One or two lines: what is happening now, and what is next. |
| `--text-file` | — | Read the report from a file; `-` reads stdin. Exactly one of the two. |

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Sent — or deliberately not sent (`disabled`, `not-opted-in`, `rate-limited`). The note says which. |
| 1 | The tracker refused the label read, so nothing was sent (a flaky tracker must not flood a room). |
| 2 | An empty report or a malformed ref; nothing was read or sent. |

## Notes

- Routed the way `ask` is: through the control-plane service when one answers — its
  process holds the credentials the label read needs and a spawned session holds none
  ([issue-482](https://github.com/MadaraUchiha-314/the-loop/issues/482)) — and
  in-process, with a note, when none does. Also `POST /api/v1/sessions/progress`.
- The rate limit reads the [event log](/config/cli/observability-options), so it cannot
  be enforced while `eventLog.enabled` is `false`.
- The text is the session's, so a Slack room draws it as inert text: broadcasts and
  direct mentions ping no one.
