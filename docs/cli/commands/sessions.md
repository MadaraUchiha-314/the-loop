# `sessions`

The work-item ↔ harness-session registry, the four execution-control commands, and the
reset that forgets a work item entirely.

```bash
# registry
the-loop sessions register --work-item github:OWNER/REPO#N --harness claude \
    --harness-session-id "$CLAUDE_SESSION_ID" [--cwd .] [--force]
the-loop sessions list   [--status active|paused|closed] [--format table|json]
the-loop sessions attach --work-item github:OWNER/REPO#N [--read-only]
the-loop sessions close  --work-item github:OWNER/REPO#N [--keep-tmux|--kill-tmux]
the-loop sessions reset  --work-item github:OWNER/REPO#N [--work-item …] [--dry-run]
the-loop sessions reset  --all [--dry-run]

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
`<state.root>/local/`, git-ignored). Writes are atomic, so concurrent sessions on one
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

A session registered by hand (`sessions register`) has no tmux session until its first
dispatched event spawns one; until then `attach` errors, telling you no tmux session is
recorded yet.

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

## `reset`

Forget everything this machine remembers about a work item, so it starts over on the code
you have just fixed. The command #137 asked for: after fixing a bug **in the-loop itself**
and releasing, an in-progress item is still holding a conversation the old CLI started, a
poll ledger saying every comment is handled, and a control record saying it is armed.

| Flag | Default | Meaning |
|------|---------|---------|
| `--work-item` | — | Which work item to reset. **Repeatable.** |
| `--all` | off | Every work item this machine holds state for. Mutually exclusive with `--work-item`. |
| `--dry-run` | off | Report what would go; change nothing. |

```console
$ the-loop sessions reset --work-item github:octo/repo#15
github:octo/repo#15: ended a live session
github:octo/repo#15: removed the workspace checkout — uncommitted work in it is gone
github:octo/repo#15: reset — removed session, control, poll
reset 1 work item
```

### What it removes

| | What goes | Why |
|---|---|---|
| the live session | ended through the normal [close path](#close) | no harness is left running against records that have gone |
| `<state.root>/local/<slug>.json` | **deleted**, not closed | a closed record still lists, and is still `attach`-able — that is the "still remembered" a reset ends |
| `portable/<slug>.json` `control` | cleared | the item is **disarmed**: it waits for an explicit start rather than resuming itself |
| `portable/<slug>.json` `poll` | cleared | the thread is first-sight again, so a fresh session re-reads it instead of finding everything already seen |
| the workspace checkout | per [`workspace.keepCheckoutOnClose`](/config/cli/routing-options#workspace-keepcheckoutonclose) | reset reuses the close path rather than inventing a second policy |

### What it does not

The event log is **appended to, never rewritten** — the reset itself lands in it as
`session.reset`, so "someone reset this" is a visible cause rather than an unexplained gap.
And nothing in your repository is touched: `docs/specs/<id>/graph-state.json`, the spec
artifacts and the phase label are checked in on the work item's branch, and the process
graph [re-derives](/capabilities/process-graph) the current node from the artifacts anyway.

::: warning Two things it will tell you about
A reset run while `gh-webhook` is up can be partly undone — the daemon holds poll state in
memory and may write it back. Stop it first for a clean slate.

And when [`requireStartCommand`](/config/cli/routing-options#control-requirestartcommand) is
`false`, clearing the poll section makes the item first-sight again, so the next poll cycle
may **re-spawn** it rather than wait for a start. The command warns in both cases and still
does the work — the judgement is yours.
:::

Selection is deliberate: a bare `reset` is a usage error rather than "reset everything", and
one bad ref in a list resets none of them. Nothing is posted to the ticket — there is no
`reset` keyword (a comment must not be able to delete local state), and posting
`stop-execution` would record intent the reset has just cleared
([decision-050](/decisions/decision-050)).

## Execution control

`start` / `pause` / `resume` / `stop` apply exactly what the corresponding
[comment keyword](/config/cli/routing-options#execution-control) applies, from the machine
running the-loop:

- **`start`** spawns through the same dispatcher the daemon uses — workspace checkout,
  harness trust, tmux hosting, announcement — or resumes a paused session, and prints
  the tmux target it spawned into.
- **`pause`** holds events; the session keeps its conversation.
- **`resume`** delivers events again.
- **`stop`** takes the normal close path.

| Flag | Default | Meaning |
|------|---------|---------|
| `--work-item` | required | Which work item to act on. |
| `--comment` / `--no-comment` | on | Post the equivalent keyword comment on the work item. |

Each invocation records the command in that work item's portable record
(`<state.root>/portable/<slug>.json`, `control` section) and posts
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

- [Routing options](/config/cli/routing-options) — registry location, tmux lifetime.
- [Concepts](/cli/concepts#work-items-and-sessions) — the invariant and how sessions end.
- [interactive sessions](/capabilities/interactive-sessions) — the capability doc.
