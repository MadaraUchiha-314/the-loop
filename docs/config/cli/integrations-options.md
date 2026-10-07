---
configBase: integrations
---

# Integrations options

Options under `integrations` — how **the-loop's own** calls reach external services.

::: tip Control plane only
This governs what the *daemon* does: posting a reaction, announcing a session, notifying a
channel, reading an item's state. What the **agent** does from inside its session is
unconstrained — CLI, MCP, API, whatever the harness has. Nothing here narrows the agent.
:::

Introduced by issue-109 to replace three copies of one setting: `ghBinary` used to be
declared separately under `routing.control`, `routing.reactions` and `routing.announce`.
Since issue-442 there is no binary at all: the daemon reaches GitHub through
[PyGithub](https://github.com/pygithub/pygithub/) under **one token**, named here and read
from the process environment. A config still carrying a retired key (`ghBinary`,
`github.transport`, `github.cli`, `jira.transport`, `jira.cli`) is **refused**, naming
the replacement — see [`the-loop migrate-config`](/cli/commands/migrate-config).

```yaml
integrations:
  github:
    # host: ghe.corp.example
    api:
      tokenEnv: [GH_TOKEN, GITHUB_TOKEN]
      baseUrl: https://api.github.com   # or https://<host>/api/v3 for GitHub Enterprise
```

::: tip Looking for Slack?
Slack is not an integration any more. It converged into the
[channels](/config/cli/channels-options) layer (issue-245, the owner's call on PR #267):
one `channels.slack` section configures the bot that posts notifications **and** carries
replies back. A config still declaring `integrations.slack` is refused with the
replacement named — [`the-loop migrate-config`](/cli/commands/migrate-config) removes it.
:::

## One transport, one token

The daemon's own GitHub calls — the control paper trail, dispatch reactions, session
announcements, the poller's reads, the existence check, the process graph's labels and
comments, the self-diagnosis issue, the channel ledger — all go through one client built on
PyGithub ([decision-139](/decisions/decision-139)). It authenticates with the first set
variable of [`github.api.tokenEnv`](/config/cli/integrations-options#github-api-tokenenv), read **at call time** from the
daemon's environment; an [`env.file`](/config/cli/instance-options) can hold it. Nothing
runs a `gh` binary any more, and nothing bridges through `gh auth token`.

**A missing token is loud, never worked around.** Every best-effort writer reports
`no GitHub token: set GH_TOKEN or GITHUB_TOKEN` and does nothing else (once per process in
the log); the poller's pre-flight names the variables; the process graph's integration
refuses with the same sentence.

**Scopes.** A fine-grained personal access token needs *Issues: read and write*,
*Pull requests: read* and *Metadata: read* on every repository the instance works with
(the top-level [`repositories`](/config/cli/repositories-options)); a classic token needs
`repo`. The token's login is the author of every comment the-loop writes, which is why each
one carries the `<!-- the-loop:agent-comment -->` marker — the ledger reads its own writes
by that login (`the-loop channels records`).

::: details Upgrading from a `gh`-based deployment (before 19.16)
`github.transport` (`auto | api | cli`) and `github.cli.binary` are gone.
[`the-loop migrate-config`](/cli/commands/migrate-config) removes both and, when the file
relied on the binary (`transport: cli`) or named no token variable, says which variable to
set. Until it is set the daemon posts nothing and reads nothing from GitHub, and says so.
:::

## GitHub

### `github.host`

- **Type:** `string`
- **Default:** none — resolved (see below)

**Which GitHub the-loop is on** (issue-311). Set it to your GitHub Enterprise domain
(`ghe.corp.example`, or `ghe.corp.example:8443`) and every link the-loop posts — the Slack
notification for a pending decision, the ask's "answer on the ticket", the portable
record's `url`, the reviewer's suggested pull requests — and every API call it makes name
that host.

You rarely need to set it. A work item that arrives through a webhook or a poll already
carries its host in its ref, read off the event. This key answers for the refs the-loop
**mints from configuration** — the graph's own work item, derived from the repository's
`ticketing.github` — and for the bare `OWNER/REPO` entries of the top-level
[`repositories`](/config/cli/repositories-options) (issue-331, issue-348), and
it is the first of five tiers, resolved in this order:

| Tier | Source |
|------|--------|
| 1 | `integrations.github.host` — this key |
| 2 | the host of `github.api.baseUrl`, when it is not the public API (`https://<host>/api/v3`) |
| 3 | `$GH_HOST` — kept as a plain environment convention (it is `gh`'s, and harmless) |
| 4 | the `origin` remote of the repository the loop is running in — only in-session, never in a daemon |
| 5 | `github.com` |

A value that is not the shape of a host — a scheme, a path, credentials, a bare word with
no dot and no port — is skipped with a warning and the next tier answers. `github.com`
stays unwritten in refs, so a deployment on github.com sees no change. The checkout
directory's host is a separate, explicit key:
[`routing.workspace.defaultHost`](/config/cli/routing-options#workspace-defaulthost).
See [decision-104](/decisions/decision-104).

### `github.api.tokenEnv`

- **Type:** `string[]`
- **Default:** `[GH_TOKEN, GITHUB_TOKEN]`

Environment variables holding the daemon's GitHub token, tried **in order**; the first one
set wins, read at call time.

::: danger Variable names, never tokens
This is a list of *variable names*. Putting a token in this file commits it.
:::

### `github.api.baseUrl`

- **Type:** `string`
- **Default:** `https://api.github.com`

API base URL. Leave it at the public API and every work item is addressed at **its own**
host — `https://<host>/api/v3` for a ref on GitHub Enterprise (issue-311), the public API
for github.com. Set an enterprise base explicitly and it is honoured verbatim for every
call; it also answers [`github.host`](/config/cli/integrations-options#github-host) when that key is unset.

## Jira

**One Jira site per deployment** (issue-475, [decision-142](/decisions/decision-142)).
Absent, Jira is off and the daemon loads nothing from the Jira SDK. Present, the daemon
reaches the site through the pycontribs [`jira`](https://jira.readthedocs.io/) SDK:

| `deployment` | Requests go to | Credential | REST, comment format |
|---|---|---|---|
| `cloud` | `https://<site>` | account email + API token (basic) | v3, ADF |
| `cloud-scoped` | `https://api.atlassian.com/ex/jira/<cloudId>` | account email + scoped API token | v3, ADF |
| `data-center` | `https://<site>` | personal access token (Bearer) | v2, wiki markup |

```yaml
integrations:
  jira:
    site: acme.atlassian.net
    deployment: cloud
    api:
      emailEnv: [JIRA_EMAIL]
      tokenEnv: [JIRA_API_TOKEN]
    projects:
      PROJ: {repository: acme/web}   # PROJ tickets' code, specs and PRs live in acme/web
      OPS: {}                        # mirror-only: a room, never a work-item source
    # closeTransition: Done
```

A ref on another site, or on a project not listed under `projects`, is refused before any
request is sent. Use a **dedicated service account**. A scoped token needs
`read:jira-work`, `write:jira-work` and `read:jira-user`; no admin scope is needed.
[`the-loop doctor jira`](/cli/commands/doctor#doctor-jira) reports a block whose
credential variables are not set.

::: details Upgrading from the 0.11 stub
`jira.transport` and `jira.cli` are gone: the-loop runs no `jira` binary.
[`the-loop migrate-config`](/cli/commands/migrate-config) removes them, turns a string
`api.tokenEnv` into a list, and turns a legacy `api.baseUrl` into `site` with
`deployment: cloud`. It then asks for the two things the stub never held: `api.emailEnv`
and `projects`.
:::

### `jira.site`

- **Type:** `string`
- **Default:** none — required

The Jira site as a bare host, e.g. `acme.atlassian.net`: no scheme, no path. Every
`jira:<site>/<KEY>-<n>` ref names it.

### `jira.deployment`

- **Type:** `'cloud' | 'cloud-scoped' | 'data-center'`
- **Default:** none — required

Which Jira this is. It picks the server URL, the authentication and the REST version (the
table above).

### `jira.cloudId`

- **Type:** `string`
- **Default:** none — required for `cloud-scoped`

The site's cloud id, from `https://<site>/_edge/tenant_info`. Scoped-token calls go
through `https://api.atlassian.com/ex/jira/<cloudId>`.

### `jira.api.emailEnv`

- **Type:** `string[]`
- **Default:** none — required for `cloud` and `cloud-scoped`

Environment variables holding the Jira account's email, tried in order and read at call
time. Unused on `data-center`.

### `jira.api.tokenEnv`

- **Type:** `string[]`
- **Default:** none — required

Environment variables holding the token, tried in order and read at call time: a Cloud
API token, or a Data Center personal access token.

::: danger Variable names, never values
Both lists hold *variable names* matching `^[A-Z_][A-Z0-9_]*$`. A token or an email
written here fails validation.
:::

### `jira.projects`

- **Type:** `map<KEY, {repository?: string}>`
- **Default:** none — at least one required

The Jira projects this deployment works with. A key matches `^[A-Z][A-Z0-9_]{1,9}$`.
`repository` (`owner/repo`, on [`github.host`](/config/cli/integrations-options#github-host)) is where that project's
tickets get their spec chain, worktree and pull requests. A project without one is
**mirror-only**: it can be a `jira@` room, never a work-item source.

### `jira.closeTransition`

- **Type:** `string`
- **Default:** none

The transition name that closes a ticket. Unset, the one available transition into the
*Done* status category is used. None, or several, is an error that lists them: the-loop
never guesses.

## Next

- [Observability options](/config/cli/observability-options) — the event log and who gets
  notified.
- [Routing options](/config/cli/routing-options) — the features that use these transports.
