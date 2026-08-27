# Verification evidence — issue-236

Every command below was run from the repository root (or `cli/`, where noted) on the
implementation branch. Output is verbatim; nothing here contains a credential, a token or
a hostname that is not already public.

## T1 — the container's default config, against the code that judges it

```console
$ cd cli && uv run python -m pytest tests/test_container.py -q
.........                                                                [100%]
9 passed in 0.02s
```

Written **red first**: with `container/` present but empty, all nine errored on the absent
file.

```console
$ cd cli && uv run python -m pytest tests/test_container.py -q   # before container/cli-config.default.yaml existed
ERROR tests/test_container.py::test_seed_clears_the_exposure_guard_explicitly
ERROR tests/test_container.py::test_seed_keeps_the_package_default_port - Fil...
ERROR tests/test_container.py::test_state_root_is_inside_the_volume - FileNot...
ERROR tests/test_container.py::test_seed_widens_no_cors_value - FileNotFoundE...
ERROR tests/test_container.py::test_seed_opens_no_ingress - FileNotFoundError...
ERROR tests/test_container.py::test_seed_is_only_the_keys_the_container_has_an_opinion_about
ERROR tests/test_container.py::test_seed_explains_the_two_lines_that_need_explaining
9 errors in 0.20s
```

## T2 / T10 — the entrypoint, executed

```console
$ cd cli && uv run python -m pytest tests/test_container_integration.py -q
......s                                                                  [100%]
6 passed, 1 skipped in 0.10s
```

Red first, the same way: six failures against the absent script. The skip is
`test_a_data_directory_it_cannot_write_fails_the_start`, which skips itself when the
running user can write to a mode-555 directory — this session runs as root, and CI's
runner does too.

## T8 — the security rows

Part of T1/T2 above, and each row of `design.md` § Security design has its test:

| Boundary | Test | Result |
|---|---|---|
| The seed opens no ingress | `test_seed_opens_no_ingress` | pass |
| The seed widens no CORS value | `test_seed_widens_no_cors_value` | pass |
| The seed clears the exposure guard **explicitly**, using `serve.py`'s own predicate | `test_seed_clears_the_exposure_guard_explicitly` | pass |
| The seed carries no key the container has no opinion about | `test_seed_is_only_the_keys_the_container_has_an_opinion_about` | pass |
| A config the service must refuse still gets refused | `assert_current` + `cors_config` run over the seed in T1; both guards are the package's own, untouched by this work item | pass |
| The boundary warning is unconditional | `test_every_start_states_where_the_network_boundary_now_is` (asserted on a seeding start **and** a subsequent one) | pass |
| An operator's file is never overwritten | `test_an_operators_config_survives_a_restart_untouched` | pass |

## T12 — the repository's own gates

```console
$ make lint
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Linting: 907 file(s)
Summary: 0 error(s)

$ make format-check
261 files already formatted

$ make typecheck
0 errors, 0 warnings, 0 informations

$ make validate
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
VALID   container/cli-config.default.yaml

$ make test
2713 passed, 2 skipped in 125.94s (0:02:05)
```

`container/cli-config.default.yaml` is now one of the files
`scripts/validate_config.py` (and therefore the pre-commit hook and CI) validates.

## T4 — the built image

**Executed by the `container` job on [PR #306](https://github.com/MadaraUchiha-314/the-loop/pull/306)** —
green, in 56s. The image built, ran, served, and stopped:

```console
the-loop: seeded /data/cli-config.yaml from the container defaults
the-loop: the service binds every interface INSIDE this container, so the boundary is the
          port you publish. Loopback of the host machine:  -p 127.0.0.1:4114:4114
          Anything wider needs an auth-terminating gateway in front of it.
INFO:     Started server process [1]
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:4114 (Press CTRL+C to quit)
INFO:     172.17.0.1:52990 - "GET /api/v1/health HTTP/1.1" 200 OK
INFO:     Shutting down
INFO:     Application shutdown complete.
INFO:     Finished server process [1]
```

Four assertions are in those twelve lines, and the third is the one no local run could
make: **`Started server process [1]`** — the service is PID 1, so `docker stop` reached
uvicorn rather than a shell, and the job's `test "$(docker inspect -f
'{{.State.ExitCode}}' …)" = "0"` passed instead of timing out to a 137. The other three:
the config was seeded into `/data`, the boundary banner was printed, and
`/api/v1/health` answered `200`. The steps between them — `docker exec … grep -q 'exposed:
true' /data/cli-config.yaml`, the banner grep, and `docker run --rm the-loop:ci the-loop
--version` — all passed, or the job would have failed on `set -euo pipefail`.

The job also surfaced one thing worth fixing, and it was fixed: `docker stop --time` is
deprecated in favour of `--timeout`, which the workflow now uses.

### Why it was not run in this session

This session's egress
policy denies Docker Hub, so no base image can be pulled:

