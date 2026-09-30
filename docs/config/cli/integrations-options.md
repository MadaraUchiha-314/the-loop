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
`github.transport`, `github.cli`) is **refused**, naming the replacement — see
[`the-loop migrate-config`](/cli/commands/migrate-config).

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

### `jira.transport`

- **Type:** `'auto' | 'api' | 'cli'`
- **Default:** `api`

How Jira calls are made. Same semantics as GitHub's.

### `jira.api.baseUrl`

- **Type:** `string`
- **Default:** none

Jira API base URL, e.g. `https://your-org.atlassian.net`.

### `jira.api.tokenEnv`

- **Type:** `string`
- **Default:** none

Environment variable holding the Jira API token. A name, not a token.

### `jira.cli.binary`

- **Type:** `string`
- **Default:** `jira`

Path or name of the Jira CLI.

## Next

- [Observability options](/config/cli/observability-options) — the event log and who gets
  notified.
- [Routing options](/config/cli/routing-options) — the features that use these transports.
