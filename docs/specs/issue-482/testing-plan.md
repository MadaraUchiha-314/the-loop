---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#482"
status: in-review
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: spawned sessions never receive a secret

> Derived from [`requirements.md`](requirements.md) and [`design.md`](design.md). The
> results are in [`evidence/verification.md`](evidence/verification.md).

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit (boundary) | yes | `credential_names` finds every `*TokenEnv`/`*SecretEnv` string and list at any depth plus the defaults; `passthrough_names` drops a credential with a warning naming it; `session_environment` takes a passthrough value from the file first, then the process, and puts every other file name and every credential in `remove` | `cli/tests/test_session_environment.py` |
| T2 | Unit (argv) | yes | a spawn and a respawn with an env file declaring `GH_TOKEN` carry no `GH_TOKEN=` in any argv element; `-e` names only the three plus passthrough; the harness is prefixed `env -u GH_TOKEN …`; with no config the argv is unchanged | `cli/tests/test_tmux_runner.py` |
| T3 | Unit (tmux environment) | yes | the tmux subprocess is started with the `remove` names absent from its environment | same |
| T4 | Integration (real tmux) | yes, where tmux ≥ 3.2 is installed | a real spawn from a process holding `GH_TOKEN=dummy-secret-value`: the tmux server's command line (`ps`) and the pane's environment (`/proc/<pid>/environ`) do not contain the value; `THE_LOOP_WORK_ITEM` is present | `cli/tests/test_session_secrets_integration.py` |
| T5 | Unit (routing) | yes | in a daemon-spawned session with no service, `harness_routed` raises `ServiceUnavailable` and never calls `local`; outside one it falls back with the note, as before; the stale-service branch likewise | `cli/tests/test_github_verbs_cli.py` |
| T6 | Unit (ask route) | yes | `the-loop ask` posts through `/sessions/ask` when a service answers; the facade passes the CLI's actor through; in-process otherwise (outside a daemon session) | `cli/tests/test_ask_route.py` |
| T7 | Contract | yes | the served OpenAPI surface matches the authored contract with `askSession` added | `cli/tests/test_api_contract_parity.py` |
| T8 | Integration (drift and restart) | yes | a pane holding a removed name is `stale`; one holding only the three is `fresh`; `restart` relaunches with an env file that declares only credentials | `cli/tests/test_sessions_restart_integration.py` |
| T9 | Config | yes | the schema accepts `env.sessionPassthrough` and rejects a non-name; `make validate` passes | `scripts/validate_config.py`, schema tests |
| T10 | Regression | yes | ruff, ruff format, pyright, the full CLI suite, markdownlint | repository checks |
| T11 | Security | yes (review) | the abuse cases A1–A5 each map to a passing test | `evidence/security-review.md` |
| T12 | UI / accessibility / performance / migration | n/a | no UI; one dict walk per spawn; the config key is additive and needs no migration | |

## Requirement trace

| Requirement | Tests |
|-------------|-------|
| R1.1, R1.2 | T2, T4 |
| R1.3, R1.4 | T1, T2, T4 |
| R2.1–R2.3 | T2, T3, T4 |
| R3.1 | T6 |
| R3.2–R3.4 | T5 |
| R4.1–R4.4 | T1, T9 |
| R5.1, R5.2 | T8 |
| R6.1 | documentation review (`evidence/documentation.md`) |

## Verification environment

This checkout, Python via `uv`, tmux from the host for T4 (skipped with a reason where
tmux is absent or older than 3.2). No credential is used: every token in a test is a
dummy value.
