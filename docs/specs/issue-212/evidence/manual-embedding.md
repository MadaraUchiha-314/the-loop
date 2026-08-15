# Evidence: the documented quickstart, run as written (issue-212)

Testing-plan row **T13**. R6.2 asks that a documented example be complete enough to run. This
is that example — the code block at the top of
[`docs/sdk/embedding.md`](../../../sdk/embedding.md), pasted into a file, served with a real
`uvicorn` (not `TestClient`), and exercised with `curl`.

## The application

```python
"""The docs/sdk/embedding.md quickstart, pasted as written."""

import logging

from fastapi import Depends, FastAPI, HTTPException, Request

from the_loop.sdk import TheLoop

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sample")

EXPECTED_KEY = "s3cret"

loop = TheLoop(config_path="cli-config.yaml")


def verify_caller(request: Request) -> None:
    if request.headers.get("x-api-key") != EXPECTED_KEY:
        raise HTTPException(status_code=401, detail="unauthorized")


app = FastAPI(title="platform-api")


@app.get("/orders")
def orders():
    return [{"id": 1}]


report = loop.mount(
    app,
    prefix="/the-loop",
    dependencies=[Depends(verify_caller)],
    mcp_allowed_hosts=["127.0.0.1:8099", "127.0.0.1"],
)
logger.info("the-loop mounted: %s", report)
logger.info("environment: %s", loop.check_environment()["ok"])
```

with a two-key CLI config beside it:

```yaml
state:
  root: ./.the-loop
service:
  hostIngresses: false
```

## Boot

```console
$ uvicorn sample:app --host 127.0.0.1 --port 8099
INFO:the-loop.sdk:the-loop mounted: {'prefix': '/the-loop', 'operations': 29, 'mcp': {'mounted': True, 'path': '/the-loop/mcp'}, 'lifespan': 'wrapped', 'hostIngresses': False, 'dependencies': 1}
INFO:sample:the-loop mounted: {'prefix': '/the-loop', 'operations': 29, 'mcp': {'mounted': True, 'path': '/the-loop/mcp'}, 'lifespan': 'wrapped', 'hostIngresses': False, 'dependencies': 1}
INFO:sample:environment: True
INFO:     Started server process [28531]
INFO:     Waiting for application startup.
INFO:mcp.server.streamable_http_manager:StreamableHTTP session manager started
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8099 (Press CTRL+C to quit)
```

`StreamableHTTP session manager started` is the line that matters: `mount()` wrapped the
lifespan, so the MCP session manager is running before the first request — the failure D3
exists to prevent.

## Exercised

```console
$ curl -s -o /dev/null -w "%{http_code}\n" $B/orders
200

$ curl -s $B/the-loop/api/v1/health
{"detail":"unauthorized"}                                             # HTTP 401

$ curl -s -H "x-api-key: s3cret" $B/the-loop/api/v1/health
{"status":"ok","version":"10.0.0"}                                    # HTTP 200

$ curl -s -H "x-api-key: s3cret" $B/the-loop/api/v1/work-items
[]                                                                    # HTTP 200

$ curl -s -H "x-api-key: s3cret" "$B/the-loop/api/v1/work-items/one?ref=github:octo/repo%23404"
{"detail":"no record for work item github:octo/repo#404"}             # HTTP 404

$ curl -s -H "x-api-key: s3cret" "$B/the-loop/api/v1/work-items/one?ref=nope"
{"detail":"invalid work-item ref 'nope'; expected <provider>:[<host>/]<owner>/<repo>#<number> …"}
                                                                      # HTTP 400

$ curl -s -X POST $B/the-loop/mcp -H "x-api-key: s3cret" \
    -H 'Accept: application/json, text/event-stream' -H 'Content-Type: application/json' \
    -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"1"}}}'
event: message
data: {"jsonrpc":"2.0","id":1,"result":{"capabilities":{…},"instructions":"Inspect and steer
the-loop's work items: read portable records, evaluate process-graph gates, control harness
sessions and the ingress daemons, and query the structured event log.…
                                                                      # HTTP 200

$ curl -s $B/openapi.json | python3 -c "…"
/orders present: True · paths under /the-loop: 28
```

Seven facts, in order: the host's own route is unaffected; the-loop is closed without the
key; open with it; a `LookupError` from core becomes a 404 with no exception handler
registered by the host; a `ValueError` becomes a 400; the MCP endpoint answers at
`<prefix>/mcp` with no redirect; and one OpenAPI document describes both surfaces.

The 28-vs-29 gap is `/api/v1/config` carrying both `GET` and `POST` on one path.

Redaction: `s3cret` is a literal invented for this run and authenticates nothing;
`127.0.0.1:8099` is loopback. Absolute scratch paths are rewritten repository-relative above.
