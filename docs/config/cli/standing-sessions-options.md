---
configBase: standingSessions
---

# Standing-session options

Options under `standingSessions` — the sessions the-loop keeps for **itself**
([issue-277](https://github.com/MadaraUchiha-314/the-loop/issues/277); see
[the capability](/capabilities/standing-sessions) and the
[`standing`](/cli/commands/standing) command). A standing session belongs to no work
item: no ticket, no spec chain, no completion. It exists for the work that sits *above*
the work items — watching the ones in flight, helping you recover one that is stuck — and
you talk to it on the control plane or in a Slack thread rather than on an issue.

```yaml
standingSessions:
  enabled: false
  sessions:
    - name: supervisor
      description: Watches the work items in flight and reports what is stuck.
      harness: claude            # omit = routing.defaultHarness
      harnessArgs: []            # omit = routing.harnessArgs.<harness>
      cwd: "~/dev/the-loop"      # omit = routing.spawnWorkdir
      autoStart: true
      prompt: |
        Every 30 minutes, run `the-loop status` and `the-loop sessions list`,
        and tell me about anything that has not moved.
      slack:
        enabled: true
        channel: ""              # empty = channels.slack.channel
```

::: warning This block is executable-adjacent config
An entry names **harness arguments** and a **working directory**, and the session runs
with your own credentials — the same posture
[`routing.harnessArgs`](/config/cli/routing-options#harnessargs) and the harness config's
`reviews.critics` already carry. Review an entry the way you review code, and never let
one arrive in your config from somewhere you would not merge a pull request from.
:::

## The block

### `enabled`

- **Type:** `boolean`
- **Default:** `false`

Whether [`the-loop start`](/cli/commands/start) brings the `autoStart` sessions up.
Default off on purpose: starting the-loop's daemons is not consent to spawn agent
sessions nobody asked for.

[`the-loop stop`](/cli/commands/stop) ignores it — a session disabled *after* it was
started must still be stoppable, the same rule the services follow.

## The `sessions` list

`standingSessions.sessions` is an array, defaulting to `[]`. One entry per standing
session. Names must be **unique**: a duplicate refuses the whole
block, naming both positions, rather than picking a winner. A block that cannot be parsed
is **refused** by every verb — including the reads, because a listing that answered "no
standing sessions" for a config with a typo in it would be a wrong answer that looks like a
fact. The one exception is [`the-loop standing stop`](/cli/commands/standing), which works
off the registry rather than the declaration, so whatever you started before the config
broke stays stoppable.

Each entry's own keys:

### `sessions[].name`

- **Type:** `string`, matching `^[a-z0-9][a-z0-9-]{0,39}$`
- **Default:** none — required

The session's identity everywhere: `loop-standing-<name>` in tmux, `<name>.json` in the
registry, `standing:<name>` as its Slack thread binding. Narrow because the value is
interpolated into a tmux session name and a file name — and it may not start with a
hyphen, which every CLI it is passed to would read as an option.

It cannot collide with a work item's `loop-<slug>`: a slug always ends in `-<number>` and
carries its provider, so reaching `loop-standing-…` would take a provider called
`standing`, and there is none.

### `sessions[].description`

- **Type:** `string`
- **Default:** `""`

What this session is for, in one line. Shown by
[`the-loop standing list`](/cli/commands/standing); never sent to the harness.

### `sessions[].harness`

- **Type:** `string` — `claude` | `cursor`
- **Default:** [`routing.defaultHarness`](/config/cli/routing-options#defaultharness)

Which harness hosts the session. Note that `cursor-agent` has no pre-assignable
conversation id, so it cannot host an interactive session — the same limitation
work-item sessions have, and a `cursor` entry fails at spawn with the adapter's own
message.

### `sessions[].harnessArgs`

- **Type:** `array` of `string`
- **Default:** [`routing.harnessArgs.<harness>`](/config/cli/routing-options#harnessargs)

Extra CLI arguments for this session's harness. **Omitting the key** inherits the
routing default; writing `[]` explicitly means *none*, which is how you give one session
a narrower surface than the rest.

Widening permissions here widens them for an unattended agent. the-loop never adds a
permission flag you did not write — the same rule
[`harnessTrust.acceptBypassPermissions`](/config/cli/routing-options#harnesstrustacceptbypasspermissions)
follows when it declines to record a disclaimer nobody asked for.

### `sessions[].cwd`

- **Type:** `string`
- **Default:** [`routing.spawnWorkdir`](/config/cli/routing-options#spawnworkdir)

The directory the session runs in. It **must exist**: a session is never spawned into a
directory that is not there, and one that names a missing path fails with the path
quoted while the others still start.

The directory is pre-trusted in your harness's own config before the spawn, per
[`routing.harnessTrust`](/config/cli/routing-options#harnesstrustenabled), so an
unattended session does not stop on a workspace-trust dialog.

### `sessions[].prompt`

- **Type:** `string`
- **Default:** `""`

The session's brief, inline. It is **appended to** the-loop's own directive — *you are a
standing session, you own no work item, do not answer a phase gate or post a control
keyword on any ticket* — and never substituted for it. That directive is deliberately not
configurable: a template key would exist only to let it be deleted.

Mutually exclusive with `promptFile`.

### `sessions[].promptFile`

- **Type:** `string`
- **Default:** `""`

The same brief, read from a file at start time (absolute, or relative to where the-loop
runs) — which is how a long brief lives in version control instead of in your config.
Same append rule as `prompt`; declaring **both** refuses the entry, because there is no
precedence between them. A file that cannot be read fails *that* session and no other.

### `sessions[].autoStart`

- **Type:** `boolean`
- **Default:** `true`

Whether [`the-loop start`](/cli/commands/start) brings this one up. `false` means it is
declared but started only on request (`the-loop standing start <name>`) — and its being
down never fails [`the-loop status`](/cli/commands/status), which counts only the sessions
`start` would have started.

### `sessions[].slack.enabled`

- **Type:** `boolean`
- **Default:** `false`

Announce this session in Slack when it starts, and bind the resulting thread to it, so an
authorized member's reply in that thread is pasted into its terminal. Requires
[`channels.slack.enabled`](/config/cli/channels-options#slackenabled).

Best-effort by contract: an unreachable workspace, a channel the bot is not in, or a
disabled channels block all leave the session **up** — it simply has no Slack thread, and
`standing.announce_failed` says so.

The bot reads only threads it is bound to. A standing session gets a thread of its own; it
does not get permission to read the channel.

### `sessions[].slack.channel`

- **Type:** `string`
- **Default:** `""` — meaning [`channels.slack.channel`](/config/cli/channels-options#slackchannel)

The channel id this session is announced in (`C…`). Everything else about the Slack
surface — the bot, the tokens, the verbosity, the read mode and the authorized-member
list — stays centrally declared under `channels.slack`, so a per-session channel is the
only thing that can differ. That is the "link to an existing config" half of the design:
one bot, many threads.
