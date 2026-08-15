# Capability: the Python SDK

> the-loop as a component of somebody else's Python service: an importable capability
> surface and a mountable HTTP surface, both driven by one CLI config (issue-212).

## What it is

`the-loopy-one` ships three ways to run the same code. The CLI is one, the standalone
control-plane service is another, and the **SDK** (`the_loop.sdk`) is the third: `import
the_loop.sdk`, name a CLI config, and either call the capabilities directly or mount the
control plane's own `APIRouter` into a FastAPI application you already deploy — behind your
authentication, your middleware and your lifespan, in your process.

It is not a client library. It does not talk to a running service; it *is* the service's
implementation, imported. The seam exists because the layering already did:
`the_loop.core` has been transport-free since issue-161, so an SDK adds no capability —
only a supported, semantically-versioned way to reach one.

## Current behaviour

- `the_loop.sdk` SHALL expose a `TheLoop` class constructible with no HTTP service
  running, and SHALL group the core facade's capabilities as namespaces —
  `work_items`, `sessions`, `graph`, `events`, `daemons`, `attention`, `repo`,
  `settings` — each method delegating to `the_loop.core` rather than reimplementing it.
  A parity test SHALL fail the build when a namespace method names a `core` function that
  no longer exists.
- The SDK's exception contract SHALL be the core's: `ValueError` for a caller mistake,
  `LookupError` for a missing resource. Over HTTP the edge translates them to 400 and 404;
  in-process they reach the caller unchanged.
- Importing `the_loop.sdk` SHALL NOT import FastAPI, uvicorn or the MCP SDK — those are
  imported by the methods that build the HTTP seam, so a batch caller pays for `core` only.
- **Initialising the SDK SHALL be naming a CLI config.** `TheLoop(config_path=…)` reads
  that file; no argument resolves by the same order every other the-loop process uses; a
  document may be supplied directly (`config=`) for tests and secret-store deployments.
  Passing both SHALL raise. The resolved file SHALL be what every capability call, every
  route and every config write uses.
- The SDK SHALL read that config **strictly**: a missing or unparseable file SHALL raise at
  construction, naming the path, rather than degrading to `{}` as the CLI does. A
  long-lived service that starts on defaults nobody chose has an empty
  `routing.authorizedUsers` and fails closed invisibly.
- Changes to the config file SHALL be picked up without a restart — once per request for
  the HTTP seam, and on `TheLoop.reload()` for every other caller.
- **The `/api/v1` surface SHALL be one `APIRouter`**, built by `the_loop.api.routes` and
  consumed both by `create_app` (the standalone service) and by the SDK. A parity test
  SHALL assert the router's operations equal the served app's, which equal the authored
  OpenAPI contract — the embedded and standalone surfaces cannot drift because they are the
  same object.
- Per-request behaviour — the config refresh, the `ValueError`/`LookupError`/`SpliceError`
  translation, and the `api.request` audit event — SHALL ride on the router's **route
  class**, not on an application object, so it travels into a host application unchanged.
  `health` SHALL stay audit-exempt, keyed on its operation id so the exemption survives a
  prefix.
- `TheLoop.mount(app)` SHALL touch the host application in **at most two ways**, both
  requested: `include_router`, and (unless `lifespan=False`) its lifespan. It SHALL install
  no middleware, register no exception handlers, apply no CORS policy, and change neither
  the application's title nor its doc URLs.
- `dependencies=` SHALL apply to every the-loop operation before any handler executes, so a
  host's authorization cannot be bypassed by choosing a the-loop path. **No in-app
  authentication SHALL be added** (decision-059 stands): the deployment owns auth, and the
  SDK's obligation is to make attaching it a parameter.
- `TheLoop.lifespan` SHALL hold open what needs the process alive — the MCP session manager
  and, per `service.hostIngresses`, the hosted ingresses. `mount()` SHALL wrap it around
  the host's existing lifespan by default (the host's still runs, inside the-loop's), and
  `lifespan=False` SHALL hand composition to the caller. An MCP request arriving while the
  lifespan is not running SHALL be answered `503` naming the omission, never served against
  an unstarted session manager.
- The MCP app SHALL be mounted at the **prefix**, after the router, so `<prefix>/mcp`
  answers with no trailing-slash redirect. An empty prefix with MCP enabled SHALL be
  refused rather than shadowing host routes declared after the mount, and
  `mcp_allowed_hosts` SHALL let an embedded deployment declare the hosts it actually serves
  on (the default derivation describes the standalone service's bind).
- `mount()` SHALL return a report — prefix, operation count, MCP mount and path, lifespan
  mode, ingress hosting, dependency count — so a mount that did less than the embedder
  expected is visible at startup.
- Ingress hosting SHALL follow `service.hostIngresses` (the ticket's "everything still runs
  through the cli-config.yaml") and SHALL be declinable at the call site
  (`host_ingresses=False`), which is what a multi-worker deployment needs.
- **The environment contract SHALL be stated and checkable.**
  `the_loop.sdk.REQUIREMENTS` names each external binary (`gh`, `claude`, `cursor-agent`,
  `tmux`, `git`, `ttyd`), the config key that renames it, the capability it serves, and the
  predicate deciding whether *this* configuration needs it.
  `TheLoop.check_environment()` resolves them against `PATH` and returns
  `{"ok", "checks"}`, where `ok` is false only when a **required** binary is absent. It
  SHALL resolve with `shutil.which` and SHALL NOT execute what it finds, and it SHALL be a
  report, never a gate. A parity test SHALL assert the table and
  `docs/sdk/environment.md` name the same binaries, in both directions.
- Process **lifecycle writes** SHALL NOT be on the SDK. `TheLoop.status()` reads;
  `start`/`stop`/`restart` manage the-loop's own processes and are meaningless (or, via
  `--with-upgrade`, actively wrong) inside somebody's web service. The REST router still
  carries `POST /api/v1/restart` and the daemon controls, because dropping them would break
  the one-router guarantee; the documentation names both as operations whose meaning
  changes when embedded.
- Everything in `the_loop.sdk.__all__` and documented on `TheLoop` SHALL be public and
  change under semantic versioning; `the_loop.core`, `the_loop.api` and the rest SHALL stay
  internal.

## Design

[`docs/specs/issue-212/design.md`](../specs/issue-212/design.md) ·
[SDK overview](../sdk/index.md) ·
[embedding](../sdk/embedding.md) ·
[environment expectations](../sdk/environment.md) ·
[SDK reference](../sdk/reference.md) ·
[vendor-SDK analysis](../reports/vendor-sdk-analysis.md)

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-212 | Capability minted: `the_loop.sdk` with `TheLoop`, eight capability namespaces, a mountable `APIRouter` extracted from `create_app` (one surface, two consumers, parity-tested), lifespan composition that wraps the host's by default, MCP under a prefix with a declarable host allowlist, strict config-at-construction, and an executable environment contract. The SDK installs no middleware, no exception handlers and no CORS on the host application; authorization is a `dependencies=` parameter, not an in-app layer | [spec](../specs/issue-212/), [decision-085](../decisions/decision-085.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/212) |
