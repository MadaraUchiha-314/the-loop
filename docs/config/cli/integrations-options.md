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
It is now declared once here and fanned out internally. A config still carrying the old key
is **refused**, naming the replacement — see
[`the-loop migrate-config`](/cli/commands/migrate-config).

```yaml
integrations:
  github:
    transport: auto
    cli: { binary: gh }
    api: { tokenEnv: [GITHUB_TOKEN], baseUrl: "" }
```

::: tip Looking for Slack?
Slack is not an integration any more. It converged into the
[channels](/config/cli/channels-options) layer (issue-245, the owner's call on PR #267):
one `channels.slack` section configures the bot that posts notifications **and** carries
replies back. A config still declaring `integrations.slack` is refused with the
replacement named — [`the-loop migrate-config`](/cli/commands/migrate-config) removes it.
:::

## Choosing a transport

Transport is a **choice, not a mandate**:

- `auto` resolves token → binary, and **fails closed naming both remedies** if neither is
  available. It never guesses silently.
- An **explicit** transport is honoured verbatim and **fails rather than degrading**. If
  you asked for `api` and the token is missing, you get an error — not a quiet fallback to
  a CLI that might be authenticated as somebody else.

## GitHub

### `github.transport`

- **Type:** `'auto' | 'api' | 'cli'`
- **Default:** `auto`

How GitHub calls are made:

| Value | Means |
|-------|-------|
| `api` | stdlib HTTP with a token from `github.api.tokenEnv` |
| `cli` | the operator's authenticated `gh`, inheriting enterprise and SSO settings |
| `auto` | token first, then binary; fails closed naming both remedies |

### `github.host`

- **Type:** `string`
- **Default:** none — resolved (see below)

**Which GitHub the-loop is on** (issue-311). Set it to your GitHub Enterprise domain
(`ghe.corp.example`, or `ghe.corp.example:8443`) and every link the-loop posts — the Slack
notification for a pending decision, the ask's "answer on the ticket", the portable
record's `url`, the reviewer's suggested pull requests — and every `gh` call it makes
(`gh api --hostname …`, `gh issue … --repo HOST/OWNER/REPO`) name that host.

You rarely need to set it. A work item that arrives through a webhook or a poll already
carries its host in its ref, read off the event. This key answers for the refs the-loop
**mints from configuration** — the graph's own work item, derived from the repository's
`ticketing.github` — and it is the first of five tiers, resolved in this order:

| Tier | Source |
|------|--------|
| 1 | `integrations.github.host` — this key |
| 2 | the host of `github.api.baseUrl`, when it is not the public API (`https://<host>/api/v3`) |
| 3 | `$GH_HOST` — `gh`'s own override |
| 4 | the `origin` remote of the repository the loop is running in — `gh`'s own next answer; only in-session, never in a daemon |
| 5 | `github.com` |

A value that is not the shape of a host — a scheme, a path, credentials, a bare word with
no dot and no port — is skipped with a warning and the next tier answers. `github.com`
stays unwritten in refs and adds nothing to any `gh` argv, so a deployment on github.com
sees no change. The checkout directory's host is a separate, explicit key:
[`routing.workspace.defaultHost`](/config/cli/routing-options#workspace-defaulthost).
See [decision-104](/decisions/decision-104).

### `github.api.tokenEnv`

- **Type:** `string[]`
- **Default:** none

Environment variables holding a token, tried **in order**.

::: danger Variable names, never tokens
This is a list of *variable names*. Putting a token in this file commits it.
:::

### `github.api.baseUrl`

- **Type:** `string`
- **Default:** none (github.com)

API base URL — set it for a GitHub Enterprise host (`https://<host>/api/v3`). An
enterprise base also answers
[`github.host`](/config/cli/integrations-options#github-host) when that key is unset; and a
work item on an enterprise host is addressed at `https://<host>/api/v3` when this key is
left at the public default (issue-311).

### `github.cli.binary`

- **Type:** `string`
- **Default:** `gh`

Path or name of the `gh` CLI. One declaration, used by every feature that shells out to
GitHub: control-command paper-trail comments, dispatch
[reactions](/config/cli/routing-options#reactions-enabled), session
[announcements](/config/cli/routing-options#announce-enabled), and the GitHub
[poll provider](/config/cli/polling-options#sources-provider).

This is the key that replaced the three `ghBinary` declarations.

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
