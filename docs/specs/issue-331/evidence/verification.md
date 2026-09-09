# Verification — issue-331

> The testing plan executed (`testing-plan.md`, rows T1, T2, T8, T10, T12). Commands
> run from the repository root at the head of `claude/github-issue-331-ahsinr`. Every
> host, ref and path in the tests is a fixture (`ghe.corp.example`, `ghe.example.com`,
> `other.corp.example`, `octo/repo`). Nothing here needed redaction.

## Red → green

The new tests were written first. With the source unchanged at `6035e50` (13.7.0) and
only the tests in place, all seventeen fail (the two passing rows are pre-existing tests
the selection also matches):

```text
uv run --project cli python -m pytest -q cli/tests/test_poller.py cli/tests/test_poller_integration.py \
  -k "default_host or inherit or describe or enterprise or malformed_default or github_com_default or resolved_host or dedupes_an_inherited"
FAILED cli/tests/test_poller.py::test_repospec_inherits_a_default_host_unless_it_names_its_own
FAILED cli/tests/test_poller.py::test_a_github_com_default_leaves_the_spec_unwritten
FAILED cli/tests/test_poller.py::test_repospec_refuses_a_malformed_default_host[ghe]
FAILED cli/tests/test_poller.py::test_repospec_refuses_a_malformed_default_host[https://x.example]
FAILED cli/tests/test_poller.py::test_repospec_refuses_a_malformed_default_host[x.example/path]
FAILED cli/tests/test_poller.py::test_repospec_refuses_a_malformed_default_host[a b]
FAILED cli/tests/test_poller.py::test_parse_repos_dedupes_an_inherited_host_against_a_written_one
FAILED cli/tests/test_poller.py::test_provider_from_source_binds_bare_repos_to_the_default_host
FAILED cli/tests/test_poller.py::test_build_provider_carries_the_default_host
FAILED cli/tests/test_poller.py::test_a_bare_repo_inherits_the_default_host_and_owns_its_refs
FAILED cli/tests/test_poller.py::test_a_bare_repos_reads_go_to_the_inherited_host
FAILED cli/tests/test_poller.py::test_describe_names_the_host_a_source_is_bound_to
FAILED cli/tests/test_poller.py::test_the_daemon_binds_sources_to_the_resolved_host[integrations.github.host]
FAILED cli/tests/test_poller.py::test_the_daemon_binds_sources_to_the_resolved_host[GH_HOST]
FAILED cli/tests/test_poller.py::test_the_daemon_binds_sources_to_the_resolved_host[config-over-env]
FAILED cli/tests/test_poller.py::test_the_daemon_binds_sources_to_the_resolved_host[none]
FAILED cli/tests/test_poller_integration.py::test_a_closed_item_on_a_bare_enterprise_source_is_reconciled
17 failed, 2 passed, 213 deselected in 0.97s
```

The ticket's own assertion is the inverted core of
`test_a_bare_repo_inherits_the_default_host_and_owns_its_refs`: `owns()` answered
`False` for a ref on the configured repository; it now answers `True`, and still `False`
for the github.com twin.

| Task | Red (before the change) | Green |
|------|-------------------------|-------|
| 1 grammar + contract | `RepoSpec.parse` / `parse_repos` / `from_source` / `build_provider` take no `default_host`; `owns()` refuses the enterprise ref; `describe()` omits the host | the eleven grammar, contract, `owns()`, reads and `describe()` tests |
| 2 the daemon caller | `daemon._build_providers` does not exist | `test_the_daemon_binds_sources_to_the_resolved_host` ×4; `test_a_closed_item_on_a_bare_enterprise_source_is_reconciled` |
| 3 docs | — | `make lint` (markdownlint over every `*.md`), `test_docs_parity.py` |

Existing assertions changed: none. Two test helpers gained a parameter
(`test_poller_integration.py`'s `_make(default_host=…)`; `GhState` records `argv`).

## Rows

| Row | Command | Outcome |
|-----|---------|---------|
| T1 | `uv run --project cli python -m pytest -q cli/tests/test_poller.py -k "default_host or inherit or describe or resolved_host"` | `15 passed, 188 deselected` |
| T2 | `uv run --project cli python -m pytest -q cli/tests/test_poller_integration.py -k enterprise` | `1 passed, 28 deselected` |
| T8 | `uv run --project cli python -m pytest -q cli/tests/test_poller.py -k "malformed_default_host or inherits_the_default_host or github_com"` | `7 passed, 196 deselected` (A1 ×4, A2/R2.1, A3 ×2) |
| T10 | `uv run --project cli python -m pytest -q cli/tests/test_poller.py cli/tests/test_poller_integration.py` | `232 passed` — 215 pre-existing, unchanged, plus the 17 new |
| T12 | `make check` (ruff check · markdownlint · ruff format --check · pyright · validate_config · the full suite) | pass — ruff `All checks passed!`, markdownlint `Summary: 0 error(s)`, `281 files already formatted`, pyright `0 errors, 0 warnings, 0 informations`, config valid, `3182 passed, 1 skipped in 152.48s`. A first run, with the T1/T2/T8/T10 rows running concurrently on the same container, failed one pre-existing issue-315 scenario (`test_one_repository_with_issues_disabled_does_not_blind_the_others`: the spawn was observed before the registry write landed — a path this change does not touch, on a source with no default host); it passed five times alone and in the serial full run recorded here |

## T12 — `make check`, raw tail

```text
...............                                                          [100%]
3182 passed, 1 skipped in 152.48s (0:02:32)
```
