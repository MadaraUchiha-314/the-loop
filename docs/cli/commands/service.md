# `the-loop service`

Run the **control-plane API service** — the HTTP layer over the-loop's core that the
CLI, the [MCP endpoint](/cli/commands/service#mcp) and the control-plane UI consume
(issue-161, decision-058). The service is the CLI's **only execution path** for core
capabilities: commands like `sessions`, `check` and `events` talk to it (auto-starting
a local one when [`service.autoStart`](/config/cli/service-options#autostart) allows)
instead of executing core logic in-process.

Hosting a service requires the `[service]` extra:

```sh
pip install 'the-loopy-one[service]'   # or: uv tool install 'the-loopy-one[service]'
```

A base install (no extra) can still *talk to* a running service — the client is
stdlib-only — and `service start` without the extra fails with the install line above.

## Authentication

The service carries **no in-app authentication**. It is meant to run behind a
gateway that terminates auth, and locally it binds **loopback only** by default,
so the network boundary — not a token — is what protects it. Do not expose it on a
network without an auth-terminating gateway in front
([`service.exposed`](/config/cli/service-options#exposed) is the explicit opt-in
that lets it bind beyond loopback at all).

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
[`specs/openapi/the-loop.v1.yaml`](https://github.com/MadaraUchiha-314/the-loop/blob/main/specs/openapi/the-loop.v1.yaml)
— a parity test fails the build when the served schema drifts from it. Interactive
docs are served at `/api/docs`. Work items, graph check/advance/complete/force,
sessions and their control verbs, the event log, daemon lifecycle, needs-attention,
and repo-scoped queries (scenarios / instructions / critics) are all exposed;
`sessions reset` deliberately is **not** (a destructive verb stays a local decision).

## MCP

The same app serves an MCP endpoint at `/mcp` (HTTP transport only): the tools mirror
the read + manage surface with the same event-log audit trail. Destructive or
attribution-forging operations (`sessions reset`, `graph force`) are not exposed as
tools.

## Observability

Every API operation lands in the [event log](/cli/commands/events) as an
`api.request` record (source `service`). `the-loop events --source service` is the
query.
