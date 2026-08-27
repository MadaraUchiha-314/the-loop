# Running in a container

One image, one command, a control-plane service — no Python install, no config file, no
checkout:

```bash
docker run -d --name the-loop \
  -p 127.0.0.1:4114:4114 \
  -v the-loop-data:/data \
  ghcr.io/madarauchiha-314/the-loop:latest
```

Then open the [control-plane dashboard](https://madarauchiha-314.github.io/the-loop/ui/),
point it at `http://127.0.0.1:4114` on the **Settings** screen, and configure the rest
from there. Nothing else to install: the page is served from GitHub Pages and the
container's shipped CORS allowlist already admits that origin
([decision-077](/decisions/decision-077)).

::: warning The publish flag is the boundary
The service carries **no authentication of its own** — that belongs to a gateway
([decision-059](/decisions/decision-059)) — and its API can spawn harness sessions. Inside
a container a loopback bind is reachable by nothing at all, so the image binds every
interface and `-p 127.0.0.1:4114:4114` is what keeps it to your machine. `-p 4114:4114`
puts an unauthenticated control plane on every network the host is on; do that only behind
an auth-terminating gateway. See [decision-102](/decisions/decision-102).
:::

## What is in it

| | |
|---|---|
| Image | `ghcr.io/madarauchiha-314/the-loop` |
| Tags | `latest`, `<major>`, `<major>.<minor>`, `<version>` — the same version as `the-loopy-one` on PyPI |
| Platforms | `linux/amd64`, `linux/arm64` |
| Runs | `python -m the_loop.api.serve` as PID 1, unprivileged (uid 10001) |
| Serves | [`/api/v1`](/cli/service), `/api/docs` and `/mcp` on port **4114** |
| Volume | `/data` — the config it seeded and everything it generates |
| Provenance | a signed [build attestation](https://github.com/MadaraUchiha-314/the-loop/attestations), pushed to the registry |

It hosts the **control plane** and only that. There is no harness binary, no `tmux` and no
`git` in the image, so it does not spawn agent sessions — for that, run the
[CLI](/cli/installation) on a machine that has them.

## The first start

The entrypoint seeds `/data/cli-config.yaml` from the image's container defaults, prints
the boundary warning, and hands the process over to the service:

```console
$ docker logs the-loop
the-loop: seeded /data/cli-config.yaml from the container defaults
the-loop: the service binds every interface INSIDE this container, so the boundary is the
          port you publish. Loopback of the host machine:  -p 127.0.0.1:4114:4114
          Anything wider needs an auth-terminating gateway in front of it.
INFO:     Uvicorn running on http://0.0.0.0:4114 (Press CTRL+C to quit)
```

The seeded file is four keys, and every option **not** in it takes the same default a
`pip install the-loopy-one` would:

```yaml
version: "0.6.0"
state:
  root: /data/state       # the event log, the work-item records, the session handles
service:
  host: 0.0.0.0           # a loopback bind in a container is reachable by nothing
  exposed: true           # so the guard is cleared here, where you can read it
```

From then on that file is **yours**. Edit it in place, mount your own over it, or change
it from the dashboard's Settings screen — the entrypoint never overwrites an existing
config, so a restart, and a newer image on the same volume, both leave it exactly as you
left it.

Keys that only take effect on a restart — `service.host`, `service.port`,
`service.exposed`, `service.cors`, `service.mcp`, `service.hostIngresses` — need
`docker restart the-loop`, not a rebuild. The dashboard says which ones those are when
you save.

## Other ways to run it

```bash
# your own config, mounted read-only over the seeded one
docker run -p 127.0.0.1:4114:4114 \
  -v ~/.the-loop/cli-config.yaml:/data/cli-config.yaml:ro \
  -v the-loop-data:/data \
  ghcr.io/madarauchiha-314/the-loop

# a bind-mounted data directory: the container is unprivileged, so give it your uid
docker run -p 127.0.0.1:4114:4114 \
  --user "$(id -u):$(id -g)" -v "$PWD/the-loop-data:/data" \
  ghcr.io/madarauchiha-314/the-loop

# the image doubles as the CLI — any argument replaces the service
docker run --rm ghcr.io/madarauchiha-314/the-loop the-loop --version
docker run --rm -v the-loop-data:/data ghcr.io/madarauchiha-314/the-loop \
  the-loop events --limit 20

# somewhere else on the network: bring the port to the browser's machine
ssh -L 4114:127.0.0.1:4114 workstation
```

## Building it yourself

The image is built from this repository's [`Containerfile`](https://github.com/MadaraUchiha-314/the-loop/blob/main/Containerfile),
and CI builds and runs it on every pull request, so `main` is always buildable:

```bash
podman build -t the-loop .              # podman reads Containerfile natively
docker build -f Containerfile -t the-loop .
```

## Troubleshooting

| What you see | What it is |
|---|---|
| `curl: (7) Failed to connect` on the host | the port was not published, or was published to a different address |
| The container exits immediately, `refusing to bind …` | `service.exposed` was set back to `false` in your config while `host` stayed non-loopback — inside a container that pair cannot serve anybody |
| The container exits immediately, naming `/the-loop:upgrade-the-loop` | the mounted config is older than the current schema version; run [`the-loop migrate-config`](/cli/commands/migrate-config) against it |
| The dashboard shows "failed to fetch" | the page's origin is not in `service.cors.allowOrigins`, or the service is not on this machine — see [the dashboard's README](https://github.com/MadaraUchiha-314/the-loop/blob/main/ui/README.md) |
| `Permission denied` seeding the config | a bind-mounted `/data` owned by another user; add `--user "$(id -u):$(id -g)"` |
| `docker pull` asks for credentials | the GHCR package is private until the first publish is made public |

## See also

- [The control-plane service](/cli/service) — what it exposes and how it is guarded
- [Installing the CLI](/cli/installation) — the other two ways to get the-loop
- [Service options](/config/cli/service-options) — every key the seeded config leaves at
  its default
