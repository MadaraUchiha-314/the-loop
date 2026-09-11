# Security review: issue-339

Gate: `security.review.required: true`, `mechanism: auto`. Risk tier 3 — below
`humanSignOffMinTier: 4` — so no named human security sign-off is required.
Executed 2026-09-11: the bundled `security-review` skill over this branch's
change set, then the five abuse cases from
[`bugfix.md`](../bugfix.md#security-considerations) one at a time.

## Automated review

**No findings.** The skill's own diff target (`origin/HEAD...`) spans six
releases of unrelated merged work, so the review was re-run scoped to this
branch's diff (`git diff HEAD -- cli/ .the-loop/`, plus the two new test files).
Paths traced, and why each is closed:

- **`THE_LOOP_CLI_CONFIG` injection.** `child_env()` derives its value only from
  `default_cli_config_path()` — the `--config` pre-scan override, the env var, or
  the fixed `./.the-loop/` / `~/.the-loop/` probe. All three call sites invoke it
  with no arguments, so no HTTP body, GitHub comment or config value reaches it.
  `control_daemon`'s attacker-reachable `daemon`/`verb` feed a fixed argv with
  `shell=False`, never the environment.
- **Config write-back.** `apply_state_root` mutates the in-memory document only.
  Every writer of the YAML re-reads the raw file (`core.config.update_config` via
  `_parse`, `migrate_cmd` via `_load_cli_config_raw`), so the injected absolute
  root is never spliced into the operator's config.
- **The widened health body.** `GET /api/v1/config` already serves the whole
  config document *and* its path to exactly the same callers across the same
  loopback/CORS boundary, so `configPath`/`stateRoot`/pidfile paths are not an
  escalation. The body is a closed set of fields: no pid, token or environment
  value.
- **The `ingress.hosted_failed` reason.** The Slack path interpolates
  `app_token_env`/`bot_token_env` — variable **names** read from the config, never
  `os.environ` values — and `_acquire` carries a pidfile path and a recorded pid.
  `core/selfdiagnosis.py`'s `ALLOWED_FIELDS` allow-list drops `reason` entirely,
  so nothing from it can reach a self-filed public issue.
- **The lock release on self-exit.** `RunLock.release` nulls `_fd` before
  unlinking and no-ops when not held; `_open_locked`'s inode-currency retry means
  no other process can substitute a file at that path while the flock is held. The
  new `finally` cannot unlink a lockfile a live process owns.

## Abuse cases

| # | Abuse case | Closed by | Test |
|---|------------|-----------|------|
| AC1 | a caller sets `THE_LOOP_CLI_CONFIG` in a spawned child to point the daemon at a config it chose | `child_env()` takes no caller input: the value is `default_cli_config_path()`, the path this process already resolved (the issue-222 property `schedule_restart` holds). A child that is itself a CLI invocation with `--config` still wins, the flag being priority 1 | `test_state_root_integration.py::test_security_the_spawn_environment_carries_only_the_resolved_path`, `test_core_daemons.py::test_a_spawned_daemon_carries_the_config_this_process_resolved`, `test_client.py::test_the_auto_started_service_carries_the_config_this_process_resolved` |
| AC2 | a `state.root` in a hand-written config escapes to somewhere it should not write | Unchanged authority: an absolute `state.root` was already used verbatim, and it is operator-written config, not request input. Anchoring a *relative* root beside the config **narrows** where it can land. A non-string is refused with a warning rather than `str()`-ed into a path | `test_cli_config.py::test_a_non_string_state_root_warns_and_takes_the_default`, `::test_state_root_anchors_on_a_config_that_is_not_inside_a_the_loop_directory` |
| AC3 | `/api/v1/health` becomes an unauthenticated inventory of the host | The response is a closed set of five keys and four per-ingress keys, asserted exactly; the two paths it adds are already served in full by `GET /api/v1/config` to the same callers. No pid, token, secret or environment value — pinned by setting a secret in the environment and asserting it is absent from the response text. The exposure guard (`service.exposed`) and the CORS allowlist are untouched | `test_api_health_integration.py::test_security_a_degraded_health_is_still_reachable_and_carries_no_secret` |
| AC4 | the degraded body is used to make an unrelated CLI command hammer a live service | A degraded health is still HTTP 200, so `client.healthy()` still means "reachable" and `ensure_service` does not respawn — asserted by driving `ensure_service` against a degraded service and requiring zero spawns | same test |
| AC5 | the new `ingress.hosted_failed` reason leaks a secret | The reasons are the ones already written to the logfile: a lock holder's pid, a pidfile path, "polling.sources is empty", and for Slack the missing environment **variable names**. No value is read, and `selfdiagnosis`'s field allow-list drops `reason` before anything is filed | `test_api_health_integration.py::test_an_enabled_ingress_that_cannot_start_writes_an_error_event` (asserts the reason names the config key, not a value) |

**Five of five closed.** No trust boundary moves in this change: no new call,
grant, token, scope, credential or state, and the one surface that grows — a
loopback response body — grows by two paths its caller already had.

## Residual risk, accepted

`state.root` and `THE_LOOP_CLI_CONFIG` remain operator-controlled paths that
decide where the daemon reads and writes. That authority is unchanged and is the
point of both settings; anyone who can edit the CLI config or the unit file can
already run the daemon. What the change removes is the *implicit* third input —
the working directory — which nothing guaranteed and nobody declared.
