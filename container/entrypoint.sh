#!/bin/sh
# The container's PID 1 (issue-236). Three jobs, in order: give the service a config to
# read, say where the network boundary went, then get out of the way.
#
# Both paths are `:=` defaults rather than hardcoded, which is what lets the test suite
# run this script outside a container (cli/tests/test_container_integration.py) — the
# image supplies the values, nothing else changes.
set -eu

: "${THE_LOOP_CLI_CONFIG:=/data/cli-config.yaml}"
: "${THE_LOOP_CONTAINER_DEFAULT_CONFIG:=/etc/the-loop/cli-config.default.yaml}"
export THE_LOOP_CLI_CONFIG

# Seed once, and only once: from here on the file is the operator's — hand-edited, or
# written by the dashboard's Settings screen. A newer image on the same volume finds it
# and leaves it alone, so an upgrade never resets a configuration.
if [ ! -e "$THE_LOOP_CLI_CONFIG" ]; then
    mkdir -p "$(dirname "$THE_LOOP_CLI_CONFIG")"
    cp "$THE_LOOP_CONTAINER_DEFAULT_CONFIG" "$THE_LOOP_CLI_CONFIG"
    echo "the-loop: seeded $THE_LOOP_CLI_CONFIG from the container defaults" >&2
fi

# Unconditional, because the container cannot tell the two cases apart: from in here,
# `-p 127.0.0.1:4114:4114` and `-p 4114:4114` are the same bind. The service has no
# authentication of its own and its API can spawn harness sessions, so who can reach the
# published port is the whole of the boundary (decision-102).
cat >&2 <<'BANNER'
the-loop: the service binds every interface INSIDE this container, so the boundary is the
          port you publish. Loopback of the host machine:  -p 127.0.0.1:4114:4114
          Anything wider needs an auth-terminating gateway in front of it.
BANNER

# `exec` in both branches: the service becomes PID 1 and takes the runtime's SIGTERM
# directly, instead of a shell swallowing it while uvicorn keeps serving.
if [ "$#" -eq 0 ]; then
    exec python -m the_loop.api.serve
fi

exec "$@"