```console
$ docker build -f Containerfile -t the-loop:dev .
ERROR: failed to build: failed to solve: python:3.11-slim-bookworm: failed to resolve
source metadata for docker.io/library/python:3.11-slim-bookworm: … Forbidden

$ curl -sS "$HTTPS_PROXY/__agentproxy/status"
"recentRelayFailures": [{ "kind": "connect_rejected",
  "detail": "gateway answered 403 to CONNECT (policy denial or upstream failure)",
  "host": "production.cloudfront.docker.com:443" }]
```

This is exactly why the work item put the build in **CI** rather than only on the release
path (R4.5) — and why the row above is a record rather than a gap. What was additionally
proved locally is everything the image wraps: see T4a.

## T4a — the entrypoint booting the real service (the image's contents, minus the image)

The entrypoint was run against a live `python -m the_loop.api.serve`, seeding into `/data`
exactly as the container does:

```console
$ THE_LOOP_CONTAINER_DEFAULT_CONFIG=container/cli-config.default.yaml \
    sh container/entrypoint.sh
the-loop: seeded /data/cli-config.yaml from the container defaults
the-loop: the service binds every interface INSIDE this container, so the boundary is the
          port you publish. Loopback of the host machine:  -p 127.0.0.1:4114:4114
          Anything wider needs an auth-terminating gateway in front of it.
INFO:     Started server process [5193]
StreamableHTTP session manager started
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:4114 (Press CTRL+C to quit)

$ curl -sS http://127.0.0.1:4114/api/v1/health
{"status":"ok","version":"12.0.0"}
```

The bind is `0.0.0.0` — the exposure guard admitted the seeded pair rather than refusing
it, which is the assertion that matters most (R1.3).

## T11 — the config surface the dashboard drives

The dashboard's Settings screen is a client of three calls; all three were exercised
directly against the seeded container config.

```console
$ curl -sS http://127.0.0.1:4114/api/v1/config
{"path":"/data/cli-config.yaml","exists":true,"version":"0.6.0",
 "config":{"version":"0.6.0","state":{"root":"/data/state"},
           "service":{"host":"0.0.0.0","exposed":true}}}

$ curl -sS -X POST http://127.0.0.1:4114/api/v1/config \
    -H 'Content-Type: application/json' -d '{"patch": {"service": {"port": 4200}}}'
{"path":"/data/cli-config.yaml","exists":true,"changed":["service.port"],
 "restartRequired":["service.port"],"written":true,
 "config":{"version":"0.6.0","state":{"root":"/data/state"},
           "service":{"host":"0.0.0.0","exposed":true,"port":4200}}}
```

The write is a splice, so the seeded file's comments — including the two explaining the
cleared guard — are still there afterwards:

```console
$ tail -6 /data/cli-config.yaml
  #     -p 127.0.0.1:4114:4114        reachable from that machine only
  #     -p 4114:4114                  reachable from every network that machine is on —
  #                                   only ever behind an auth-terminating gateway
  host: 0.0.0.0
  exposed: true
  port: 4200
```

The published dashboard's origin is admitted by the seeded config with nothing added to
it (R3.1):

```console
$ curl -sS -i -X OPTIONS http://127.0.0.1:4114/api/v1/config \
    -H 'Origin: https://madarauchiha-314.github.io' \
    -H 'Access-Control-Request-Method: POST' -H 'Access-Control-Request-Headers: content-type'
HTTP/1.1 200 OK
access-control-allow-methods: GET, POST, OPTIONS
access-control-allow-origin: https://madarauchiha-314.github.io
```

State landed in the volume, not the writable layer (R2.4):

```console
$ find /data/state -type f
/data/state/logs/events.jsonl
/data/state/local/service.pid
```

### The restart-required loop, end to end (R3.3, R2.2)

`SIGTERM` to the entrypoint shut the service down cleanly, in about three seconds — no
kill timeout, no orphaned uvicorn:

```console
INFO:     Waiting for application shutdown.
StreamableHTTP session manager shutting down
INFO:     Application shutdown complete.
INFO:     Finished server process [5193]
exited after ~3s
```

Started again on the same `/data` — the second start seeds nothing, applies the saved
`service.port`, and leaves the file byte-identical:

```console
$ head -4 serve2.err
the-loop: the service binds every interface INSIDE this container, so the boundary is the
          port you publish. Loopback of the host machine:  -p 127.0.0.1:4114:4114
          Anything wider needs an auth-terminating gateway in front of it.
INFO:     Started server process [5232]

$ grep -o "http://0.0.0.0:[0-9]*" serve2.err | head -1
http://0.0.0.0:4200

$ curl -sS http://127.0.0.1:4200/api/v1/health
{"status":"ok","version":"12.0.0"}

$ md5sum -c before.md5
/data/cli-config.yaml: OK
```

No `seeded` line on the second start, which is `test_an_operators_config_survives_a_restart_untouched`
observed against the real service rather than a stub.
