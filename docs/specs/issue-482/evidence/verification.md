---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#482"
---

# Verification: spawned sessions never receive a secret (issue-482, issue-485)

Executes [`testing-plan.md`](../testing-plan.md). All tokens used are dummy values.

## Activities

- [x] **T1 boundary** — `tests/test_session_environment.py`, `tests/test_envstate.py`: pass.
- [x] **T2, T3 argv and tmux environment** — `tests/test_tmux_runner.py::TestNoSecretReachesASession`: pass.
- [x] **T4 real tmux** — `tests/test_session_secrets_integration.py` on tmux 3.4 (Linux): pass. Red on the pre-change runner, which reproduced #485:

  ```text
  E       AssertionError: assert 'dummy-secret-value-482' not in 'tmux\x00new...sleep 30\x00'
  ```

- [x] **T5 routing** — `tests/test_github_verbs_cli.py` (`test_abuse_482_a5_…` ×3 markers, the stale-service and CLI exit-2 cases): pass.
- [x] **T6 ask route** — `tests/test_ask_route.py`: pass.
- [x] **T7 contract** — `tests/test_api_contract_parity.py` with `askSession`: pass.
- [x] **T8 drift and restart** — `tests/test_sessions_restart_integration.py` (31): pass.
- [x] **T9 config** — `make validate`: all configs valid; docs parity tests pass with `env.sessionPassthrough` documented.
- [x] **T10 regression** — below.
- [x] **T11 security** — [`security-review.md`](security-review.md).

## Repository checks

```text
$ uv run ruff check cli hooks          → All checks passed!
$ uv run ruff format --check cli hooks → 448 files left unchanged
$ uv run pyright cli                   → 0 errors, 0 warnings, 0 informations
$ npx markdownlint-cli2 "**/*.md"      → Summary: 0 error(s)
$ cd cli && uv run python -m pytest -q → 6068 passed, 1 skipped
```

## Known flake, not this PR's

`tests/test_control_integration.py` fails about 1 run in 5 on the base commit too
(07879a9, 5 runs with these changes stashed: 1 failure). It passed in the final full run.
