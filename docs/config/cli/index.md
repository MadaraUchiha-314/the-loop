# Configuring the CLI

`cli-config.yaml` is read by the CLI's **daemon** commands —
[`start`](/cli/commands/start), [the receiver](/cli/receiver),
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
[`cli-config.schema.json`](https://github.com/MadaraUchiha-314/the-loop/blob/main/.the-loop/cli-config.schema.json),
which ships with the plugin — `/the-loop:init` scaffolds the config alone and never a copy
of the schema beside it.

## Editing it from the dashboard

Since issue-222 this file is not only hand-editable. Run
[`the-loop start`](/cli/commands/start), open the
[dashboard's](https://madarauchiha-314.github.io/the-loop/ui/) **Settings** tab, and the
whole config is there — one section per top-level block, rendered from the schema, with
each key's description beside it.

Two things are worth knowing before you use it:

- **Your comments survive.** A save rewrites the values you changed *in the file text*
  rather than re-serializing the document, so the prose explaining each knob stays where
  you wrote it, along with key order and formatting.
- **A save is live immediately** — the poller and the receiver reload from the file, and
  so does the service itself. The exceptions are the values read once at boot
  (`service.host`, `service.port`, `service.exposed`, `service.cors.*`); the dashboard
  names them in its confirmation when you change one.

An invalid change is refused with the offending key named, and nothing is written. The
route has the same authority as the rest of the control plane — see
[service options](/config/cli/service-options) for the network posture, which this does
not change.

## Where the file is found

Resolved in priority order — the first that exists wins:

1. **`--config` / `-c`** — an explicit flag. It must come **before** the subcommand:

   ```bash
   the-loop --config path/to/cli-config.yaml start
   ```

2. **`$THE_LOOP_CLI_CONFIG`** — an explicit env var, same priority as the flag. Handy in
   containers and systemd units where a flag is less convenient.
3. **`./.the-loop/cli-config.yaml`** — repo-relative. Pick this to *track* your CLI config
   in a chosen repository (a "dev box" repo, checked in and versioned) rather than in your
   home directory; it is picked up automatically when you run from that checkout.
4. **`~/.the-loop/cli-config.yaml`** — the always-available fallback, tied to no repo.

::: danger Two settings have no fallback
`routing.authorizedUsers` (who may trigger the daemon) and a poll
source's `repos` (what it watches) are **CLI-config only**. They do **not** fall back to
any repository's harness config. Left unset, the daemon fails closed: it ignores every
human-authored event, and polls nothing.
:::

## Versioning and migration

### `version`

- **Type:** `string`
- **Default:** none — unset is accepted
- **Current:** `0.4.0`

Schema version of this file. The CLI **refuses to start** against a config that declares
a version older than the one it needs, naming the key, its replacement and the exact
command to run. A removed key is never silently ignored: ignoring a value you deliberately
set would change your behaviour without telling you.

The gate is narrow on purpose — it refuses exactly two things:

1. a **removed key is still present** — today `ghBinary`, retired in favour of
   [`integrations.github.cli.binary`](/config/cli/integrations-options#github-cli-binary);
   `polling.stateFile`, retired in issue-128 because the poller's ledger became one
   record per work item under `state.root` (below) and a file path has nothing left to
   point at; and `webhooks.ghWebhook.routing`, promoted in issue-142 to the top-level
   [`routing`](/config/cli/routing-options) because the poller dispatches on that same
   block and a key named `webhooks` said otherwise;
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

| What | Default | Travels? |
|------|---------|----------|
| work-item records (control + poll state) | `<root>/portable/` | **portable** |
| the index of those records (derived) | `<root>/portable/index.json` | **portable** |
| session registry | `<root>/local/` | local |
| event log | `<root>/logs/events.jsonl` | local |
| receiver pidfile | `<root>/gh-webhook.pid` | local |

The tree is organised by **portability**, not by which component writes it
([decision-046](/decisions/decision-046)): `portable/` holds one record per work item —
what an authorized user armed, and which comments have already been seen — and is the half
worth tracking in git. Everything else is a handle to this machine.

Two of them can still be set **explicitly** —
[`routing.registryDir`](/config/cli/routing-options#registrydir),
[`eventLog.path`](/config/cli/observability-options#eventlog-path) — plus
[`webhooks.ghWebhook.pidfile`](/config/cli/webhook-options#pidfile); those are used
verbatim. `portable/` follows the root, so "where is the half I track?" has one answer.

[State on disk](/cli/state) documents every file, what is inside it, what is lost if you
delete it, and the three-line `.gitignore` block. Upgrading from the pre-issue-128 layout
(`<root>/sessions/…`) loses nothing: the old locations are read once per work item and
written forward.

::: warning `~` is not expanded here
`state.root` is used as given. `root: ~/.the-loop` creates a directory literally named
`~` in the process's working directory — write an absolute path, or leave the relative
default. (This differs from
[`routing.workspace.root`](/config/cli/routing-options#workspace-root), which **does**
expand `~`.)
:::

## A minimal working config

```yaml
version: "0.4.0"

state:
  root: .the-loop

webhooks:
  ghWebhook:
    host: 127.0.0.1
    port: 8787

routing:                                     # shared by BOTH ingresses
  enabled: true
  authorizedUsers: ["your-github-login"]     # REQUIRED — empty fails closed
  spawnOnUnmatched: labeled
```

Everything else takes its default. Build up from here with the option pages below.

## Options by area

| Page | Block |
|------|-------|
| [Webhook options](/config/cli/webhook-options) | `webhooks.ghWebhook` — bind address, path, HMAC secret, event filter |
| [Routing options](/config/cli/routing-options) | `routing` — who may trigger, what spawns, how sessions are hosted |
| [Polling options](/config/cli/polling-options) | `polling` — the pull-based ingress and its sources |
| [Integrations options](/config/cli/integrations-options) | `integrations` — how the-loop's own calls reach GitHub, Slack and Jira |
| [Service options](/config/cli/service-options) | `service` — the control-plane API's bind, auto-start and cross-origin allowlist |
| [Observability options](/config/cli/observability-options) | `eventLog`, `collaborators`, `notifications` |

Every option on those pages is checked against the schema in both directions by a test in
the repository — a documented key the schema does not define fails the build, and so does
a schema key nobody documented.
