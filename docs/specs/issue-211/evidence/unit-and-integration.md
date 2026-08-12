# Evidence: unit, integration and abuse-case tests (T1, T2, T8)

Captured 2026-08-12 on the work item's branch. Nothing here contains a credential,
hostname or path beyond this checkout.

## The two new test files

```console
$ uv run --project cli python -m pytest cli/tests/test_api_cors.py cli/tests/test_api_cors_integration.py
============================= test session starts ==============================
platform linux -- Python 3.11.15, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/user/the-loop/cli
configfile: pyproject.toml
plugins: anyio-4.14.2
collected 19 items

cli/tests/test_api_cors.py ........                                      [ 42%]
cli/tests/test_api_cors_integration.py ...........                       [100%]

============================== 19 passed in 2.25s ==============================
```

Eight resolution/validation cases (T1) and eleven behavioural ones (T2), of which six are
the negative tests T8 names: unlisted origin (three parametrised cases, including the
suffix lookalike and the wrong scheme), the wildcard+credentials refusal at both the
config layer and `serve.main`, the declined private-network preflight, and the MCP
transport's own origin check.

## The headers a browser actually receives

Driving the assembled app with the shipped defaults — no `service.cors` block configured:

```console
$ uv run --project cli python -c "<TestClient, see below>"
PREFLIGHT 200
  vary: Origin
  access-control-allow-methods: GET, POST, OPTIONS
  access-control-max-age: 600
  access-control-allow-headers: Accept, Accept-Language, Content-Language, Content-Type
  access-control-allow-origin: https://madarauchiha-314.github.io
  access-control-allow-private-network: true
  content-length: 2
  content-type: text/plain; charset=utf-8

GET health 200 {'content-length': '33', 'content-type': 'application/json',
                'access-control-allow-origin': 'https://madarauchiha-314.github.io',
                'vary': 'Origin'}

GET health (evil) 200 {'content-length': '33', 'content-type': 'application/json'}
```

The script, for reproduction:

```python
from fastapi.testclient import TestClient
from the_loop.api.app import create_app

c = TestClient(create_app({}))
r = c.options("/api/v1/work-items", headers={
    "Origin": "https://madarauchiha-314.github.io",
    "Access-Control-Request-Method": "GET",
    "Access-Control-Request-Private-Network": "true",
})
print("PREFLIGHT", r.status_code)
for k, v in r.headers.items():
    print(" ", k + ":", v)
print("GET health", *[c.get("/api/v1/health", headers={"Origin": o}).headers
                      for o in ("https://madarauchiha-314.github.io", "https://evil.example.com")])
```

Three things to read off it:

1. The allowed origin is echoed **by name**, never as `*`, and `Vary: Origin` comes with
   it so a cache cannot serve one origin's response to another.
2. `Access-Control-Allow-Private-Network: true` is present — this is the header that lets
   a page on `https://madarauchiha-314.github.io` reach `http://127.0.0.1:4114` in
   Chromium at all.
3. The disallowed origin gets a normal 200 with **no** `Access-Control-Allow-Origin`. The
   service does not pretend to fail; the browser discards the response. That is the
   correct shape — CORS is a read permission, not an access control.

`Access-Control-Allow-Headers` lists more than the two configured because Starlette adds
the browser's own safelist (`Accept-Language`, `Content-Language`) to whatever is
configured.
