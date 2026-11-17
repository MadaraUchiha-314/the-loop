# Configuring the CLI

`cli-config.yaml` is read by the CLI's **daemon** commands —
[`start`](/cli/commands/start), [the receiver](/cli/receiver),
[`sessions`](/cli/commands/sessions) and [`events`](/cli/commands/events). It describes
*your machine*: which port the receiver binds, who is allowed to trigger it, how sessions
are hosted, where the log goes.

It is deliberately **not** tied to a repository. The daemon is expected to watch several
at once, so its settings live in one place rather than in N checkouts
([decision-032](/decisions/decision-032)), and it is the **only** file the CLI reads:
a repository's [harness config](/config/harness-config) is the agent's
([decision-123](/decisions/decision-123)).

A commented starting point ships at
[`skills/the-loop/templates/cli-config.yaml`](https://github.com/MadaraUchiha-314/the-loop/blob/main/skills/the-loop/templates/cli-config.yaml).
Validated against
[`cli-config.schema.json`](https://github.com/MadaraUchiha-314/the-loop/blob/main/.the-loop/cli-config.schema.json),
which ships with the plugin — `/the-loop:init-cli` scaffolds the config alone and never a copy
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
`routing.authorizedUsers` (who may trigger the daemon) and the top-level
[`repositories`](/config/cli/repositories-options) (which repositories it works with) are
**CLI-config only**. They do **not** fall back to any repository's harness config. Left
unset, `authorizedUsers` fails closed — every human-authored event is ignored — and
`repositories` leaves the poller with nothing to poll and the receiver bounded by nothing,
which it says at start.
:::

## Versioning and migration

### `version`

- **Type:** `string`
- **Default:** none — unset is accepted
- **Current:** `0.10.0`

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
   block and a key named `webhooks` said otherwise; and `polling.sources[].repos`,
   promoted in issue-348 to the top-level
   [`repositories`](/config/cli/repositories-options) because the repository list bounds
   every ingress — the webhook receiver, which never read it, included; and
   `routing.autoExecuteLabel` with `polling.sources[].label`, wrapped in issue-381 into
   the lists [`autoExecuteLabels`](/config/cli/routing-options#autoexecutelabels) and
   `labels`, every entry of which an item must carry;
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
- **Default:** `.the-loop`, resolved **beside the config file** — see below

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

### Where a relative root lands

A **relative** `state.root` — the default `.the-loop` included — is resolved against the
directory your config's `.the-loop/` sits in, **never** against the process's working
directory:

| Your config file | `state.root` | Resolves to |
|---|---|---|
| `/repo/.the-loop/cli-config.yaml` | *unset* | `/repo/.the-loop` |
| `/repo/.the-loop/cli-config.yaml` | `.the-loop` | `/repo/.the-loop` |
| `/repo/.the-loop/cli-config.yaml` | `var/state` | `/repo/var/state` |
| `~/.the-loop/cli-config.yaml` | *unset* | `~/.the-loop` |
| *anything* | `/srv/the-loop` | `/srv/the-loop` |
| *anything* | `~/loop-state` | `~/loop-state`, expanded |

This is the rule [`env.file`](/config/cli/#env-file) follows, one directory out — and it is what makes
the daemon and the CLI read the *same* files. Before
[decision-119](/decisions/decision-119) the root was relative to whoever asked, so a
daemon started in one directory wrote a heartbeat, a session registry and an event log
that `the-loop status`, run from another, never looked at
([issue-339](https://github.com/MadaraUchiha-314/the-loop/issues/339)): it read a second,
stale copy and reported a live poller as dead. `the-loop status` now prints the config and
the root it is answering about, and names a second root when it finds one.

::: tip `~` **is** expanded
`root: ~/loop-state` is your home directory, as
[`routing.workspace.root`](/config/cli/routing-options#workspace-root) has always been.
Until 13.12.0 it created a directory literally *named* `~`; if you have one, it is that
bug's, and moving its contents to the expanded path is safe while nothing is running.
:::

## Environment file

### `env.file`

- **Type:** `string`
- **Default:** `""` (nothing loaded)

Path of a **dotenv-format** file the-loop loads into its own environment when a process
starts — before any command, daemon or service reads a variable. Every credential the-loop
uses is *named* in this file and *read* from the environment
([`secretEnv`](/config/cli/webhook-options#secretenv),
[`botTokenEnv`](/config/cli/channels-options#slack-bottokenenv),
[`tokenEnv`](/config/cli/integrations-options)); `env.file` names where the values live,
so you need not `export` them by hand before every `the-loop start`:

```yaml
env:
  file: .env          # beside this config file; ~ is expanded
```

```bash
# ~/.the-loop/.env — keep it out of git, chmod 600
THE_LOOP_GH_WEBHOOK_SECRET='the same secret you gave GitHub'
export THE_LOOP_SLACK_BOT_TOKEN="xoxb-…"
```

What the loader does, and does not do ([decision-108](/decisions/decision-108)):

- **A relative path resolves against this config file's directory**, not the working
  directory, and `~` is expanded — so `~/.the-loop/cli-config.yaml` naming `.env` finds
  `~/.the-loop/.env` from anywhere. (This differs from `state.root`, above.)
- **The environment wins.** A variable already set — exported in the shell, or by
  systemd — is never overwritten; the file fills the gaps.
- **Every entry point loads it**, first: the `the-loop` CLI, `python -m
  the_loop.daemon_entry`, `python -m the_loop.api.serve`. The daemons and the service
  `the-loop start` spawns inherit the CLI's environment *and* load the file again on
  their own start, so a systemd unit that runs the daemon directly sees the same
  variables.
- **Read once, at start — for the process that reads it.** A change to the file needs a
  restart of that process; the daemons' hot reload of `cli-config.yaml` does not re-read
  it, so a reload can never change the credentials a running process holds.
- **Harness sessions never see it**
  ([issue-482](https://github.com/MadaraUchiha-314/the-loop/issues/482)). The file is the
  daemon's environment. A session the daemon spawns is given only `THE_LOOP_INSTANCE`,
  `THE_LOOP_WORK_ITEM` and `THE_LOOP_CLI_CONFIG`, plus the non-secret names you list in
  [`env.sessionPassthrough`](/config/cli/#env-sessionpassthrough); every other name the file
  declares, and every credential name, is removed from its environment. The session
  reaches GitHub and Jira through the service, which holds the token.
- **A passthrough value is re-read per spawn**
  ([issue-410](https://github.com/MadaraUchiha-314/the-loop/issues/410)), so a session
  started after you change it is not born on the old value. A session **already
  running** is frozen, by definition: roll them with
  [`the-loop sessions restart --all`](/cli/commands/sessions#restart), which relaunches
  each one in place and verifies that it landed.
  [`the-loop status`](/cli/commands/status) says when any of them have drifted, or still
  hold a credential.
- **The grammar** is the usual one: `NAME=value` per line, `#` comments, an optional
  leading `export`, double quotes with `\n \t \r \\ \"` unescaped, single quotes
  literal, an unquoted value trimmed and cut at a trailing comment (a space, then `#`). There is **no
  interpolation** (`${OTHER}` is four characters) and no multi-line value.
- **Failures are warnings, never a stop.** A missing or unreadable file, or a malformed
  line, is logged — the resolved path, the line *number*, the error class, and never a
  value — and the process continues; each credential-dependent feature then keeps its
  own fail-closed behaviour (an unsigned receiver warns, a channel without a token is
  refused). A file readable by group or others is warned about and still loaded.

::: warning The config names a path, never a value
`cli-config.yaml` may be tracked in git; the env file must not be. Nothing the-loop writes
— state, event log, warnings — ever carries a loaded value.
:::

### `env.sessionPassthrough`

- **Type:** `string[]` (variable names)
- **Default:** `[]` (a session is given nothing from the environment)

The **non-secret** variables a spawned agent session is given — a proxy, a locale
([issue-482](https://github.com/MadaraUchiha-314/the-loop/issues/482)). the-loop never
sends a secret to a session, so by default it gets nothing but its own three identifiers.

```yaml
env:
  file: .env
  sessionPassthrough: [HTTPS_PROXY, NO_PROXY]
```

- A listed name takes its value from `env.file` when the file declares it (re-read per
  spawn), else from the daemon's own environment. A name in neither is skipped.
- **A credential name is refused**, with a warning naming the variable: any name a
  `*tokenEnv` or `*secretEnv` key holds anywhere in this config, and the defaults
  (`GH_TOKEN`, `GITHUB_TOKEN`, `THE_LOOP_GH_WEBHOOK_SECRET`,
  `THE_LOOP_SLACK_BOT_TOKEN`, `THE_LOOP_SLACK_APP_TOKEN`), plus every `name` and `from`
  listed in [`env.sessionCredentials`](/config/cli/#env-sessioncredentials).
- Every other name `env.file` declares, and every credential name, is **removed** from the
  session's environment — even when the tmux server holds it, because the daemon that
  started the server loaded the file.
- A listed value reaches the session through `tmux -e`, so it is visible in `ps`. That is
  why only non-secret names belong here. A credential a session needs goes in
  [`env.sessionCredentials`](/config/cli/#env-sessioncredentials) instead.

### Session credentials {#env-sessioncredentials}

`env.sessionCredentials` is a list of `{name, from?, repositories?}`. The default is `[]`:
a session holds no credential.

The credentials a spawned agent session **may** hold, by name
([issue-533](https://github.com/MadaraUchiha-314/the-loop/issues/533)). Use it when an
agent needs `gh` or `git` beyond the verbs the service wraps: `gh api` on an endpoint
the-loop does not wrap, a private release asset, a second private repository.

```yaml
env:
  file: .env
  sessionCredentials:
    - name: GH_TOKEN             # the variable the session sees
      from: SESSION_GH_TOKEN     # the daemon-side variable it comes from (default: name)
      repositories: [octo/app]   # optional: only sessions for these work items
```

- **`from` is for a narrower token.** Give sessions a fine-grained, read-mostly,
  short-lived token of their own, not the daemon's
  `integrations.github.api.tokenEnv`. Pointing `from` at one of the daemon's own
  credential names works, with a warning.
- **The value is never on an argv.** It is written to a per-spawn file of mode `0600`
  under `<state.root>/local/session-credentials/`. The pane reads it, deletes it and
  then starts the harness; only the file's path is on a command line. The value is never
  in the tmux client's environment, the tmux server's global environment or any tmux
  session's environment, so the web-terminal hub and other sessions never inherit it.
- **Read per spawn.** The value comes from `env.file` when the file declares `from`, else
  from the daemon's environment. A rotation shows up as a `stale` session in
  [`the-loop status`](/cli/commands/status), and
  [`sessions restart`](/cli/commands/sessions#restart) relaunches onto the new value.
- **Fail closed.** An entry whose `name` or `from` is not a variable name, or whose source
  is unset, is skipped with a warning that names the variable, never its value. A
  `repositories` list that matches nothing means the session does not get it. Either
  way the name stays stripped from the pane. `repositories` matches GitHub work items
  only, as `[HOST/]OWNER/REPO`.
- **Masked on the way out.** The service replaces every configured value with
  `<redacted:session-credential>` in the text a session sends it: comments, questions,
  replies, ticket and PR titles and bodies, and `graph force`/`skip` reasons. That
  covers everything the service then posts to GitHub, Jira or Slack. The event log
  masks the values its process has seen.
- **Visible.** `status` names the credentials running sessions hold, and `sessions list`
  shows them as `NAME@fingerprint`. Every spawn that hands one over logs a
  warning-level `session.credentials_inherited` event naming them.

::: danger An unattended agent holding a token can leak it
It can leak it through `env`, `set -x`, a debug dump, its transcript or a pasted log.
Masking covers text that passes through the service. It does not cover a `gh`, `git push`
or `curl` the agent runs with the token itself, or a value it has transformed (base64,
split). Masking reduces the risk; it does not remove it. Use a dedicated,
least-privilege, short-lived token. `env.sessionPassthrough` still refuses credential
names: this list is the only way a credential reaches a session.
:::

### `env.sessionCredentials[].name`

- **Type:** `string` (a variable name)
- **Default:** none — required

The variable the session sees.

### `env.sessionCredentials[].from`

- **Type:** `string` (a variable name)
- **Default:** the entry's `name`

The daemon-side variable the value is read from, per spawn: from `env.file` when the file
declares it, else the daemon's environment. It never reaches a session under its own name.

### `env.sessionCredentials[].repositories`

- **Type:** `string[]` (`[HOST/]OWNER/REPO`)
- **Default:** unset — every session

Only sessions for GitHub work items in these repositories get the credential. A Jira work
item or a standing session never does.

::: warning
**`repositories` limits delivery, not reach.** Every session runs as the same user, so an agent in any session can read another session's environment (`/proc/<pid>/environ`) while both run. A token scoped to a private repository is therefore reachable from a concurrent session on another repository. Do not rely on the scope to isolate a token from an untrusted work item. Isolating it needs sessions under separate users or a PID-isolated sandbox, which the-loop does not provide.
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
| [Instance options](/config/cli/instance-options) | `instance` — which instance of the-loop this config is, and the work items it manages |
| [Webhook options](/config/cli/webhook-options) | `webhooks.ghWebhook` — bind address, path, HMAC secret, event filter |
| [Routing options](/config/cli/routing-options) | `routing` — who may trigger, what spawns, how sessions are hosted |
| [Graphs](/config/cli/graphs-options) | `graphs` — graphs of your own, which `routing.control.commands` binds commands to |
| [Lifecycle hooks](/config/cli/hooks-options) | `hooks` — your code at the moments a work item's delivery turns, asked before the-loop acts; local or remote |
| [Standing-session options](/config/cli/standing-sessions-options) | `standingSessions` — the sessions the-loop keeps for itself, which belong to no work item |
| [Critic options](/config/cli/critics-options) | `critics` — the critic harnesses a session may hand its work to (moved here from the harness config in issue-352) |
| [Polling options](/config/cli/polling-options) | `polling` — the pull-based ingress and its sources |
| [Integrations options](/config/cli/integrations-options) | `integrations` — how the-loop's own calls reach GitHub, Slack and Jira |
| [Channels options](/config/cli/channels-options) | `channels` — the peers on the event bus (the Slack bot) and the ledger they record on |
| [Service options](/config/cli/service-options) | `service` — the control-plane API's bind, auto-start and cross-origin allowlist |
| [Observability options](/config/cli/observability-options) | `eventLog` — the JSONL trail the daemon writes |
| [Self-diagnosis options](/config/cli/self-diagnosis-options) | `selfDiagnosis` — the-loop filing issues for its own failures (opt-in) |

Every option on those pages is checked against the schema in both directions by a test in
the repository — a documented key the schema does not define fails the build, and so does
a schema key nobody documented.
