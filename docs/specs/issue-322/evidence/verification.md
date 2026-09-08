# Verification — issue-322 (instances scoped to their own work items)

> The record of `testing-plan.md` executed on branch `claude/github-issue-322-2yely4`,
> 2026-09-08. Commands are the plan's own; counts and tails are pasted from the runs.
> No credentials, paths outside the repository or hostnames appear here.

## Red → green per task

| Task | Red | Green |
|------|-----|-------|
| 1 the block | `tests/test_instance.py` collected against no `the_loop.instance` module: `ERROR tests/test_instance.py — ModuleNotFoundError` (1 error during collection) | `60 passed` after `instance.py`, `apply_instance`, `RoutingConfig.instance`, `ControlRecord.instance`, `command_comment(address=)`, `announcement_body(instance=)`, `TmuxRunner.instance`, `core/instance.py` (the first pass left 6 failing: the parenthesised token, the three fan-out tests and the two `describe_instance` tests — each fixed in turn) |
| 3 the seam | `tests/test_instance_integration.py`: `5 failed, 9 passed` — four on a test defect (`FakeTmux.deliveries` is `delivers`) and one on the CLI-start fake pointing the dispatcher at an empty control store | `14 passed` |
| 5 the surface | `test_lifecycle_cmd.py::test_status_prints_the_instance_line` written against the pre-change renderer | `8 passed` |
| 6 docs | `make check` → markdownlint `MD038` at `design.md:180` (a code span with a leading space); full suite `4 failed, 3104 passed` — three `test_cli_config.py` equality tests seeing the new `_instance` key on a config with no block, and `test_routing.py` pinning the settled vocabulary | the fan-out made conditional on a declared block; the vocabulary test and the `poll.comment_settled` catalogue entry extended with the four scope outcomes; `335 passed` on the affected suites, then the full gate below |

## Rows

### T1 — unit

```text
$ uv run --project cli python -m pytest -q cli/tests/test_instance.py cli/tests/test_control.py cli/tests/test_announce.py cli/tests/test_lifecycle_cmd.py
145 passed in 0.52s
```

### T2 — integration (two dispatchers, one event stream)

```text
$ uv run --project cli python -m pytest -q cli/tests/test_instance_integration.py
14 passed in 0.20s
```

Scenarios: an addressed start reaches only the instance it names · an unaddressed start on
two addressed instances reaches neither · an open unnamed instance is 13.3.1 · an explicit
address wins over the managed set · two different addresses are ambiguous · an address does
not unlock a locked instance but a declaration does · a managed work item is delivered in
every mode (×3) · a control record makes a work item managed · a refused event leaves no
mark · an unauthorized address grants nothing · `sessions start` on a locked instance is
refused and posts nothing · `sessions start` on an addressed instance claims and names
itself.

### T3 — contract and MCP

```text
$ uv run --project cli python -m pytest -q cli/tests/test_api_contract_parity.py cli/tests/test_mcp_integration.py
9 passed in 2.43s
```

### T8 — abuse cases A1–A6

```text
$ uv run --project cli python -m pytest -q cli/tests -k "unauthorized_address or malformed_token or does_not_unlock or unknown_mode_resolves or leaves_no_mark or only_the_configured_name"
17 passed, 3092 deselected in 5.85s
```

(Eleven of the seventeen are the parametrised malformed-token bodies of A2.)

### T10 — migration / parity / existing suites unchanged

```text
$ uv run --project cli python -m pytest -q cli/tests/test_config_schema_parity.py cli/tests/test_docs_parity.py cli/tests/test_sdk_docs_parity.py cli/tests/test_migrations.py cli/tests/test_control_integration.py cli/tests/test_graphlink_integration.py
104 passed in 7.97s
$ make validate
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```

The authored and packaged schemas are byte-identical (`cmp` exit 0); the schema diff is
purely additive (38 insertions, 0 deletions); `CURRENT_CONFIG_VERSION` unchanged.

### T12 — the whole gate

```text
$ make check
ruff check cli hooks            All checks passed!
markdownlint-cli2 (977 files)   Summary: 0 error(s)
ruff format --check             (clean)
pyright cli                     0 errors, 0 warnings, 0 informations
validate_config                 seven configs VALID
pytest -q cli                   3108 passed, 1 skipped in 147.51s
```

### T13 — security review

See [`security-review.md`](security-review.md): six abuse cases, six closed; the tier-4
human sign-off is requested from the owner at the PR.
