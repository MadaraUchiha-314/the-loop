# Configuring the CLI

`cli-config.yaml` is read by the CLI's **daemon** commands —
[`gh-webhook`](/cli/commands/gh-webhook), [`poll`](/cli/commands/poll),
[`sessions`](/cli/commands/sessions) and [`events`](/cli/commands/events). It describes
*your machine*: which port the receiver binds, who is allowed to trigger it, how sessions
are hosted, where the log goes.

It is deliberately **not** tied to a repository. The daemon is expected to watch several
at once, so its settings live in one place rather than in N checkouts
([decision-032](/decisions/decision-032)). For the per-repository file — phases, reviews,
autonomy, tooling — see the [harness config](/config/harness-config).

A commented starting point ships at
[`skills/the-loop/templates/cli-config.yaml`](https://github.com/MadaraUchiha-314/the-loop/blob/main/skills/the-loop/templates/cli-config.yaml).
Validated against
[`.the-loop/cli-config.schema.json`](https://github.com/MadaraUchiha-314/the-loop/blob/main/.the-loop/cli-config.schema.json).

## Where the file is found

Resolved in priority order — the first that exists wins:

1. **`--config` / `-c`** — an explicit flag. It must come **before** the subcommand:

   ```bash
   the-loop --config path/to/cli-config.yaml gh-webhook start
   ```

2. **`$THE_LOOP_CLI_CONFIG`** — an explicit env var, same priority as the flag. Handy in
   containers and systemd units where a flag is less convenient.
3. **`./.the-loop/cli-config.yaml`** — repo-relative. Pick this to *track* your CLI config
   in a chosen repository (a "dev box" repo, checked in and versioned) rather than in your
   home directory; it is picked up automatically when you run from that checkout.
4. **`~/.the-loop/cli-config.yaml`** — the always-available fallback, tied to no repo.

::: danger Two settings have no fallback
`webhooks.ghWebhook.routing.authorizedUsers` (who may trigger the daemon) and a poll
source's `repos` (what it watches) are **CLI-config only**. They do **not** fall back to
any repository's harness config. Left unset, the daemon fails closed: it ignores every
human-authored event, and polls nothing.
:::

## Versioning and migration

### `version`

- **Type:** `string`
- **Default:** none — unset is accepted
- **Current:** `0.2.0`

Schema version of this file. The CLI **refuses to start** against a config that declares
a version older than the one it needs, naming the key, its replacement and the exact
command to run. A removed key is never silently ignored: ignoring a value you deliberately
set would change your behaviour without telling you.

The gate is narrow on purpose — it refuses exactly two things:

1. a **removed key is still present** (today: `ghBinary`, retired in favour of
   [`integrations.github.cli.binary`](/config/cli/integrations-options#github-cli-binary));
2. the config **declares** a version older than the current one — it says it is stale, so
   it is believed.

An **unset** `version` with no removed keys is *not* refused. There is nothing to move and
nothing to lose — most likely a minimal hand-written config — and a gate that stops a
daemon over a missing bookkeeping key is a gate operators learn to route around.

Migrate with [`the-loop migrate-config`](/cli/commands/migrate-config), or let
`/the-loop:upgrade-the-loop` run it for you. The migration is a deterministic key move:
idempotent, previewable with `--dry-run`, and it keeps a `.bak` of the file it replaced.

## Generated state

### `state.root`

- **Type:** `string`
- **Default:** `.the-loop`

Root directory for everything the CLI **generates**. One value moves them all, because
every generated path *defaults* from it:

| What | Default |
|------|---------|
| session registry | `<root>/sessions/` |
| control records | `<root>/sessions/control/` |
| poll state | `<root>/sessions/poll-state.json` |
| event log | `<root>/logs/events.jsonl` |
| receiver pidfile | `<root>/gh-webhook.pid` |

A path you set **explicitly** —
[`routing.registryDir`](/config/cli/routing-options#registrydir),
[`polling.stateFile`](/config/cli/polling-options#statefile),
[`eventLog.path`](/config/cli/observability-options#eventlog-path),
[`webhooks.ghWebhook.pidfile`](/config/cli/webhook-options#pidfile) — is used verbatim.
The root only fills in what you left out, so an existing config behaves identically.

With the default root only the poll state moves (it was `.the-loop/poll-state.json`). If
that legacy file still exists and the new one does not, the poller keeps using it and
warns once — adopting an empty state file would make every watched thread first-sight
again and re-forward its entire comment history.

All of it is git-ignored runtime state.

::: warning `~` is not expanded here
`state.root` is used as given. `root: ~/.the-loop` creates a directory literally named
`~` in the process's working directory — write an absolute path, or leave the relative
default. (This differs from
[`routing.workspace.root`](/config/cli/routing-options#workspace-root), which **does**
expand `~`.)
:::

## A minimal working config

```yaml
version: "0.2.0"

state:
  root: .the-loop

webhooks:
  ghWebhook:
    host: 127.0.0.1
    port: 8787
    routing:
      enabled: true
      authorizedUsers: ["your-github-login"]   # REQUIRED — empty fails closed
      spawnOnUnmatched: labeled
      runner: tmux
```

Everything else takes its default. Build up from here with the option pages below.

## Options by area

| Page | Block |
|------|-------|
| [Webhook options](/config/cli/webhook-options) | `webhooks.ghWebhook` — bind address, path, HMAC secret, event filter |
| [Routing options](/config/cli/routing-options) | `webhooks.ghWebhook.routing` — who may trigger, what spawns, how sessions are hosted |
| [Polling options](/config/cli/polling-options) | `polling` — the pull-based ingress and its sources |
| [Integrations options](/config/cli/integrations-options) | `integrations` — how the-loop's own calls reach GitHub, Slack and Jira |
| [Observability options](/config/cli/observability-options) | `eventLog`, `collaborators`, `notifications` |

Every option on those pages is checked against the schema in both directions by a test in
the repository — a documented key the schema does not define fails the build, and so does
a schema key nobody documented.
