---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#236"
status: draft
approvedBy: []
overrides: {}
---

# Testing plan: the-loop service as a container image on GHCR

> Derived from `requirements.md` and `design.md`. Nothing under `cli/the_loop/` changes,
> so this plan proves three things instead: that the **seeded config** is one the real
> service accepts, that the **entrypoint** seeds it exactly once and hands the process
> over, and that the **built image** actually serves.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `container/cli-config.default.yaml` against the packaged schema, the migration gate, the exposure guard's own predicate, `cors_config` and `layout_from_config` | `cd cli && uv run python -m pytest tests/test_container.py` |
| T2 | Integration (scenario) | yes | `container/entrypoint.sh` executed by `sh`: seeds when absent, never overwrites, warns every start, execs the given command | `cd cli && uv run python -m pytest tests/test_container_integration.py` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — no route, request or response shape changes; `test_api_contract_parity.py` already guards the served surface | | |
| T4 | End-to-end | yes | the built image, run: `/api/v1/health` answers `ok`, the config is seeded at `/data/cli-config.yaml`, the banner is on stderr | `.github/workflows/ci.yml` job `container` |
| T5 | UI / visual | n/a — no product UI changes; the dashboard is an unmodified client | | |
| T6 | Snapshot | n/a — no rendered output to freeze | | |
| T7 | Performance / load | n/a — one process, one operator; the only timing claim (cold boot < 30s) is asserted by T4's wait loop | | |
| T8 | Security / abuse case | yes | one negative test per boundary in `design.md` § Security design: the seed opens no ingress, widens no CORS, carries no non-default port; a config the service must refuse still gets refused; the warning is unconditional | `cd cli && uv run python -m pytest tests/test_container.py tests/test_container_integration.py -k "security or refus or warn or ingress or cors"` |
| T9 | Accessibility | n/a — no user interface | | |
| T10 | Migration / upgrade | yes | an existing `/data/cli-config.yaml` survives a restart byte-identical (the image-upgrade path: new image, old volume) | T2's `test_existing_config_is_never_overwritten` |
| T11 | Manual exploratory | yes | the hosted dashboard, pointed at a locally running container, reads and saves the config | recorded in `evidence/verification.md` |
| T12 | Static analysis / lint | yes | ruff + pyright over the new tests, markdownlint over every new doc, `scripts/validate_config.py` unchanged and green | `make check` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R2.3, R2.4 | the seeded config validates against `cli-config.schema.json` and carries `CURRENT_CONFIG_VERSION` |
| T1 | R1.3 | `service_config(seed)` yields a non-loopback host **and** `exposed: true` — the pair `serve.main` admits |
| T1 | R3.1, R5.2 | the seed adds no `cors`, no `webhooks`, no `polling`, no `standingSessions` key |
| T2 | R2.1 | `Scenario: a container with no config is given the shipped container defaults` |
| T2 | R2.2, R2.5 | `Scenario: an operator's config survives a restart untouched` |
| T2 | R1.4 | `Scenario: a command passed to the image replaces the service` |
| T2 | R1.1 | `Scenario: no arguments boots the control-plane service in the foreground` |
| T2 | abuse case 1 | `Scenario: every start states where the network boundary now is` |
| T4 | R1.1, R2.1, R4.5 | the image is built and run; `/api/v1/health` returns `{"status":"ok"}` and `/data/cli-config.yaml` exists |
| T8 | abuse cases 1–3 | the boundary table in `design.md` § Security design, row by row |
| T10 | R2.2 | a config written before the restart is byte-identical after it |

## Verification environment

- **Repositories:** this repo only.
- **Services / containers:** T1/T2/T8/T12 need **none** — the entrypoint is driven with
  `sh` against a temp directory. T4 needs a container runtime and runs in CI
  (`docker buildx`); locally the same steps run under `podman build -t the-loop:dev .`
  (`localOrchestration.containerRuntime`).
- **Fixtures & data:** none beyond the checked-in `container/cli-config.default.yaml`.
- **Credentials:** none for T1–T3 and T12. The publish path uses `GITHUB_TOKEN`
  (`packages: write`) — by reference only, minted per run, never stored.
- **Bring-up:** `uv sync` · **Tear-down:** none.
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T8, T12 | command output: counts, duration, pass/fail | `verification.md` |
| T4 | the CI job's steps reproduced locally where a runtime exists, or the reason it could not be | `verification.md` |
| T11 | what was driven from the dashboard and what happened | `verification.md` |

## Verification activities

- [x] T1 — `cd cli && uv run python -m pytest tests/test_container.py -q`
- [x] T2 — `cd cli && uv run python -m pytest tests/test_container_integration.py -q`
- [x] T8 — the security rows above, run as part of T1/T2
- [x] T10 — `test_an_operators_config_survives_a_restart_untouched`, and the same
  property observed against the live service (T4a)
- [x] T12 — `make lint`, `make format-check`, `make typecheck`, `make validate`, `make test`
- [ ] T4 — build the image and `GET /api/v1/health` from it — **not executed here**: this
  session's egress policy denies Docker Hub, so no base image can be pulled. Proven by the
  `container` job in CI on this pull request (which is why R4.5 put it there)
- [x] T4a — the entrypoint booting the **real service**, seeding, serving, and exiting on
  `SIGTERM`: everything the image wraps, minus the image
- [x] T11 — the config surface the dashboard drives (`GET`/`POST /api/v1/config`, the
  preflight from the published origin), against the seeded container config

## Verification results

All output in [`evidence/verification.md`](evidence/verification.md).

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | `cd cli && uv run python -m pytest tests/test_container.py -q` | pass — 9 passed (9 errored before the file existed) | [`evidence/verification.md`](evidence/verification.md) § T1 |
| T2, T10 | `cd cli && uv run python -m pytest tests/test_container_integration.py -q` | pass — 6 passed, 1 skipped (the not-writable case skips itself for a root user) | § T2 / T10 |
| T8 | the seven security rows, run as part of T1/T2 | pass — 7/7 | § T8 |
| T12 | `make lint` · `make format-check` · `make typecheck` · `make validate` · `make test` | pass — 0 lint errors over 907 markdown files, 261 formatted, 0 type errors, 8 configs valid, **2713 passed / 2 skipped** | § T12 |
| T4a | `sh container/entrypoint.sh` against a live `the_loop.api.serve` | pass — seeded, warned, bound `0.0.0.0:4114`, `/api/v1/health` → `{"status":"ok","version":"12.0.0"}`, clean `SIGTERM` exit in ~3s | § T4a |
| T11 | `GET`/`POST /api/v1/config` and the dashboard-origin preflight | pass — read, wrote (`restartRequired: ["service.port"]`), comments preserved by the splice, `access-control-allow-origin` echoed, state under `/data/state` | § T11 |
| T4 | `docker build -f Containerfile …` | **not executed** — egress policy denies Docker Hub (`403 to CONNECT`, `production.cloudfront.docker.com`) | § T4 |

**Not executed:** T4 (build and run the image) — the container runtime in this environment
cannot pull a base image. Not replanned and not escalated: the pull request's own
`container` CI job performs exactly this activity on a runner that can, which is the
arrangement R4.5 asked for. The reviewer reads its result on the PR; everything the image
wraps was proved locally as T4a and T11.

## Review comments
