# Verification evidence: issue-339

Executed 2026-09-11 on `claude/github-issue-339-2rj3oh`, base `48d1e8f`
(13.11.0). Commands are the testing plan's, run from the repository root.

## The failure, before the fix

`state.root` was relative, and `StateLayout` never anchored it, so the answer
depended on who asked:

```console
$ python3 -c "import os;from the_loop.state import layout_from_config as L;\
print(os.path.abspath(L({}).poll_status));os.chdir('/tmp');\
print(os.path.abspath(L({}).poll_status))"
/home/user/the-loop/.the-loop/poll-status.json
/tmp/.the-loop/poll-status.json
```

One config, two files. That is the whole bug; everything below is the fix and
the three reporting gaps that let it stay invisible for 17 hours.

## T1 · T2 · T3 · T8 · T10 · T12 — unit, scenario, contract, abuse, migration, docs

The new files were **red first**. `test_state_root_integration.py` did not
import against `48d1e8f` (`ImportError: cannot import name 'rival_roots'`), and
once it imported, `test_one_config_file_two_working_directories_one_state_root`
failed on the assertion above.

```console
$ uv run pytest cli/tests/test_state_root_integration.py cli/tests/test_api_health_integration.py -q
19 passed

$ uv run pytest cli/tests/test_cli_config.py cli/tests/test_state.py \
    cli/tests/test_core_daemons.py cli/tests/test_client.py -q
40 passed

$ uv run pytest cli/tests/test_api_contract_parity.py -q
2 passed

$ uv run pytest cli/tests/test_docs_parity.py cli/tests/test_config_schema_parity.py \
    cli/tests/test_state_portability.py -q
15 passed
```

Two existing assertions changed, both to the corrected contract, neither to
make a test pass:

| Test | Was | Is | Why |
|---|---|---|---|
| `test_cli_config.py::test_missing_file_lenient_empty_strict_raises` (and `test_empty_file_is_empty_mapping`) | the loaded document `== {}` | the document minus `state` `== {}` | the anchored root is applied to the empty document too — design §D1; a fresh install must not keep the cwd-relative default |
| `test_poll_command.py::test_default_options_resolve_under_the_state_root` | `Path(options.pidfile) == Path(".the-loop") / "poll.pid"` | `== tmp_path / ".the-loop" / "poll.pid"` | the assertion **is** the fix: the poller's paths are now absolute and anchored on its config |

## T13 — the whole suite

```console
$ uv run ruff check cli hooks
All checks passed!
$ uv run ruff format --check cli hooks
289 files already formatted
$ uv run pyright cli
0 errors, 0 warnings, 0 informations
$ uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
$ uv run --project cli python -m pytest -q cli
3366 passed, 1 skipped in 152.35s
$ npx markdownlint-cli2@0.18.1 "**/*.md"
Summary: 0 error(s)
```

New tests: 12 scenarios in `test_state_root_integration.py`, 7 in
`test_api_health_integration.py`, 4 unit cases in `test_cli_config.py`, 1 each
in `test_core_daemons.py` and `test_client.py`.

## T11 — the reporter's repro, run against a real service

A box at `<box>` with `polling.enabled: true` and one source, its config at
`<box>/.the-loop/cli-config.yaml`, started with `--config` from the repository
checkout — the reporter's shape exactly. This machine has **no `gh`**, so the
hosted poller's dependency check fails and its run loop returns during startup:
the reported failure, reproduced without contriving it.

**Before the `_host` change (same box, same command):** `start` reported
`poller hosted … (pid 17296)` and exited **0**, and health answered
`{"status": "ok", …}` — the dead poller's lock was still held under the
*service's* pid. That is the outage, reproduced by the code meant to catch it.

**After:**

```console
$ the-loop --config <box>/.the-loop/cli-config.yaml start
service         started    [enabled]   started at http://127.0.0.1:4114; /mcp exposed
gh-webhook      disabled   [disabled]  webhooks.ghWebhook.enabled is false
poller          failed     [enabled]   the service did not host it; check `the-loop events --source service`
slack-listener  disabled   [disabled]  channels.slack.enabled is false or read.mode is not socket
start exit=1

$ curl -s http://127.0.0.1:4114/api/v1/health
{
  "status": "degraded",
  "version": "13.11.0",
  "configPath": "<box>/.the-loop/cli-config.yaml",
  "stateRoot": "<box>/.the-loop",
  "ingresses": [
    {"name": "poller", "enabled": true, "running": false,
     "detail": "polling.enabled is true but nothing holds <box>/.the-loop/poll.pid"},
    {"name": "gh-webhook", "enabled": false, "running": false, "detail": ""},
    {"name": "slack-listener", "enabled": false, "running": false, "detail": ""}
  ]
}
```

`configPath` is the **operator's** config, not `~/.the-loop/cli-config.yaml`:
the spawned service read the file `--config` selected (R1.5), which is the half
of the fix a unit test cannot show.

`status`, from a directory that is neither the checkout nor the box — the
reporter's exact command:

```console
$ cd <box>/elsewhere && the-loop --config <box>/.the-loop/cli-config.yaml status
config      <box>/.the-loop/cli-config.yaml
state       <box>/.the-loop
instance    (unnamed) [open] — 0 declared, 0 managed
service     running (pid 17685) [enabled] — http://127.0.0.1:4114, healthy
gh-webhook  not running [disabled]
poller      not running [enabled]
            last cycle: unknown — no heartbeat recorded
slack-listener not running [disabled]
status exit=1
```

And with a **healthy** hosted poller (the run before the dependency check was
reached), the same command from the same unrelated directory reported
`poller  running (hosted in the service, pid 17296) [enabled]` — the line the
ticket reported as `not running`.

The event log, which the ticket says contained only a silence:

```json
{"ts":"2026-09-11T04:35:20.542Z","source":"service","event":"service.started","level":"info","pid":17685,"host":"127.0.0.1","port":4114}
{"ts":"2026-09-11T04:35:20.566Z","source":"service","event":"ingress.hosted","level":"info","pid":17685,"ingress":"poller"}
{"ts":"2026-09-11T04:35:20.568Z","source":"service","event":"ingress.hosted_failed","level":"error","pid":17685,"ingress":"poller","reason":"the run loop ended on its own, without a shutdown; its lock is released so `status` does not report it as running — the reason is in the service log"}
```

Redaction: the box path is rewritten as `<box>` above; no token, credential or
personal data appears in any captured output. The service was stopped after the
run (`the-loop stop` → `service stopped (pid 17685)`).

## Not verified

Nothing in the plan was skipped. Two limits worth naming:

- **T11 could not exercise a *successful* poll cycle** — this machine has no
  `gh` and no network to GitHub — so "the poller forwards a comment again" is
  covered by the existing poller suite, not by a live cycle here.
- **The multi-day heartbeat staleness** in the ticket is a consequence of the
  split root, not an independent behaviour; T2 proves the split is gone rather
  than waiting a day to prove the symptom is.
