# Verification — issue-334

> The testing plan executed (`testing-plan.md`, rows T1, T2, T8, T10, T12). Commands run
> from the repository root at the head of `claude/github-issue-334-k9yw0i`. Every token,
> member id, channel id and URL in the tests is a fixture (`xoxb-supersecret`, `UHUMAN`,
> `C123`, `https://hooks.slack.com/commands/T/1/x`). Nothing here needed redaction.

## Red → green, per task

The new tests were written first. Against `e54592d` (13.8.0) the unit module does not
even import — `the_loop.channels.commands` does not exist:

```text
uv run --project cli python -m pytest -q cli/tests/test_channels_commands.py
ERROR cli/tests/test_channels_commands.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.24s
```

and the four integration scenarios fail the same way (each imports the module). One
scenario then failed for a real reason on the first green run — it read the thread
reply through `poll_once` under a `read.mode: socket` config, which the poll transport
rightly skips — and was corrected to go through `handle_socket_event`, the transport
the config names.

| Task | Red (before the change) | Green |
|------|-------------------------|-------|
| 1 catalog + events | `instance.command` / `standing.command` absent from `EVENTS`; the three `channel.command_*` types unknown to `eventlog.EVENT_TYPES` | `test_the_catalog_carries_the_two_command_grants`, `test_the_family_grants_are_catalog_rows`; `test_eventlog.py`; `test_bus.py` (two pins updated) |
| 2 parser + target | no `parse_invocation`, `resolve_work_item`, `may_target` | the eleven parser tests, the four resolver tests, the three target tests |
| 3 handler | no `handle_slash_command` | the twenty-one handler, answer and event tests |
| 4 transport + CLI + manifest | `channels manifest` unknown to argparse; no `commands:` line in `status`; no manifest file in the package | `test_the_manifest_is_packaged_and_printed`, `test_channels_status_says_which_command_families_are_granted`; the four scenarios |
| 5 docs | — | `test_the_guide_reproduces_the_packaged_manifest`, `test_the_docs_list_every_publishable_event`, `test_docs_parity.py`, markdownlint |

Baseline before the change: `test_channels.py` + `test_channels_integration.py` +
`test_docs_parity.py` + `test_eventlog.py` + `test_config_schema_parity.py` 142 passed.
After: 47 new unit tests in `test_channels_commands.py` and 4 new scenarios in
`test_channels_integration.py`. Existing assertions changed: two, both in `test_bus.py`
— the issue-309 pins of the publishable set (now six) and of "every publishable event is
recorded" (the two command grants are not, by design).

## Rows T1, T2, T8, T10

```text
== T1
uv run --project cli python -m pytest -q cli/tests/test_channels_commands.py
47 passed in 0.24s
== T2
uv run --project cli python -m pytest -q cli/tests/test_channels_integration.py
24 passed in 4.90s
== T8
uv run --project cli python -m pytest -q cli/tests/test_channels_commands.py -k "abuse or unauthorized or grant or foreign or duplicate or response_url or grammar or payload or malformed or unparsable or keyword_not_the_text or events_carry or disabled"
15 passed, 32 deselected in 0.17s
== T10
uv run --project cli python -m pytest -q cli/tests/test_config_schema_parity.py cli/tests/test_docs_parity.py cli/tests/test_eventlog.py cli/tests/test_channels.py cli/tests/test_bus.py
162 passed in 1.58s
```

## Row T12 — `make check`

```text
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Finding: **/*.md !**/node_modules/** !cli/node_modules/** !**/.venv/** !docs/.vitepress/dist/** !docs/.vitepress/cache/** !docs/operating-model/reference/** !docs/specs/*/design/**
Linting: 1024 file(s)
Summary: 0 error(s)
uv run ruff format --check cli hooks
283 files already formatted
uv run pyright cli
WARNING: there is a new pyright version available (v1.1.411 -> v1.1.412).
Please install the new version or set PYRIGHT_PYTHON_FORCE_VERSION to `latest`
0 errors, 0 warnings, 0 informations
uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
uv run --project cli python -m pytest -q cli
…
3251 passed, 1 skipped in 174.67s (0:02:54)
exit=0
```

Every gate the repository runs — `ruff check`, markdownlint over 1024 files,
`ruff format --check`, `pyright`, `validate_config` over the seven configs, and the whole
suite — passed on the head this evidence was written at.

## Row T13

[`security-review.md`](security-review.md) — nine abuse cases, nine closed.

## Addendum — the downtime gap closed at review (R2.6)

Raised by the owner on PR #336 (*how are Slack events accounted for while the-loop is
down?*). New tests, red first against the PR's previous head (`catch_up` did not exist;
`poll_once` refused socket mode; a redelivered message was processed twice):

| Test | Proves |
|------|--------|
| `test_channels_integration.py::test_a_socket_listener_catches_up_after_downtime` | the catch-up read processes a reply posted while no listener was connected exactly once; Slack's retry of the same `ts` is dropped as `duplicate`; a second catch-up processes nothing |
| `test_channels.py::test_poll_once_runs_in_socket_mode_as_a_reconciliation` | `poll_once` runs in `socket` mode (only `off` refuses) |
| `test_eventlog.py` | the catalog knows `channel.caught_up` |

```text
uv run --project cli python -m pytest -q cli/tests/test_channels.py cli/tests/test_channels_integration.py cli/tests/test_channels_commands.py cli/tests/test_eventlog.py
187 passed in 6.01s
make check
3253 passed, 1 skipped in 178.14s (0:02:58)
```

## Addendum — the service hosts the listener (R2.7)

Raised by the owner on PR #336 (*why can't this be encapsulated in `the-loop start`?*).
New tests, red first against the previous head (no `_start_slack_listener`, no
`slack-listener` row, no lock on `channels listen`):

| Test | Proves |
|------|--------|
| `test_hosted_listener.py` (6) | the service hosts the listener under its own pid and stops it through the stop event; a loop that exits on its own releases its lock; poll mode or a disabled channel hosts nothing; missing tokens refuse loudly; a held lock is not fought over; `channels listen` refuses beside a hosted listener |
| `test_core_lifecycle.py` (4 new, 7 updated) | `enabled_services` knows the listener; `start_all` rows `hosted` / `manual` / `already-running` / `disabled`; `stop_all` and `status_all` carry the fourth row |

```text
uv run --project cli python -m pytest -q cli/tests/test_core_lifecycle.py cli/tests/test_hosted_listener.py cli/tests/test_lifecycle_cmd.py cli/tests/test_channels.py cli/tests/test_channels_commands.py
181 passed in 1.17s
make check
3263 passed, 1 skipped in 175.82s (0:02:55)
```
