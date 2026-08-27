# the-loop's control-plane service, as an image (issue-236).
#
# `Containerfile`, not `Dockerfile`: `localOrchestration.containerRuntime` is podman,
# which reads this name natively. Docker needs `-f Containerfile`, which the docs give.
#
#   podman build -t the-loop .
#   docker build -f Containerfile -t the-loop .
#   docker run --rm -p 127.0.0.1:4114:4114 -v the-loop-data:/data ghcr.io/madarauchiha-314/the-loop
#
# The image hosts the CONTROL PLANE and nothing else: no harness binary, no tmux, no git,
# so it serves the API and the dashboard's config editor but does not spawn agent sessions
# (docs/specs/issue-236/requirements.md § Out of scope). What it can do, it can do from a
# single `pip install` — the-loop ships no extras (PR #162).
#
# python:3.11-slim is the interpreter CI resolves and runs the suite under. Same version
# in both stages, so `--prefix=/install` lands on the site-packages path the runtime reads.

FROM python:3.11-slim-bookworm AS build

WORKDIR /src

# Only the package: a docs, UI or spec change leaves this layer cached.
COPY cli/ ./cli/

RUN pip install --no-cache-dir --prefix=/install ./cli


FROM python:3.11-slim-bookworm

LABEL org.opencontainers.image.title="the-loop" \
      org.opencontainers.image.description="the-loop's control-plane service: the /api/v1 surface, its MCP endpoint, and the config the dashboard edits." \
      org.opencontainers.image.source="https://github.com/MadaraUchiha-314/the-loop" \
      org.opencontainers.image.documentation="https://madarauchiha-314.github.io/the-loop/cli/container" \
      org.opencontainers.image.licenses="MIT"

# The built package and its dependencies. No compiler, no pip cache, no source tree.
COPY --from=build /install /usr/local

COPY container/cli-config.default.yaml /etc/the-loop/cli-config.default.yaml
COPY container/entrypoint.sh /usr/local/bin/the-loop-container

# Unprivileged, and owning the volume mountpoint so a NAMED volume inherits that
# ownership. A bind mount does not — run those with `--user "$(id -u):$(id -g)"`.
RUN chmod 0755 /usr/local/bin/the-loop-container \
    && useradd --system --create-home --home-dir /home/theloop --uid 10001 theloop \
    && mkdir -p /data \
    && chown theloop:theloop /data

USER theloop

# The config the entrypoint seeds and the dashboard writes, and the state root it names —
# both inside the volume, so `docker rm` costs nothing but the process.
ENV THE_LOOP_CLI_CONFIG=/data/cli-config.yaml \
    PYTHONUNBUFFERED=1
VOLUME /data
WORKDIR /data

EXPOSE 4114

# stdlib, so the image does not carry curl for one line. `/api/v1/health` is the service's
# own audit-exempt route: it is not written to the event log on every probe.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:4114/api/v1/health', timeout=4).status == 200 else 1)"]

ENTRYPOINT ["/usr/local/bin/the-loop-container"]
