# Capability: control plane

> The API layer over the-loop's core, and its clients: the service-routed CLI,
> the MCP endpoint (issue-161, decision-058) and the static web dashboard
> (issue-207).

## What it is

the-loop's executable functionality is layered as **core → API → clients**: a
transport-agnostic core facade (`the_loop.core`, one module per capability) is the
single implementation; the API service (`the_loop.api`, FastAPI) exposes it at
`/api/v1` plus an MCP endpoint at `/mcp`; the CLI and an agent host are thin
clients of that surface. Everything needed to host the service ships with the
package — there are no install extras (owner decision, PR #162).

## Current behaviour

- The core facade SHALL be importable and invocable with no CLI or HTTP context;
  every capability (work items, events, graphs, repo-scoped queries, sessions,
  daemons, attention) SHALL be implemented once there, delegating to the modules
  that already carry the behaviour.
- A daemon the core **starts** SHALL have its stdout/stderr appended to that daemon's
  logfile under `state.root`, never sent to `/dev/null` (issue-191) — a control-plane
  start that runs fine and logs nowhere is the same defect a hand-backgrounded poller
  had. `daemon_status` SHALL carry that logfile, plus the poller's `startedAt` and
  `lastCycleAt` from its heartbeat (empty for `gh-webhook`, which keeps none).
- The API service SHALL expose the core at `/api/v1` per the **authored OpenAPI
  contract** (`docs/api-specs/openapi/the-loop.v1.yaml`); a parity test SHALL fail the build
  when the served schema's paths/methods/operationIds drift from it. Interactive
  docs are served at `/api/docs`, generated, never hand-written.
- The service SHALL carry **no in-app authentication** — a gateway terminates auth
  for any exposed deployment (owner decision, PR #162). Its own boundary SHALL be
  network scoping: it SHALL bind loopback by default and refuse a non-loopback bind
  unless `service.exposed: true`. No
  credential SHALL be minted, stored, or required.
- Which browser **origins** may read the service's responses SHALL be configuration
  (`service.cors`, issue-211) and SHALL be a separate question from who may connect:
  no value under `cors` widens the bind, and the exposure guard is unaffected. The
  allowlist SHALL ship containing exactly the origin the-loop publishes its own
  dashboard to, so the hosted page works against a local service with nothing in
  between ([decision-077](../decisions/decision-077.md)); an empty `allowOrigins`
  SHALL install no middleware at all, restoring same-origin-only behaviour. Origins
  SHALL be compared exact-string — no prefix, suffix or regex matching — and
  `"*"` together with `allowCredentials: true` SHALL refuse to start, before the bind
  and before the run lock. Chromium's private-network preflight SHALL be answered only
  for an origin the allowlist already admits.
- The CORS middleware SHALL sit outside the audit middleware, so a **preflight** runs
  no operation and emits no `api.request` event; `/mcp` SHALL keep the SDK's
  DNS-rebinding protection with its own loopback-only origin allowlist, so no CORS
  setting makes the MCP endpoint drivable from a page.
- `the-loop service start|stop|status` SHALL manage the service with the issue-159
  lifecycle discipline: the pidfile is the flock, a second start reports `already
  running`, stop signals and waits. Hosting needs no extra: `fastapi`, `uvicorn`
  and the official `mcp` SDK are required dependencies, so `pip install
  the-loopy-one` is always enough to run the service.
- The service SHALL be the CLI's **only execution path** for core capabilities
  (owner decision, PR #162): a command auto-starts a local service when
  `service.autoStart` allows and otherwise fails closed naming `the-loop service
  start` — never an in-process fallback. Every core-capability command routes:
  `check`, `events`, `graph` (show/status/advance/complete/force/run), `sessions`
  (register/list/close/start/pause/resume/stop), `scenarios`, `instructions` and
  `critic` (list/run). Four commands stay local **by nature**: `sessions attach`
  replaces the caller's terminal with tmux, `sessions reset` is a recovery action
  that must work when nothing is running, `poll start` / `gh-webhook start` run the
  daemon themselves because cron and systemd units depend on it — foreground by
  default, and detaching on their own with `--daemon` (issue-191) rather than
  through the service — and the bootstrap commands
  (`install`, `upgrade`, `migrate-config`, `service`, `--version`) precede any
  service. `THE_LOOP_SERVICE_LOCAL=1` is a test seam, not an operator switch.
- The CLI SHALL NOT re-implement any routed operation: commands render the
  `messages` and `exitCode` the core facade returns, so an operator's `sessions
  pause` and an agent's `control_session` tool call produce identical words.
- `/mcp` SHALL serve the MCP interface over **HTTP transport only** (no stdio),
  built on the **official MCP Python SDK** (`mcp`) rather than a hand-rolled
  protocol implementation (owner decision, PR #162). The SDK's DNS-rebinding
  protection stays on, pinned to the hosts the service answers on. `sessions
  reset` (destructive) and `graph force` (requires a human-attributed reason)
  SHALL NOT be exposed as tools.
- Every API operation SHALL land in the event log (`api.request`; tool calls as
  `mcp.call`), queryable via `the-loop events --source service`.
- A **static web dashboard** (`ui/`, issue-207) SHALL be the third client of the
  same surface, adding no state and no server of its own. It SHALL be a pure
  build artifact — published to GitHub Pages at `/the-loop/ui/`, beside the docs
  site, from the one Pages artifact both are assembled into — with the API base
  URL chosen at runtime and persisted per browser, so one hosted copy serves any
  number of workstations.
- The dashboard SHALL derive a work item's loop position from `graph/check`,
  whose `repo` comes from the session record's `cwd` and whose `workItem` comes
  from the portable record's `graph.workItem`. Because that join spans two
  records, an item with no session on this machine SHALL still be listed, showing
  its frozen node list with no pointer rather than an error — the API's inability
  to answer "where is it?" is not the same as the item not existing.
- The dashboard's inbox SHALL be the union of `/attention` and the graph gates
  that endpoint deliberately excludes: gate waits are repo-scoped, so
  `core.attention` documents them as reaching a client through `graphs.check` per
  work item, and the client that already reads those reports folds them back in.
- Where the dashboard's design specified a surface this API cannot back, that
  surface SHALL be rendered **disabled and named**, never mocked and never
  silently dropped. Two such surfaces exist today: the **inline reply** to an
  agent's question (needs a `the-loop ask` verb emitting `session.awaiting_input`,
  and a `POST /sessions/reply` that pastes into the pane — today
  `the_loop/interaction.py` directs the agent to post its own question with `gh`)
  and the **turns-and-tool-calls trace** (needs a transcript route; the harness
  runs as a CLI in tmux, so the record is its own file — for Claude Code a JSONL
  whose path the dashboard derives and displays).
- The dashboard SHALL hold no credential and mint none. The network posture is
  unchanged and is stated in its Settings screen: the service binds loopback, so a
  service on **another** machine is reached through an SSH tunnel or a gateway that
  terminates auth — never by exposing the service. A service on the **same** machine
  needs neither, since this page's origin is in the shipped `service.cors.allowOrigins`
  (issue-211).

## Design

[`docs/specs/issue-161/design.md`](../specs/issue-161/design.md) ·
[`docs/specs/issue-207/design.md`](../specs/issue-207/design.md) ·
[`docs/api-specs/openapi/the-loop.v1.yaml`](../api-specs/openapi/the-loop.v1.yaml) ·
[CLI: service](../cli/commands/service.md) ·
[config: service options](../config/cli/service-options.md) ·
[`ui/README.md`](https://github.com/MadaraUchiha-314/the-loop/blob/main/ui/README.md)

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-161 | Capability minted: core facade extracted, API service + OpenAPI contract, loopback-default network posture (no in-app auth — the gateway owns it, decision-059), service lifecycle commands, every core-capability command routed through the service, HTTP-only MCP endpoint on the official SDK, no install extras. The UI was descoped on owner review | [spec](../specs/issue-161/), [decision-058](../decisions/decision-058.md), [decision-059](../decisions/decision-059.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/161) |
| issue-211 | The dashboard can actually read the service: `service.cors` makes the allowed browser origins configuration, shipping the published page's own origin as the default. Exact-string origins only; `"*"` with credentials refuses to start; an empty list installs no middleware. The bind, the exposure guard and the MCP transport's origin check are unchanged | [spec](../specs/issue-211/), [decision-077](../decisions/decision-077.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/211) |
| issue-207 | The descoped UI lands: a static dashboard in `ui/` over the same `/api/v1`, published to `/the-loop/ui/` from the docs site's Pages artifact. Loop position joined from the session's `cwd` and the record's spec id; the inbox unions `/attention` with the repo-scoped graph gates it excludes; the two surfaces the API cannot back ship disabled and named | [spec](../specs/issue-207/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/207) |
