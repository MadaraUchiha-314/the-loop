# Embedding in an existing FastAPI app

::: danger Authorize it, or do not expose it
This surface can spawn harness sessions with the operator's credentials, read session
transcripts and rewrite the CLI config. The standalone service defends itself with a
loopback-only bind and a CORS allowlist — **neither of those exists once the router is in
your application**. The bind is yours, the browser policy is yours, and so is the
authorization.

Pass `dependencies=` and mean it.
:::

## The whole thing

```python
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from the_loop.sdk import TheLoop

loop = TheLoop(config_path="/etc/the-loop/cli-config.yaml")


def verify_caller(request: Request) -> None:
    if request.headers.get("x-api-key") != EXPECTED_KEY:
        raise HTTPException(status_code=401, detail="unauthorized")


app = FastAPI(title="platform-api")

report = loop.mount(
    app,
    prefix="/the-loop",
    dependencies=[Depends(verify_caller)],
    mcp_allowed_hosts=["platform.internal.example"],
)
logger.info("the-loop mounted: %s", report)
```

`report` is a plain dict, and reading it at startup is worth the two lines:

```python
{'prefix': '/the-loop', 'operations': 29,
 'mcp': {'mounted': True, 'path': '/the-loop/mcp'},
 'lifespan': 'wrapped', 'hostIngresses': True, 'dependencies': 1}
```

A mount that silently did less than you expected — MCP disabled in the config, ingresses
declined — is visible there rather than at the first failing call.

## What `mount()` touches

Exactly two things, both of which you asked for:

| Touched | Why | Opt out |
|---------|-----|---------|
| `app.include_router(...)` | the operations | — |
| `app.router.lifespan_context` | the MCP session manager and the hosted ingresses need the process alive | `lifespan=False` |

It installs no middleware, registers no exception handlers, applies no CORS policy, and
changes neither your `title` nor your doc URLs. Error mapping (`ValueError` → 400,
`LookupError` → 404) rides on the router's own route class, so it works in an application
that registers no handlers at all.

Because it may wrap your lifespan, **call `mount()` while the application is being
constructed**, before it starts serving. That is the SDK's only ordering constraint.

## Authorization

`dependencies` are FastAPI dependencies, applied to every the-loop operation before any
handler runs. There is no path that skips them — a request that chooses
`/the-loop/api/v1/sessions/control` over `/the-loop/api/v1/health` meets the same
dependency.

Anything a dependency can express works: an API key, a bearer token verified against your
IdP, a per-scope check, mTLS terminated upstream and read off a header.

```python
def require_scope(scope: str):
    def dependency(claims: dict = Depends(current_claims)) -> None:
        if scope not in claims.get("scopes", []):
            raise HTTPException(status_code=403, detail=f"needs {scope}")
    return dependency

loop.mount(app, dependencies=[Depends(require_scope("the-loop:admin"))])
```

Need finer granularity than "one policy for the whole surface"? Skip `mount()` and include
the router yourself as many times as you have policies — but note that the router carries
every operation each time, so the practical shape is one mount plus your own routes in
front of the operations you want to narrow.

## Middleware

Your middleware applies to the-loop's routes exactly as it applies to your own, in your
order — request-id stamping, structured access logs, tracing, timing, compression. There
is nothing to configure: they are your app's routes now.

```python
@app.middleware("http")
async def transaction_id(request: Request, call_next):
    token = request.headers.get("x-transaction-id", new_id())
    response = await call_next(request)
    response.headers["x-transaction-id"] = token
    return response
```

## CORS

The SDK deliberately installs none. `service.cors` configures the **standalone** service,
where the-loop owns the whole application; applying one the-loop config key to every route
of an app it does not own is not a decision a library gets to make for you.

If a browser page needs to read these routes, add `CORSMiddleware` to your app as you would
for any other route:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://console.example"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Accept", "Content-Type"],
)
```

## Lifespan

Two things need the process to be *running*, not merely imported: the MCP session manager
(without it the first `/mcp` call fails) and the hosted ingresses. `mount()` arranges both
by wrapping whatever lifespan your app already has — yours still runs, inside the-loop's.

To own the composition instead:

```python
@asynccontextmanager
async def lifespan(app):
    async with loop.lifespan(app):
        await my_startup()
        yield
        await my_shutdown()

app = FastAPI(lifespan=lifespan)
loop.mount(app, lifespan=False)
```

If you pass `lifespan=False` and then forget to compose it, the MCP endpoint answers `503`
saying so rather than meeting an unstarted session manager.

::: tip Why wrapping is the default
Not composing the lifespan is silent at import, silent at startup, and surfaces as an
obscure session-manager error on the first MCP call — in production, from a client.
:::

## The MCP endpoint

With `service.mcp.enabled` (default true), `mount()` also mounts the MCP streamable-HTTP
app so `<prefix>/mcp` answers — the URL you paste into Claude Code or Cursor.

Two things to know:

**The prefix may not be empty when MCP is mounted.** The MCP app is mounted *at* the
prefix, after the router, so `<prefix>/mcp` answers exactly with no trailing-slash redirect
(some MCP clients will not follow one on a POST). At the root that mount would shadow every
route your app declares after `mount()`, so the SDK refuses instead. `prefix="/the-loop"` is
the default; `mcp=False` opts out of MCP entirely.

**Set `mcp_allowed_hosts` to your own hostnames.** The MCP SDK's DNS-rebinding guard checks
the `Host` header against an allowlist, which the-loop derives from `service.host`/
`service.port` — the standalone service's bind, not yours. A deployment reachable at
`platform.internal.example` passes it explicitly, or gets a `421`.

## The hosted ingresses

`service.hostIngresses` (default true) means the process running the service also runs the
enabled ingresses — the poller and the webhook receiver — as background threads. Embedded,
that process is *yours*.

Usually that is what you want: one deployment, one supervisor. Decline it when your service
runs several workers, because each would start its own poller and only the first would win
the lock:

```python
loop.mount(app, host_ingresses=False)
```

The report's `hostIngresses` key states which way it went.

## Operations that mean something different when embedded

The router carries every operation the standalone service does — that is what stops the two
surfaces drifting — but two of them are about *the-loop's own processes* rather than about
work items, and inside your service they read strangely:

| Operation | Embedded meaning |
|-----------|------------------|
| `POST <prefix>/api/v1/restart` | schedules a detached `the-loop restart` for the **standalone** deployment this config describes. It does not restart your service. |
| `POST <prefix>/api/v1/daemons/control` | starts or stops the poller/receiver **as standalone daemons**, by pidfile. |

If neither belongs on your surface, gate them with a dependency of their own — a scope your
callers do not have, or a route registered before the mount that returns `404`.

## Without FastAPI

The capability namespaces need no web framework at all, so a Django, Flask or Celery
process can drive the-loop directly:

```python
loop = TheLoop(config_path="/etc/the-loop/cli-config.yaml")
for item in loop.attention.list():
    notify(item)
```

The HTTP seam is FastAPI-shaped, and that is the only part that is. A non-FastAPI service
that also wants the REST surface runs [the standalone service](/cli/service) beside itself.

## Checklist before you ship

- [ ] `dependencies=` names a real authorization check.
- [ ] `loop.check_environment()["ok"]` is asserted at startup
      ([environment](/sdk/environment)).
- [ ] `mcp_allowed_hosts` names the hosts you actually serve on (or `mcp=False`).
- [ ] `host_ingresses=False` if you run more than one worker.
- [ ] `restart` and `daemons/control` are gated, or knowingly exposed.
- [ ] The CLI config is deployed as a file your process can read, and its `state.root` is
      on a volume that survives a restart.
