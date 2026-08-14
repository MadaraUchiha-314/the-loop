---
configBase: service
---

# Service options

Options under `service` — the control-plane API service started by
[`the-loop start`](/cli/commands/start) or
[`the-loop service start`](/cli/commands/service) (issue-161, decision-058). The
service carries **no in-app authentication** — a gateway owns that — so its own
posture is network scoping: loopback-only unless `exposed` is explicitly true.

```yaml
service:
  enabled: true
  host: 127.0.0.1
  port: 4114
  exposed: false
  autoStart: true
  mcp:
    enabled: true
  cors:
    allowOrigins: ["https://madarauchiha-314.github.io"]
    allowMethods: [GET, POST, OPTIONS]
    allowHeaders: [Accept, Content-Type]
    allowCredentials: false
    allowPrivateNetwork: true
```

## Lifecycle

### `enabled`

- **Type:** `boolean`
- **Default:** `true`

Whether [`the-loop start`](/cli/commands/start) brings the service up (issue-228,
[decision-084](/decisions/decision-084)). Default on: the service is the CLI's only
execution path for core capabilities. `false` also disables `autoStart` — a service the
operator disabled must not resurrect because an unrelated CLI command wanted it
(fail-closed, the affected command names this key) — while the explicit
`the-loop service start` still works.

### `mcp.enabled`

- **Type:** `boolean`
- **Default:** `true`

Whether the service mounts the [MCP endpoint](/cli/commands/service#mcp-connecting-an-agent)
at `/mcp` (issue-228). Default on — `/mcp` has been mounted unconditionally since
issue-161 — so the flag exists to *narrow* a deployment to REST-only: with `false`, no
MCP app is built and `/mcp` answers 404.

## Binding

### `host`

- **Type:** `string`
- **Default:** `127.0.0.1`

Bind host. The API is an RCE-equivalent surface — it can spawn harness sessions with
the operator's credentials — so a non-loopback value **refuses to boot** unless
`exposed` is true. Prefer keeping the loopback default and fronting the service with
something that provides exposure and TLS deliberately.

### `port`

- **Type:** `integer`
- **Default:** `4114`

Bind port. Also where the CLI and UI look for the service
(`http://<host>:<port>`).

### `exposed`

- **Type:** `boolean`
- **Default:** `false`

Explicit opt-in to serving beyond loopback. There is no in-app authentication, so
only set this when an auth-terminating gateway fronts the service; this flag only
unlocks the bind.

## Cross-origin access

**Two different questions, two different blocks.** `host`/`exposed` above decide **who
may connect**; `cors` decides **which browser page may read the answer**. Nothing under
`cors` widens the bind, and a page on an allowed origin still has to reach the service —
over loopback, a tunnel, or a gateway — before any of this applies.

It exists because the [dashboard](/cli/commands/service) is published to GitHub Pages and
the service it drives runs on your workstation. Without an `Access-Control-Allow-Origin`
header the browser throws the response away, and the only alternative remedy is a proxy
in front of a port that is already listening on your own machine.

::: warning What the default admits
The default allows one origin, `https://madarauchiha-314.github.io` — where the-loop's
own dashboard is published. An origin is host-granular, and that host serves **every**
GitHub Pages site under that account, so a script on any of them can read this service
from a browser you have open. The service has no in-app auth, so "read" means "drive".
Set `allowOrigins: []` if you do not use the hosted dashboard. See
[decision-077](https://github.com/MadaraUchiha-314/the-loop/blob/main/docs/decisions/decision-077.md).
:::

### `cors.allowOrigins`

- **Type:** `string[]`
- **Default:** `["https://madarauchiha-314.github.io"]`

Exact origins — scheme, host and port, **no path** — allowed to read responses. The
comparison is exact-string: no prefix, suffix or regex match, so
`https://madarauchiha-314.github.io.example.com` is not admitted by the default and
`https://ops.example.com/app` matches nothing (the browser never sends the path).

`[]` disables cross-origin access entirely — no middleware is installed and the service
behaves exactly as it did before this option existed. `"*"` allows every origin; it is
allowed on its own and **refused at start-up** together with `allowCredentials: true`.

### `cors.allowMethods`

- **Type:** `string[]`
- **Default:** `["GET", "POST", "OPTIONS"]`

Methods a cross-origin caller may use. The default is exactly what the dashboard sends;
the API has no other verbs.

### `cors.allowHeaders`

- **Type:** `string[]`
- **Default:** `["Accept", "Content-Type"]`

Request headers a cross-origin caller may send beyond the browser's own safelist. Add
`Authorization` when a gateway in front of the service expects a bearer token from the
page.

### `cors.allowCredentials`

- **Type:** `boolean`
- **Default:** `false`

Whether the browser may attach cookies or HTTP credentials to cross-origin requests.
the-loop's own client sends none, so leave this off unless a gateway authenticates the
page itself. `true` together with `"*"` in `allowOrigins` makes the service **refuse to
start**, naming both keys — browsers reject that pair anyway, and a deployment that
honoured it would hand every site on the internet an authenticated read.

### `cors.allowPrivateNetwork`

- **Type:** `boolean`
- **Default:** `true`

Answer Chromium's private-network preflight
(`Access-Control-Request-Private-Network` → `Access-Control-Allow-Private-Network`),
which is what a **public HTTPS page reaching a loopback address** has to clear. It is
answered only for an origin `allowOrigins` already admits, so this never widens the
allowlist — it can only decline what the allowlist let through.

## Behaviour

### `autoStart`

- **Type:** `boolean`
- **Default:** `true`

Whether a CLI command may boot a local service on demand when none is reachable.
The service is the CLI's only execution path for core capabilities, so with
`autoStart: false` those commands fail (naming the lifecycle commands) until the
operator starts one. Honoured only while `enabled` is true — a disabled service never
auto-starts (issue-228).
