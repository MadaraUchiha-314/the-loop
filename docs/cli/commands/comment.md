# `comment`

Post the agent's comment on its work item. The harness uses it instead of `gh` for the
ticket's paper trail: spec-gate replies, the completion summary, the reviewer
briefing, decision records.

```bash
the-loop comment --work-item github:OWNER/REPO#N --body "The design is updated."
the-loop comment --work-item github:OWNER/REPO#N --body-file summary.md
some-tool | the-loop comment --work-item github:OWNER/REPO#N --body-file -
```

## What it does

1. **Posts the comment** on the work item. The issues endpoint serves PR conversations
   too, so a PR ref works. The loop-prevention marker and an event envelope are
   stamped **centrally**, so the agent does not have to remember them, and its own
   comment never resumes its own session
   ([issue-104](https://github.com/MadaraUchiha-314/the-loop/issues/104)).
2. **Mirrors it** to every [channel](/capabilities/channels) subscribed to
   `comment.agent` (the Slack room, say). The poller and the webhook receiver see the
   envelope when they read the comment back, and publish nothing, so the room gets
   it once.

It prints the comment's URL. To **ask** a human and wait for the answer, use
[`ask`](/cli/commands/ask) instead: it records the wait, and `comment` does not.

## Flags

| Flag | Default | Meaning |
|------|---------|---------|
| `--work-item` | required | The ref the comment goes to (`github:[HOST/]OWNER/REPO#N`). |
| `--body` | — | The comment (markdown). |
| `--body-file` | — | Read the comment from a file; `-` reads stdin. Exactly one of the two. |

## Where it runs, and whose token

Through the control-plane service when one is running, so the daemon's token posts
the comment and the session holds none. When no service answers, it runs
in-process on the token `integrations.github.api.tokenEnv` names (default
`GH_TOKEN`, then `GITHUB_TOKEN`), and says so on stderr. It never starts a service
for this ([decision-140](/decisions/decision-140)). The same holds for
[`ticket`](/cli/commands/ticket) and [`pr`](/cli/commands/pr).

## Exit codes

| Code | When |
|------|------|
| 0 | Posted. |
| 1 | GitHub refused it, or there is no token. The message names the status and GitHub's text, or the variables to set. |
| 2 | A malformed ref, an empty body, or an unreadable `--body-file`. Nothing is sent. |
