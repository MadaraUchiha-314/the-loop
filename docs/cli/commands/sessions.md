# `sessions`

The work-item ↔ harness-session registry, and the four execution-control commands.

```bash
# registry
the-loop sessions register --work-item github:OWNER/REPO#N --harness claude \
    --harness-session-id "$CLAUDE_SESSION_ID" [--cwd .] [--force]
the-loop sessions list   [--status active|paused|closed] [--format table|json]
the-loop sessions attach --work-item github:OWNER/REPO#N [--read-only]
the-loop sessions close  --work-item github:OWNER/REPO#N [--keep-tmux|--kill-tmux]

# execution control — the same four commands as the comment keywords
the-loop sessions start  --work-item github:OWNER/REPO#N [--no-comment]
the-loop sessions pause  --work-item github:OWNER/REPO#N [--no-comment]
the-loop sessions resume --work-item github:OWNER/REPO#N [--no-comment]
the-loop sessions stop   --work-item github:OWNER/REPO#N [--no-comment]
```

Every subcommand accepts `--registry-dir`, defaulting to
[`routing.registryDir`](/config/cli/routing-options#registrydir).

## The registry

One human-inspectable JSON file per session under `<registryDir>` (default
`<state.root>/sessions/`, git-ignored). Writes are atomic, so concurrent sessions on one
machine are safe.

The invariant is **one work item ↔ one active session**. `--force` replaces a stale
registration.

Claude Code sessions register with `$CLAUDE_SESSION_ID`. Cursor sessions register with the
chat id they were launched with — non-interactive `cursor-agent ls` is unreliable for id
discovery, so the id is captured at registration time.

::: tip A missing harness binary only warns
`register` succeeds even when the harness CLI is not on `PATH`, telling you events cannot be
dispatched until it is installed. Registration is bookkeeping; dispatch is what needs the
binary.
:::

## `register`

| Flag | Required | Meaning |
|------|----------|---------|
| `--work-item` | yes | Work-item ref, e.g. `github:OWNER/REPO#15`. |
| `--harness` | yes | `claude` or `cursor`. |
| `--harness-session-id` | yes | Claude session id, or Cursor chat id. |
| `--cwd` | no (`.`) | Directory the session runs in — resume is scoped to it. |
| `--force` | no | Replace an existing active registration for this work item. |

## `list`

| Flag | Default | Meaning |
|------|---------|---------|
| `--status` | all | `active`, `paused` or `closed`. |
| `--format` | `table` | `table` or `json`. |

Shows each session's status — `paused` included — and its last control command. Retained
tmux sessions accumulate after their work items close; `--status closed` is how you find
them.

## `attach`

| Flag | Default | Meaning |
|------|---------|---------|
| `--work-item` | required | Which session to attach to. |
| `--read-only` | off | Observe without a keyboard (`tmux attach -r`). |

Works after the work item is closed too — and is then **always** read-only, because a
finished session takes no input. Equivalent to `tmux attach -t loop-<slug>`.

## `close`

| Flag | Default | Meaning |
|------|---------|---------|
| `--work-item` | required | Which session to close. |
| `--keep-tmux` / `--kill-tmux` | [`routing.tmux.keepSessionOnClose`](/config/cli/routing-options#tmux-keepsessiononclose) | Whether the tmux session survives. |

Mutually exclusive. `--keep-tmux` keeps the transcript readable; the harness inside it is
still ended unless
[`routing.tmux.killHarnessOnClose`](/config/cli/routing-options#tmux-killharnessonclose) is
`false`. `--kill-tmux` ends it for good.

### Sessions usually close themselves

When the work item **ends** — the issue closed, or, when the PR *is* the work item, that PR
merged or closed — the session is auto-closed. No manual `close` needed.

A PR merely *linked* to the work item closing leaves the session running: one item is often
delivered by several PRs, so only the item's own close ends it. Both ingress paths do it —
the receiver on the `closed` event of the registered item, and the poller by noticing the
item has left the open listing and confirming upstream that it really ended.

A tmux-hosted session is **kept** so you can read back what happened, but the harness inside
it is **ended** so nothing can be typed into finished work.

## Execution control

`start` / `pause` / `resume` / `stop` apply exactly what the corresponding
[comment keyword](/config/cli/routing-options#execution-control) applies, from the machine
running the-loop:

- **`start`** spawns through the same dispatcher the daemon uses — workspace checkout,
  harness trust, runner, announcement — or resumes a paused session.
- **`pause`** holds events; the session keeps its conversation.
- **`resume`** delivers events again.
- **`stop`** takes the normal close path.

| Flag | Default | Meaning |
|------|---------|---------|
| `--work-item` | required | Which work item to act on. |
| `--comment` / `--no-comment` | on | Post the equivalent keyword comment on the work item. |

Each invocation records the command beside the session (`<registryDir>/control/`) and posts
the **same keyword** back to the work item, so the ticket stays the full record of who asked
for what. That comment carries the loop-prevention marker, so the daemon never reads its own
action back and re-applies it.

Posting is best-effort: `--no-comment` skips it, and a missing or failing `gh` only warns —
it never undoes the local action.

## Label-gated auto-execution

With [`spawnOnUnmatched: labeled`](/config/cli/routing-options#spawnonunmatched): give an
issue or PR the configurable
[`autoExecuteLabel`](/config/cli/routing-options#autoexecutelabel), have an authorized user
comment `the-loop start` (or run `sessions start`), and the ingress spawns a
session and starts `/the-loop:work-on` on it — then routes that item's later activity
(comments, reviews, CI, and **every** PR linked to it) to the same session, and auto-closes
when the item itself closes. Label presence is read straight from the webhook payload, with
no extra API call. A new issue *without* the label is received and ignored.

### PRs are work items too

The label applies to **PRs directly**: a labelled PR with no linked issue is routed as its
own work item, `github:OWNER/REPO#<pr-number>`.

That makes PRs monitorable even when the ticketing system is **Jira or another provider** —
the ticket cannot be routed, but the PR delivering it can. `/the-loop:work-on <jira-id>`
adds the label to the PR it opens and registers its session against the PR's ref
automatically, so PR activity resumes the session and **that** PR's merge or close ends it,
exactly like a GitHub-ticketed item.

## See also

- [Routing options](/config/cli/routing-options) — registry location, runner, tmux lifetime.
- [Concepts](/cli/concepts#work-items-and-sessions) — the invariant and how sessions end.
- [interactive sessions](/capabilities/interactive-sessions) — the capability doc.
