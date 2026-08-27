---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#236"
phase: needs-review
status: in-progress
---

# Execution Log: the-loop service as a container image on GHCR

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-27 | — | Tier 4 (`human-approves-pr`): `.github/workflows/**` is a `sensitivePaths` entry and the work re-sites a security boundary. Brainstorming skipped — the issue names the artifact, the runtime and the client |
| requirements-definition | 2026-08-27 | | [`requirements.md`](requirements.md) — five requirements, four abuse cases, four things explicitly out of scope |
| design | 2026-08-27 | | [`design.md`](design.md) — four files, no change under `cli/the_loop/`; seven alternatives recorded |
| test-planning | 2026-08-27 | | [`testing-plan.md`](testing-plan.md) — twelve rows, seven applicable |
| tasks-breakdown | 2026-08-27 | | [`tasks.md`](tasks.md) — seven tasks |
| implementation | 2026-08-27 | | On `claude/github-issue-236-rvtmfa` |
| verification | 2026-08-27 | | [`evidence/verification.md`](evidence/verification.md) — every activity but the image build itself, which this environment cannot pull a base image for; the CI `container` job is that row |
| needs-review | 2026-08-27 | | PR raised; awaiting the owner |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#307](https://github.com/MadaraUchiha-314/the-loop/pull/307) | Tasks 1–7 (the whole work item) | open |

## What was delivered

`docker run -p 127.0.0.1:4114:4114 -v the-loop-data:/data ghcr.io/madarauchiha-314/the-loop`
is now a control-plane service — and **nothing under `cli/the_loop/` changed to make it
one**. Everything the image needs already existed: a foreground boot
(`python -m the_loop.api.serve`), a config path from `$THE_LOOP_CLI_CONFIG`, a
`POST /api/v1/config` that creates the file the dashboard writes, and a CORS default that
already admits the published dashboard's origin. What was missing was the packaging, and
one property those pieces were designed *against*.

- **A two-stage `Containerfile`** over `python:3.11-slim-bookworm` — the interpreter CI
  runs — installing `./cli` into a prefix and copying it into a runtime stage that carries
  no compiler, no source tree and no pip cache. Non-root (uid 10001), `/data` volume,
  `EXPOSE 4114`, a stdlib `HEALTHCHECK` so the image does not carry `curl` for one line.
  It hosts the control plane only: no harness binary, no `tmux`, no `git`, so it drives no
  agent sessions.
- **A container-shaped default config, seeded once.** Four keys — the current config
  `version`, `state.root: /data/state`, and the bind — checked in as
  `container/cli-config.default.yaml` rather than heredoc'd into the entrypoint, precisely
  so the test suite can put it through the *real* gates: the packaged schema,
  `assert_current`, `cors_config`, and the exposure guard's own `is_loopback` predicate. A
  container default the service would refuse to boot on is a red build. It is also
  validated by `scripts/validate_config.py` now, beside the other configs the-loop writes
  into other people's machines.
- **An entrypoint that seeds, warns, and gets out of the way.** It copies the defaults in
  only when nothing is there — a restart, and a newer image on the same volume, leave an
  operator's file byte-identical — prints the boundary, then `exec`s, so the service is
  PID 1 and takes `SIGTERM` itself. Arguments after the image name replace the service, so
  the image doubles as the CLI.
- **The release publishes it beside the wheel.** `publish-container` carries the same
  `needs: release` + `released == 'true'` gate as `publish-pypi`, checks out the release
  tag, builds `linux/amd64,linux/arm64`, tags `<version>`/`<major>.<minor>`/`<major>`/`latest`,
  and attests build provenance to the registry. CI builds **and runs** the image on every
  pull request, so the release path is never the first place it is exercised.

### The one decision worth your attention

The service refuses to bind anything but loopback unless `service.exposed: true`, because
it has no authentication and its API can spawn sessions. Inside a container that guard
protects nothing anybody wanted: a loopback bind in a network namespace is reachable by
**nothing at all**, not even by the host. So the image ships `host: 0.0.0.0` with
`exposed: true`, and the boundary becomes the publish flag —
[decision-102](../../decisions/decision-102.md).

