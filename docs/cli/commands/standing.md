# `standing`

The sessions the-loop keeps for **itself** — declared in the CLI config, brought up by
[`the-loop start`](/cli/commands/start), and addressed by **name** rather than by work
item.

```bash
the-loop standing list [--format text|json]
the-loop standing create NAME [--harness H] [--cwd DIR] [--prompt TEXT|--prompt-file F]
                              [--description D] [--harness-arg ARG]... [--slack]
                              [--slack-channel C] [--no-auto-start] [--no-start]
the-loop standing delete NAME
the-loop standing start [NAME]      # omit NAME for every declared or created session
the-loop standing stop  [NAME]      # omit NAME for every recorded session
the-loop standing restart NAME
the-loop standing say NAME --text "…" [--actor WHO]
```

## What a standing session is

Everything else the-loop spawns belongs to a ticket: the tmux session is named after the
work item, events arrive from GitHub, and every question the agent asks goes back to the
issue it came from. A **standing session** is the other kind — it owns no work item, so it
has no ticket to be armed on, no phase to advance and no completion. It is what
[issue-277](https://github.com/MadaraUchiha-314/the-loop/issues/277) asked for: somewhere
for the work that sits *above* the work items, like watching the ones in flight and
helping you recover one that is stuck.

Because there is no ticket, **GitHub is not its surface**. You talk to it here, over the
control plane, or in a Slack thread of its own.

| | work-item session | standing session |
|---|---|---|
| Addressed by | `github:OWNER/REPO#N` | a name |
| Started by | an authorized `the-loop start` on the ticket | `the-loop start`, or `standing start` |
| tmux session | `loop-<work-item-slug>` | `loop-standing-<name>` |
| Record | `<state.root>/local/<slug>.json` | `<state.root>/local/standing/<name>.json` |
| Defined by | the ticket | a config entry, or `standing create` |
| Answers arrive from | ticket comments, routed by the daemon | `standing say`, or its Slack thread |
| Ends when | the work item is delivered | you stop it |

A session gets its definition one of two ways, and the verbs cannot tell them apart:

- **Declared** in [`standingSessions.sessions`](/config/cli/standing-sessions-options) —
  the durable kind, brought up by `the-loop start`. The block is **off by default**, and
  an entry names harness arguments and a working directory, so review one like code.
- **Created** with `standing create` — the same definition, written straight to the
  registry instead of the config. This is how you spin one up without editing a file and
  restarting ([decision-100](/decisions/decision-100)).

## `create`

```bash
the-loop standing create triage --cwd ~/dev/app \
    --prompt "Watch the work items in flight and tell me what is stuck."
```

Writes the whole definition — harness, arguments, working directory, brief, Slack binding
— into `<state.root>/local/standing/<name>.json`, then starts it. `--no-start` records it
without running anything; `--no-auto-start` keeps [`the-loop
start`](/cli/commands/start) from bringing it back.

It refuses a name that is **already declared or already recorded**: a name is one session,
and adopting an existing one would let a create take over a running agent. Every refusal a
declared start applies applies here too — the name shape, a `cwd` that must exist, the
live-occupant refusal — because the start half is the same code. A create whose start
fails removes the record it wrote, so the name stays free for your retry.

## `delete`

```bash
the-loop standing delete triage
```

Stops the session — the same graceful termination `stop` performs — and then **removes its
record**, so nothing comes back. That is the whole difference from `stop`, which keeps the
record precisely so the next start resumes the same conversation.

It refuses a **declared** session, naming the config key: `the-loop start` would recreate
its record on the next boot, so a delete that appeared to work would be lying. Remove the
entry from the config, or `stop` it.

## `list`

Every session that is **declared** or **recorded**, merged by name. Both halves are shown
because both are real: a declared one is what `start` will bring up, and a recorded one
that is no longer declared is a live process you still have to stop. `Live` is tmux's
answer *now*, not the record's claim.

```console
$ the-loop standing list
Name        Harness  Tmux                      Declared  Status   Live  Slack
supervisor  claude   loop-standing-supervisor  yes       running  yes   1712698400.001
triage      claude   loop-standing-triage      yes       stopped  no    -
```

`--format json` returns the same rows for scripting, and is what `GET
/api/v1/standing-sessions` serves.

## `start` / `stop` / `restart`

Idempotent in both directions, like the service verbs:

- A session whose pane is **alive** is reported `already-running` and is not touched.
  the-loop never spawns over a live pane.
- A session with a recorded conversation id and no live tmux session is **resumed**
  (`claude --resume <id>`), so `the-loop restart` is not amnesia for a supervisor. A
  resume that does not survive its liveness probe falls back to a fresh conversation and
  says so (`standing.resume_failed`).
- `stop` ends the harness **gracefully first** (SIGTERM, then SIGKILL after
  [`routing.tmux.harnessKillGraceSeconds`](/config/cli/routing-options#tmuxharnesskillgraceseconds))
  and only then kills the tmux session — the order matters, because Claude Code flushes
  its conversation on exit and a conversation that was not flushed cannot be resumed.
- `stop` **keeps the record**, with `status: stopped` and the conversation id intact.
- A **live** tmux session holding a standing name that the-loop has **no record of** is
  refused loudly, never spawned over — and `stop` will not signal it either. Inspect it
  with `tmux attach -r -t loop-standing-<name>` and `tmux kill-session` it yourself if you
  want it gone; the-loop releases what the-loop started. (A **dead** retained pane is a
  different thing — nothing is running in it, so a start clears it and spawns.)

Omitting the name means *every declared or created session that auto-starts* for `start`,
and *every recorded one* for `stop` — which is what makes a session you disabled after
starting it still stoppable, and what keeps a declared-but-never-started entry out of
`stop`'s way. `restart` needs a name.

The `start` side counts created sessions too, and deliberately: `stop` takes down every
**recorded** session, so without the symmetry [`the-loop restart`](/cli/commands/restart)
would destroy exactly the sessions `create` made while dutifully stopping them first.

`stop` is also the one verb that survives a config it cannot parse: it works off the
registry, so a typo you introduce after starting a session does not strand it.

## `say`

The point of the whole command. It pastes your message into the session's terminal and
submits it:

```bash
the-loop standing say supervisor --text "what has not moved since this morning?"
```

Fail-closed, exactly like [`sessions reply`](/cli/commands/sessions): a message answers a
session that exists, so it never *creates* one. An unknown name, a stopped session or a
dead pane is an error naming `the-loop standing start <name>`.

Nothing is posted to any ticket — there is none — so `standing.said` in the
[event log](/cli/commands/events) is the delivery's record. `--actor` is recorded on that
event for the audit trail and is never trusted as authentication.

## Talking to one from Slack

With [`channels.slack`](/config/cli/channels-options) enabled and the entry's
`slack.enabled` set, the-loop posts an announcement into the session's channel when it
starts and **binds that thread to the session**. An authorized member's reply in the
thread is pasted into its terminal — the same pipeline that carries a work-item answer,
minus the mirror step, because there is no ticket to mirror onto
(`channel.mirror_skipped` records that).

The bot still reads **only threads it is bound to**: a standing session gets a thread of
its own, not permission to read the channel.

## Attaching

There is no `standing attach`: `tmux attach -t loop-standing-<name>` is the whole of it,
and `tmux attach -r -t …` observes without being able to type. The
[web terminal](/config/cli/routing-options#webterminalenabled) reaches these sessions like
any other.

## See also

- [standing-sessions options](/config/cli/standing-sessions-options) — the config block
- [standing sessions](/capabilities/standing-sessions) — the capability doc
- [`start`](/cli/commands/start) / [`stop`](/cli/commands/stop) /
  [`status`](/cli/commands/status) — where they are brought up and reported
