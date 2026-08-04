# Commands

```bash
the-loop --help
the-loop --version
the-loop --config path/to/cli-config.yaml <command>   # must precede the subcommand
```

## Daemon commands

Long-running or machine-scoped. Their **own** settings come from the
[CLI config](/config/cli/) and from nowhere else — no repository configures the daemon
([decision-044](/decisions/decision-044)). When they act *on* a work item they still read
that item's own checkout, the same way the repo-scoped commands do.

| Command | What it does |
|---------|--------------|
| [`gh-webhook`](/cli/commands/gh-webhook) | HMAC-verified GitHub webhook receiver; routes each event to the session working that item. |
| [`poll`](/cli/commands/poll) | Pull-based ingress for hosts a webhook cannot reach. Same dispatch stack. |
| [`sessions`](/cli/commands/sessions) | The work-item ↔ session registry, execution control (`start`/`pause`/`resume`/`stop`), and `reset` — forget a work item's state so it starts over. |
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
| [`migrate-config`](/cli/commands/migrate-config) | Migrate a `cli-config.yaml` to the current schema version. Deterministic, idempotent, previewable. |

## Global flags

### `--config PATH` / `-c PATH`

The [CLI config](/config/cli/) to use. **Must precede the subcommand** —
`the-loop --config x.yaml poll start`, not `the-loop poll start --config x.yaml`. Same
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
| `2` | Could not run — bad arguments, missing work item, unreadable config |

## Adding one

Commands come from a registry, so a new one is three steps — see
[extending the CLI](/cli/extending). A registered command with no page here fails the
repository's test suite, which is why this table cannot quietly fall behind the code.
