---
configBase: service
---

# Service options

Options under `service` — the control-plane API service started by
[`the-loop service start`](/cli/commands/service) (issue-161, decision-058). The
service carries **no in-app authentication** — a gateway owns that — so its own
posture is network scoping: loopback-only unless `exposed` is explicitly true, with
CORS pinned to `ui.origins`.

```yaml
service:
  host: 127.0.0.1
  port: 4114
  exposed: false
  autoStart: true
  ui:
    origins: ["http://localhost:5173"]
```

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

## Behaviour

### `autoStart`

- **Type:** `boolean`
- **Default:** `true`

Whether a CLI command may boot a local service on demand when none is reachable.
The service is the CLI's only execution path for core capabilities, so with
`autoStart: false` those commands fail (naming `the-loop service start`) until the
operator starts one.

## UI

### `ui.origins`

- **Type:** `array` of `string`
- **Default:** `["http://localhost:5173"]`

Browser origins allowed by CORS — pin to where the control-plane UI is actually
served. Never a wildcard: a malicious page in the operator's browser must not be
able to drive a local control plane (issue-161 abuse case 4).
