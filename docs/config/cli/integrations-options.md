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
  slack:
    transport: sdk
    urlEnv: THE_LOOP_SLACK_WEBHOOK_URL
```

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

API base URL — set it for a GitHub Enterprise host.

### `github.cli.binary`

- **Type:** `string`
- **Default:** `gh`

Path or name of the `gh` CLI. One declaration, used by every feature that shells out to
GitHub: control-command paper-trail comments, dispatch
[reactions](/config/cli/routing-options#reactions-enabled), session
[announcements](/config/cli/routing-options#announce-enabled), and the GitHub
[poll provider](/config/cli/polling-options#sources-provider).

This is the key that replaced the three `ghBinary` declarations.

## Slack

### `slack.transport`

- **Type:** `'auto' | 'sdk' | 'webhook'`
- **Default:** `sdk`

- `sdk` — the official `slack-sdk`. Zero required dependencies of its own, but it is an
  **optional extra**: `pip install "the-loopy-one[slack]"`.
- `webhook` — a raw POST to an incoming-webhook URL. No dependency at all, so the base
  install stays a one-package install.

### `slack.urlEnv`

- **Type:** `string`
- **Default:** `THE_LOOP_SLACK_WEBHOOK_URL`

Environment variable holding the incoming-webhook URL.

::: danger A variable name, never the URL
A Slack incoming-webhook URL *is* the credential — anyone holding it can post to your
channel. Keep it in the environment.
:::

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
