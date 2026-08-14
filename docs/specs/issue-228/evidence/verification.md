# Verification evidence — issue-228

> Executing [`../testing-plan.md`](../testing-plan.md). One section per activity; raw
> output in fenced blocks. Environment: this repository's checkout, `uv` workspace in
> `cli/`, Linux, Python 3.11. No credentials involved; all processes loopback-only
> against temp directories.

## T1 — `core.lifecycle` unit tests

```console
$ uv run pytest tests/test_core_lifecycle.py -q
10 passed
```

## T2 — lifecycle command tests

```console
$ uv run pytest tests/test_lifecycle_cmd.py -q
7 passed
```

## T3 — re-pointed poller tests

```console
$ uv run pytest tests/test_poll_daemon_integration.py tests/test_poll_command.py \
    tests/test_poll_status.py tests/test_poll_heartbeat.py -q
37 passed in 22.79s
```

One run of this combination failed a single process-table assertion while the full
suite was executing concurrently on the same machine (CPU contention stretching a
bounded wait); three immediate re-runs and all three full-suite runs passed. Recorded
rather than hidden — the timing bound is the daemon tests' known sensitivity, not new
to this change.

(`test_poll_daemon_integration` spawns real `the-loop start` subprocesses and
interrogates `/proc`; `test_poll_command` drives `daemon_entry poller --once`;
`test_poll_status` drives `the-loop status` text and JSON.)

## T4 — restart API + MCP flag integration

```console
$ uv run pytest tests/test_service_lifecycle_integration.py tests/test_mcp_integration.py \
    tests/test_api_routers_integration.py -q
19 passed in 9.15s     # incl. test_restart_schedules_a_detached_fixed_argv_process
                       # and test_mcp_can_be_disabled_per_config
```

## T5 — contract parity

```console
$ uv run pytest tests/test_api_contract_parity.py tests/test_config_schema_parity.py \
    tests/test_docs_parity.py tests/test_configschema.py -q
29 passed in 2.08s     # /api/v1/restart present in app + authored contract
```

## T6 — schema copies, docs parity, config schema

```console
(combined into the T5 run above: schema copies byte-identical, docs P1–P5 green over
the new/removed pages and the four new keys)
```

## T7 — full suite

```console
$ cd cli && uv run pytest -q
2034 passed, 1 skipped in 84.45s (final make check run; three full-suite runs total, all green)
```

The skip is the same pre-existing one `main` carries. The first run on this branch —
code changed, tests not yet re-pointed — was 23 failed / 1991 passed / 1 skipped, all
23 in the expected categories (poll-command suites, docs parity, two config tests);
the count then grew by the new lifecycle tests and shrank by the fork-specific
scenarios that died with `daemonize()`.

## T8 — lint / format / types

```console
$ make lint format-check typecheck
uv run ruff check cli hooks         → All checks passed!
npx markdownlint-cli2 "**/*.md"     → 658 file(s), 0 error(s)
uv run ruff format --check cli hooks → 212 files already formatted
uv run pyright cli                  → 0 errors, 0 warnings, 0 informations
```

## T9 — markdown lint

Included in `make lint` above (markdownlint-cli2 over 658 files, 0 errors). The three
errors it caught mid-work — unescaped `|` inside code spans in the new capability
history rows — were fixed, which is self-review round 1's second finding.

## T10 — config validation

```console
$ uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```

The template now carries the four new keys and validates against the updated schema;
the repo's own `cli-config.yaml` (no `enabled` keys) validates unchanged — R5.3.

## T11 — manual smoke (temp HOME, real service)

Script: fresh `$HOME` with a two-line `cli-config.yaml` (a free port, nothing else),
run from an empty working directory. Transcript, verbatim:

```console
$ the-loop start
service     started         [enabled]  started at http://127.0.0.1:34493; /mcp exposed
gh-webhook  disabled        [disabled]  webhooks.ghWebhook.enabled is false
poller      disabled        [disabled]  polling.enabled is false
exit=0

$ the-loop status
service     running (pid 7060) [enabled] — http://127.0.0.1:34493, healthy
gh-webhook  not running [disabled]
poller      not running [disabled]
            last cycle: unknown — no heartbeat recorded
exit=0

$ the-loop restart
stopping:
poller      not-running     [disabled]  poller is not running
gh-webhook  not-running     [disabled]  gh-webhook is not running
service     stopped         [enabled]  stopped (pid 7060)
starting:
service     started         [enabled]  started at http://127.0.0.1:34493; /mcp exposed
gh-webhook  disabled        [disabled]  webhooks.ghWebhook.enabled is false
poller      disabled        [disabled]  polling.enabled is false
exit=0

$ the-loop stop
poller      not-running     [disabled]  poller is not running
gh-webhook  not-running     [disabled]  gh-webhook is not running
service     stopped         [enabled]  stopped (pid 7070)
exit=0

$ the-loop status (after stop)
service     not running [enabled]
gh-webhook  not running [disabled]
poller      not running [disabled]
            last cycle: unknown — no heartbeat recorded
exit=1
```

Every claim on display: defaults compose service-only (R5.3), disabled rows name their
keys (R1.2), restart is stop-then-start (R4.1), stop is idempotent about the
not-running daemons (R3.1), and the final `status` exits 1 because an enabled service
is down (R3.3). `--with-upgrade` was exercised at the plan level only (unit test with
the planner faked, plus the real planner's own issue-152 suite) — executing a real
upgrade would mutate this environment (testing-plan §Verification environment).

## T12 — reference sweep

```console
$ grep -rn "the-loop poll" README.md cli/README.md docs skills cli/the_loop \
    --include="*.md" --include="*.py" | grep -v docs/specs | grep -v docs/decisions
cli/the_loop/poller/daemon.py:3   # "``the-loop poll start`` used to be…" — the module
                                  # docstring describing the removal itself
```

Surviving matches are intended: the new daemon module's own docstring (which must name
the old command to explain the move), the historical record under `docs/specs/**` and
`docs/decisions/**`, and the rewritten test files whose docstrings describe what was
re-pointed. Four code docstrings still naming `the-loop poll status` were caught by
this sweep and fixed (self-review round 3).

## Docs site build

```console
$ cd docs && npm run docs:build
✓ building client + server bundles…
✓ rendering pages…
build complete in 41.95s
```

The new command pages, the edited option pages and the sidebar entries all render.