What keeps that defensible is *where* it is written. It is configuration, in a file the
operator can read and the dashboard's Settings screen can change; no env var, no branch in
`serve.py`, no code path that behaves differently in a container. Every start prints the
boundary, unconditionally, because from inside the container `-p 127.0.0.1:4114:4114` and
`-p 4114:4114` are the same bind. And nothing else is widened: CORS keeps the shipped
allowlist, the ingresses stay off, the container is unprivileged, no credential is baked
in.

The alternatives are in [`design.md`](design.md)'s trade-off table — an env-var opt-in on
first run (the issue's own premise fails out of the box), `--network host` (Linux-only,
and a strictly larger grant than one published port), and detecting the container in code
(invisible where it matters).

## Verification

Full results in [`evidence/verification.md`](evidence/verification.md): **2713 passed /
2 skipped** (15 new tests, every one of them run red first), all four linters and gates
clean, 8 configs valid, and the entrypoint driven against a **live service** — seeded,
warned, bound `0.0.0.0:4114`, `/api/v1/health` → `{"status":"ok","version":"12.0.0"}`, a
dashboard-shaped `POST /api/v1/config` round trip that preserved the seeded file's
comments, the published origin's preflight echoed, state under `/data/state`, a clean
`SIGTERM` exit, and a restart that applied the saved `service.port` while leaving the
config byte-identical.

One activity was **not** executed: the image build itself. This environment's egress
policy denies Docker Hub (`403 to CONNECT`, `production.cloudfront.docker.com`), so no
base image can be pulled here. That row is the CI `container` job on this pull request —
which is the arrangement R4.5 asked for, not a workaround for it.

## Documentation

- [`docs/cli/container.md`](../../cli/container.md) — new page: the run line, what is in
  the image, the first start, the other ways to run it, building it, troubleshooting.
  Added to the CLI sidebar.
- [`docs/cli/installation.md`](../../cli/installation.md) — a third way to get the-loop,
  beside PyPI and the plugin.
- [`README.md`](https://github.com/MadaraUchiha-314/the-loop/blob/main/README.md) — the
  one-line container run under **The CLI**, and the reference link.
- [`docs/capabilities/distribution.md`](../../capabilities/distribution.md) — four new
  behaviour bullets (the image and its tags, what it does and does not host, seed-once,
  the container config and its cleared guard) and a history row.
- [`docs/capabilities/release-publishing.md`](../../capabilities/release-publishing.md) —
  the publish job and the PR-time build gate, plus a history row.
- [`docs/capabilities/capabilities.md`](../../capabilities/capabilities.md) — both index
  summaries.
- [`docs/decisions/decision-102.md`](../../decisions/decision-102.md) + the index row.

## Decisions and open questions

[decision-102](../../decisions/decision-102.md) is the one record raised, and it is the
review's centre of gravity: it re-sites a security boundary that decision-059 placed on
the bind address.

Two things for the owner at the gate:

1. **The GHCR package starts private.** The first `publish-container` run creates the
   package private, and only the owner can make it public — a one-time click in the
   package settings that no workflow can do. Until then, the `docker pull` lines in the
   docs need a `docker login ghcr.io`.
2. **The image is control-plane-only, on purpose.** It cannot spawn sessions, because that
   needs the harness binary, `tmux`, `git` and the operator's credentials — a different
   threat model, and a different image. If you want that one too, it is a work item, not a
   flag on this one.

## Progress entries

### 2026-08-27 — spec chain, implementation, verification

- **Phase:** needs-review
- **Did:** wrote the four spec artifacts; implemented the container config, the entrypoint,
  the `Containerfile` and `.dockerignore`, the CI build-and-run job and the GHCR publish
  job; added 15 tests (red first); updated six docs and raised decision-102.
- **Checkpoint/tests:** `make lint` · `make format-check` · `make typecheck` ·
  `make validate` · `make test` — all green (2713 passed, 2 skipped). The entrypoint was
  additionally driven against a live service; see the evidence file.
- **Next:** the owner's review at the PR gate. The `container` CI job's result on the PR
  is the T4 row of the testing plan.
- **Blockers:** none. One activity deferred to CI with its reason recorded.

## Verification results

> This work item has a `testing-plan.md`, so the `verification` node recorded its results
> there. This section stays as the template left it.

| What was verified | Command | Outcome | Evidence |
|-------------------|---------|---------|----------|
|                   |         | pass \| fail | link or `evidence/<file>` |
