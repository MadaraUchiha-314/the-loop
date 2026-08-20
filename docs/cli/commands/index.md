# Commands

```bash
the-loop --help
the-loop --version
the-loop --config path/to/cli-config.yaml <command>   # must precede the subcommand
```

## The control plane

Since issue-161 every command below that touches the-loop's state runs **through the
control-plane service**, which is the single implementation of each capability. It is
started for you on first use, so nothing here needs setting up first.

| Command | What it does |
|---------|--------------|
| [`start`](/cli/commands/start) | Bring up every service the CLI config enables — the control-plane service (+ `/mcp`), the webhook receiver, the poller. |
| [`stop`](/cli/commands/stop) | Stop every running the-loop service, whatever the `enabled` flags say now. |
| [`status`](/cli/commands/status) | Per-service liveness and the poller's progress; exit 0 iff everything enabled is running. |
| [`restart`](/cli/commands/restart) | `stop` then `start`, optionally upgrading the CLI in between (`--with-upgrade`). Also `POST /api/v1/restart`. |

## Daemon commands

Long-running or machine-scoped. Their **own** settings come from the
[CLI config](/config/cli/) and from nowhere else — no repository configures the daemon
([decision-044](/decisions/decision-044)). When they act *on* a work item they still read
that item's own checkout, the same way the repo-scoped commands do.

| Command | What it does |
|---------|--------------|
| [`sessions`](/cli/commands/sessions) | The work-item ↔ session registry, execution control (`start`/`pause`/`resume`/`stop`), and `reset` — forget a work item's state so it starts over. |
| [`standing`](/cli/commands/standing) | The sessions the-loop keeps for itself — no work item, addressed by name: `list`, `start`, `stop`, `restart`, and `say` to talk to one. |
| [`ask`](/cli/commands/ask) | Post an agent's question on its work item — marker stamped centrally, wait recorded as `session.awaiting_input`. |
| [`channels`](/cli/commands/channels) | Operate the conversation channels (the Slack bot): `status`, one `poll` cycle, or the Socket Mode `listen`er. |
| [`events`](/cli/commands/events) | Query the structured event log — the answer to "why did nothing happen?". |

## Repo-scoped commands

Run once, inside a checkout. They read that project's
[harness config](/config/harness-config) and are no part of the daemon
([decision-032](/decisions/decision-032)) — they need no `cli-config.yaml` at all, which
is what lets [`check`](/cli/commands/check) run as a CI gate in a bare checkout.

| Command | What it does |
|---------|--------------|
| [`check`](/cli/commands/check) | Evaluate a work item's nodes against its checked-in artifacts. Pure: no network, no subprocess, no mutation — so CI runs the same code the runtime does. |
| [`graph`](/cli/commands/graph) | Inspect and drive the [process graph](/capabilities/process-graph): `show`, `status`, `advance`, `run`, `force`. |
| [`critic`](/cli/commands/critic) | Hand a review round to a **different** harness and read back what it said, as one JSON envelope. |
| [`scenarios`](/cli/commands/scenarios) | The table of Gherkin scenarios the integration tests cover. |
| [`instructions`](/cli/commands/instructions) | Which of the project's registered [custom instruction docs](/operating-model/reference/instructions) actually resolve — and `onMissing` as an exit code. |

## Maintenance

| Command | What it does |
|---------|--------------|
| [`install`](/cli/commands/install) | Install the-loop itself — the CLI and the Claude Code / Cursor plugin — at user or project scope. Plans, previews, and reports every step. |
| [`upgrade`](/cli/commands/upgrade) | The same plan, moving an installed CLI/plugin to the current version with the installer that owns it. |
| [`migrate-config`](/cli/commands/migrate-config) | Migrate a `cli-config.yaml` to the current schema version. Deterministic, idempotent, previewable. |

## Global flags

### `--config PATH` / `-c PATH`

The [CLI config](/config/cli/) to use. **Must precede the subcommand** —
`the-loop --config x.yaml start`, not `the-loop start --config x.yaml`. Same
priority as `$THE_LOOP_CLI_CONFIG`; see
[where the file is found](/config/cli/#where-the-file-is-found).

### `--version`

The installed package version, read from package metadata — so it always reports what you
actually have rather than a string someone forgot to bump.

## Exit codes

Consistent across commands:

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Ran, and the answer is negative — a failed round, an unmet gate, a stopped run |
| `2` | Could not run — bad arguments, missing work item, unreadable config, or no reachable [service](/cli/service) |

## Adding one

Commands come from a registry, so a new one is three steps — see
[extending the CLI](/cli/extending). A registered command with no page here fails the
repository's test suite, which is why this table cannot quietly fall behind the code.
