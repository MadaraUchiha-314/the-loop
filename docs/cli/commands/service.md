# `the-loop service`

Run the **control-plane API service** — the HTTP layer over the-loop's core that the
CLI and the [MCP endpoint](#mcp-connecting-an-agent) consume
(issue-161, decision-058). The service is the CLI's **only execution path** for core
capabilities: `sessions`, `check`, `graph`, `events`, `scenarios`, `instructions` and
`critic` all talk to it (auto-starting a local one when
[`service.autoStart`](/config/cli/service-options#autostart) allows) instead of
executing core logic in-process.

## Install and run it locally

Everything needed to host the service ships with the package — there are **no
extras** to remember:

```sh
uv tool install the-loopy-one     # or: pip install the-loopy-one
the-loop service start
```

That is the whole setup. `service start` boots the service, waits for
`/api/v1/health` to answer, and prints the URL it is listening on:

```console
$ the-loop service start
service started at http://127.0.0.1:4114

$ the-loop service status
running (pid 24846, http://127.0.0.1:4114, healthy)

$ curl -s http://127.0.0.1:4114/api/v1/health
{"status":"ok","version":"7.1.1"}
```

You do not have to start it by hand. Any routed command starts one for you the first
time it needs it, so a fresh install works immediately:

```console
$ the-loop check issue-161
issue-161: ok (at pr-review)
```

Set [`service.autoStart: false`](/config/cli/service-options#autostart) if you would
rather manage the process yourself (a systemd unit, a container); commands then fail
with `the-loop service start` in the message instead of booting one.

To change the port or bind address, set
[`service.host` / `service.port`](/config/cli/service-options) in your CLI config:

```yaml
service:
  host: 127.0.0.1
  port: 4114
```

## Authentication

The service carries **no in-app authentication**. It is meant to run behind a
gateway that terminates auth, and locally it binds **loopback only** by default,
so the network boundary — not a token — is what protects it. Do not expose it on a
network without an auth-terminating gateway in front
([`service.exposed`](/config/cli/service-options#exposed) is the explicit opt-in
that lets it bind beyond loopback at all).

## The web dashboard, and CORS

The [dashboard](https://madarauchiha-314.github.io/the-loop/ui/) is a static page on
GitHub Pages pointed at whichever machine runs the service, so its calls are
**cross-origin** and the browser needs the service's permission to read the answers.
That permission is
[`service.cors.allowOrigins`](/config/cli/service-options#cors-alloworigins), and it
ships allowing the published dashboard's origin — so the page works against a local
service with nothing in between.

It is a *read* permission, not a network one: the loopback bind and the exposure guard
are unchanged, and no CORS setting can loosen them. Read what the default admits before
keeping it, and set `allowOrigins: []` if you do not use the hosted page.

## `service start`

Starts the service in the background and waits for `/api/v1/health` to answer.

- The pidfile **is** the lock (`<state.root>/local/service.pid`, flock — the
  issue-159 lifecycle discipline): a second `start` reports `already running` and
  starts nothing.
- Binding beyond loopback refuses to boot unless
  [`service.exposed`](/config/cli/service-options#exposed) is explicitly true — the
  API can spawn harness sessions with the operator's credentials, so "accidentally on
  the network" is made impossible. Set it only when a gateway fronts the service.

## `service stop`

Signals the running service (SIGTERM) and **waits** for the lock to be released
(`--timeout`, default 30s). Stopping a service that is not running reports so and
exits 0 — stop is idempotent.

## `service status`

Reports `not running`, or `running (pid …, http://…, healthy|unresponsive)`.

## The API surface

The contract is authored in
[`docs/api-specs/openapi/the-loop.v1.yaml`](https://github.com/MadaraUchiha-314/the-loop/blob/main/docs/api-specs/openapi/the-loop.v1.yaml)
— a parity test fails the build when the served schema drifts from it. Interactive
docs are served at `/api/docs`. Work items, the process graph
(show/check/advance/complete/force), sessions and their register/close/control verbs,
the event log, daemon lifecycle, needs-attention, and repo-scoped queries (scenarios /
instructions / critics, and running one critic round) are all exposed; `sessions reset`
deliberately is **not** (a destructive verb stays a local decision).

## MCP: connecting an agent

The same app serves an **MCP endpoint** at `/mcp`, built on the
[official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk).
Transport is **streamable HTTP only — there is no stdio server**, so every client
below is configured with a URL rather than a command to spawn.

Start the service first; the endpoint is live as soon as it is:

```sh
the-loop service start          # -> http://127.0.0.1:4114/mcp
```

### Claude Code

```sh
claude mcp add --transport http the-loop http://127.0.0.1:4114/mcp
```

Add `--scope project` to write it to the repository's `.mcp.json` so everyone
working the repo gets it, or `--scope user` for every project on your machine.
Check it connected with `/mcp` inside a session.

### Claude Desktop

Edit `claude_desktop_config.json`
(macOS: `~/Library/Application Support/Claude/`, Windows: `%APPDATA%\Claude\`):

```json
{
  "mcpServers": {
    "the-loop": {
      "type": "http",
      "url": "http://127.0.0.1:4114/mcp"
    }
  }
}
```

Restart Claude Desktop afterwards.

### Cursor

Add it to `.cursor/mcp.json` in the project (or `~/.cursor/mcp.json` globally):

```json
{
  "mcpServers": {
    "the-loop": {
      "url": "http://127.0.0.1:4114/mcp"
    }
  }
}
```

### Anything else

Any MCP client that speaks streamable HTTP works — point it at
`http://<host>:<port>/mcp`. Two things to know:

- **No auth header is needed** and none is accepted: the service has no in-app auth
  (see above). If you put it behind a gateway, configure the credential in the
  client the way that gateway expects.
- The SDK's **DNS-rebinding protection** is left on and pinned to the host the
  service is configured to bind. Reach it on that host (`127.0.0.1` by default) —
  a `Host` header naming something else is rejected with a 421, on purpose.

### What the tools do

The tools mirror the API's read and manage surface over the same core facade, so an
agent sees exactly what the CLI does:

| Tool | What it does |
| --- | --- |
| `list_work_items`, `get_work_item` | The portable records: control and poll state |
| `check_work_item` | Evaluate a work item's process-graph gates (the `the-loop check` report) |
| `graph_show`, `graph_advance`, `graph_complete` | Read the graph; take an edge; file a completion claim |
| `list_sessions`, `register_session`, `close_session`, `control_session` | The session registry and its `start`/`pause`/`resume`/`stop` verbs |
| `query_events` | The structured event log |
| `daemon_status`, `control_daemon` | The poller and gh-webhook daemons |
| `list_attention` | What needs a human: paused sessions, armed items with no session, recent errors |
| `repo_scenarios`, `repo_instructions`, `repo_critics`, `repo_critic_run` | Repo-scoped queries, and one critic-review round |

Two operations are deliberately **not** tools: `sessions reset` is destructive and
stays a local decision, and `graph force` requires a human-attributed reason an agent
must not forge.

## Observability

Every API operation lands in the [event log](/cli/commands/events) as an
`api.request` record (source `service`). `the-loop events --source service` is the
query.
