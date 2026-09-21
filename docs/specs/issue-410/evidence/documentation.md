---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#410"
---

# Documentation: roll running sessions onto a refreshed environment (issue-410)

Updated in this PR:

| Page | What changed |
|---|---|
| [`docs/capabilities/interactive-sessions.md`](../../../capabilities/interactive-sessions.md) | Four new *Current behaviour* clauses (spawn carries the declared environment; `restart` relaunches in place resuming the conversation; the relaunch is verified and names what still differs; `status` carries the drift line) and a history row |
| [`docs/cli/commands/sessions.md`](../../../cli/commands/sessions.md) | New `## restart` section: the synopsis, the flag table, a worked console transcript, what it will **not** do, how it proves the relaunch, the argv-exposure warning, and the drift line |
| [`docs/cli/commands/status.md`](../../../cli/commands/status.md) | The `sessions` drift line: when it appears, why it exists, that it never moves the exit code, and the `sessionEnvironment` JSON |
| [`docs/config/cli/index.md`](../../../config/cli/index.md) | `env.file`'s "Read once, at start" bullet corrected — it was true of every process and is now only true of the process that reads it; spawned sessions get the file as read at spawn time, and running ones are rolled with `sessions restart` |

Capability docs **not** affected, and why:

- `cli.md` — the command index is generated from the registered commands; `sessions`
  already has its page, and `restart` is a subcommand of it.
- `channels.md` — the Slack `status` rendering gained the same one line from the shared
  `environment_line`; nothing about channels' own behaviour changed.
- `control-plane.md` / `sdk.md` — deliberately untouched: `restart` adds no HTTP route and
  no MCP tool (design § *Why this executes in-process*), so neither surface moved.
- `standing-sessions.md` — standing sessions gained the fresher spawn environment through
  the shared runner, which is the interactive-sessions behaviour that page already defers
  to.

`docs/cli/commands/restart.md` is a **different** command (`the-loop restart`, the service
lifecycle) and is untouched; the new subcommand is `the-loop sessions restart`.
