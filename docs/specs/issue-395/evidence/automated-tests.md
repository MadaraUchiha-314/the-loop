---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#395"
---

# Evidence: automated tests (issue-395)

Run on 2026-09-20, on the branch of the delivering PR (#400), from the repository
root unless noted. Nothing in the output names a token, a host or a person.

## T1 + T2 + T8 — the reconcile suite, beside the hosted-listener suite it extends

```
$ uv run --project cli python -m pytest -q cli/tests/test_hosted_reconcile.py cli/tests/test_hosted_listener.py
14 passed in 1.37s
```

New tests (all Gherkin-docstringed where they are scenarios):

- `test_wanted_is_the_enabled_set_in_boot_order` (T1 — R1.2, R1.3)
- `test_turning_read_mode_off_stops_the_hosted_listener_without_a_restart` (T2 — R1.1, R1.4, R1.8; the B5 reproduction)
- `test_turning_read_mode_back_to_socket_starts_the_listener_with_the_new_config` (T2 — R1.2, R1.4)
- `test_an_unrelated_edit_and_an_unparseable_one_leave_the_set_alone` (T2 — R1.3, R1.5)
- `test_a_disabled_poller_is_stopped_too` (T2 — R1.1)
- `test_shutdown_ends_the_supervisor_before_the_ingresses` (T2 — R1.6)
- `test_a_refused_start_on_reconcile_is_recorded_and_the_supervisor_survives` (T2/T8 — R1.2, abuse case 3)
- `test_reconcile_is_serialized_against_stop` (T2 — R1.6)

**Red first.** The suite was written before the production change and failed on
`AttributeError: module 'the_loop.api.ingress' has no attribute 'HostedIngresses'`
(seven tests) and `… no attribute '_wanted'` (one) — the red→green transition of the
TDD rule; the `status` test below failed on the old `running … [disabled]` line.

## T7 — `status` never prints a contradiction

```
$ cd cli && uv run python -m pytest -q tests/test_lifecycle_cmd.py tests/test_instance.py
72 passed in 0.39s
```

New test: `tests/test_lifecycle_cmd.py::test_status_never_prints_running_beside_disabled`
(R2.1). Before the fix it failed with
`slack-listener running (hosted in the service, pid 7) [disabled]` in the output.

## T12 — full suite, lint, format, typecheck

Run from `cli/`, which is how the pre-commit hook and CI run it:

```
$ cd cli && uv run python -m pytest -q
4291 passed, 1 skipped in 184.84s (0:03:04)

$ uv run ruff check cli hooks
All checks passed!
$ uv run ruff format --check cli hooks
338 files already formatted
$ uv run pyright cli
0 errors, 0 warnings, 0 informations
```

The lifespan, SDK, health and hosted-ingress integration suites were also run on their
own after the wiring change (`test_hosted_ingress_integration.py`,
`test_api_health_integration.py`, `test_core_lifecycle.py`, `test_lifecycle_integration.py`,
`test_service_lifecycle_integration.py`, `test_sdk*.py`, `test_eventlog.py`): 107 passed.

**A note on the working directory.** Run from the repository *root* instead of
`cli/`, four pre-existing tests in `tests/test_instance.py` fail on this branch **and on
`main`** (`assert all("-e" not in a for a in runner.argv)`): the checkout's own
`.the-loop/cli-config.yaml` is then the resolved config, and the runner exports it into
the spawned session's argv as `-e THE_LOOP_CLI_CONFIG=…` (issue-393 B6), which those
tests do not expect. Not this work item's — the file they read is untouched here — and
not what CI runs; recorded so the next person who runs `pytest` from the root is not
surprised.

CI on the PR's head (`b2689ba`): `gate`, `checks` and `ui` all green.
