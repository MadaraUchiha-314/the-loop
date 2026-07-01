# Decision 005: Provide a lightweight, extensible Python CLI (`the-loop`)

- **Status:** accepted
- **Date:** 2026-06-30
- **Deciders:** @MadaraUchiha-314 (via issue #1 update)
- **Work item:** issue-1

## Context

Issue #1 was updated to add: although the-loop is primarily a Claude/Cursor plugin, it
should ALSO expose a CLI for quality-of-life commands the plugin itself can use — for
example, running a server that receives GitHub (or Jira) webhooks. The issue specifies
the shape `the-loop gh-webhook start|stop`, requires the CLI to be extensible, and
mandates **Python** (lightweight) because future self-learning/ML capabilities are
mostly exposed as Python SDKs.

## Decision

- Ship a Python CLI package named **`the-loop`** under `cli/` (package `the_loop`),
  with the primary CLI `the-loop` and an **extensible command registry** (subclass
  `Command`, decorate with `@register`, drop the module in `commands/`).
- **Zero runtime dependencies** in the core (stdlib `argparse` + `http.server`); PyYAML
  is an optional extra used only to read `.the-loop/config.yaml` defaults; pytest is a
  dev extra.
- First command: **`gh-webhook start|stop`** — a GitHub webhook receiver that verifies
  the `X-Hub-Signature-256` HMAC (secret from an env var, never a flag), exposes
  `GET /health`, logs events, and is structured to route events to the harness later.
- Config: a `webhooks.ghWebhook` section in the schema (host/port/path/secretEnv/
  pidfile/events).

## Consequences

- The plugin gains an out-of-harness companion for webhook receipt and future
  quality-of-life automation, on a path toward issue #1's webhook/"dream" goals.
- Python keeps the door open for ML/self-learning features.
- Routing received webhook events through to actually trigger the harness remains
  deferred (R8) — this delivers the receiver scaffold.

## Alternatives considered

- Node/TS CLI to match the JS/TS tooling — rejected: the issue mandates Python for
  future ML SDKs.
- A heavy web framework (FastAPI/Flask) for the receiver — rejected: stdlib keeps it
  "very lightweight" with zero runtime deps.
