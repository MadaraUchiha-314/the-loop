# Verification (issue-442)

Executed at the `verification` node on 2026-09-30, head of this work item's PR branch
(`claude/github-issue-442-vovfqj`), in the work item's cloud checkout (`uv 0.12.21`,
Python 3.11, PyGithub 2.10.0, **no `gh` on `PATH`**, `GH_TOKEN`/`GITHUB_TOKEN` deleted for
every test by `conftest.py`). One section per row of `testing-plan.md`; summaries as the
runner printed them.

## T1 — unit, the client

```text
$ uv run python -m pytest -q tests/test_ghapi.py
49 passed in 0.10s
```

Every test runs the real client over the real PyGithub with HTTP replaced by PyGithub's own
connection-injection hook (`tests/ghreplay.py`). Red → green: the suite was written against
a smoke-tested client and went red on two PyGithub behaviours the implementation then
corrected — the `url` stamp PyGithub puts on an empty document
(`test_an_empty_document_is_an_error_not_an_open_item`) and the eager completion of a
URL-built object (`test_post_comment_is_one_post_on_the_issues_endpoint`, which asserts
exactly one exchange). Outcome: **pass**.

## T2 — unit, the writers

```text
$ uv run python -m pytest -q tests/test_comments.py tests/test_linkage.py tests/test_reactions.py \
    tests/test_announce.py tests/test_selfdiagnosis.py
116 passed in 2.30s
```

## T3 — unit, the readers and config

```text
$ uv run python -m pytest -q tests/test_poller.py tests/test_graph_integrations.py \
    tests/test_cli_config.py tests/test_control.py tests/test_sdk_environment.py
360 passed in 1.14s
```

## T4 — integration (scenario)

```text
$ uv run python -m pytest -q tests/test_poller_integration.py tests/test_reactions_integration.py \
    tests/test_tmux_runner_integration.py tests/test_selfdiagnosis_integration.py \
    tests/test_channels_integration.py tests/test_control_integration.py \
    tests/test_webhook_routing_integration.py tests/test_channels_records_integration.py \
    tests/test_poll_daemon_integration.py tests/test_hosted_ingress_integration.py
226 passed in 71.68s (0:01:11)
```

The daemon scenarios start real `the-loop` processes with `GH_TOKEN` set and
`integrations.github.api.baseUrl` pointed at a loopback GitHub (`tests/ghstub.py`): a poll
cycle completes, the poller's log names `github octo/repo`, `stop` releases every lock.

## T5 — contract / parity

```text
$ uv run python -m pytest -q tests/test_config_schema_parity.py tests/test_docs_parity.py tests/test_sdk_docs_parity.py
12 passed in 0.15s
$ uv sync --locked
(resolved; the lockfile is up to date)
```

## T6 — migration / upgrade

```text
$ uv run python -m pytest -q tests/test_migrations.py
64 passed in 2.44s
```

A `0.10.0` file with `transport: cli` migrates to `0.11.0` with both keys gone and the token
note; one with `transport: api` and a `tokenEnv` migrates quietly; a `0.1.0` file with the
per-feature `ghBinary` keys migrates in one pass and reports both moves; an un-migrated file
is refused naming the keys, the token and the command; idempotent.

## T7 — security / abuse cases

```text
$ uv run python -m pytest -q tests -k "token_never or hostile or not_a_host or operations_unchanged \
    or no_rate_limit_sleep or graphql_mutation_with_variables or missing_token or bad_number \
    or refuse_an_unknown_content"
35 passed, 4986 deselected in 2.88s
```

One negative test per abuse case A1–A8; the mapping is in `evidence/security-review.md`.

## T8 — performance

```text
$ uv run python -m pytest -q tests/test_ghapi.py -k "six_requests or reuses"
2 passed, 47 deselected in 0.04s
```

A cycle over one issue and one pull request is `2 + 1 + 3` exchanges (R5.2); two writes
through the shared client reuse one `Github`.

## T10 — manual

Procedure in `evidence/manual.md`. The `gh`-less-box steps that need no live repository
(install, pre-flight with and without a token, a cycle against the loopback GitHub) were run
in the cloud checkout; the live-repository steps are the owner's to run and are recorded
as **not run by the agent**.

## T11 — the repository's own gates

```text
$ uv run ruff check cli hooks            → All checks passed!
$ uv run ruff format --check cli hooks   → 394 files already formatted
$ uv run pyright cli                     → 0 errors, 0 warnings, 0 informations
$ uv run python scripts/validate_config.py
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
$ npx --yes markdownlint-cli2@0.18.1 "**/*.md"
Linting: 1475 file(s)  Summary: 0 error(s)
$ cd cli && uv run python -m pytest -q
5020 passed, 1 skipped, 1 warning in 201.68s (0:03:21)
```

## T12 — security review

`evidence/security-review.md`: no open finding; the tier-4 human sign-off is requested on
the PR.
