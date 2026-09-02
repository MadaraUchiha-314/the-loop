# Verification — issue-311

> The testing plan executed (`testing-plan.md`, rows T1–T10). Commands run from the
> repository root at the head of `claude/github-issue-311-hp66sw`. Fixture hosts
> (`ghe.corp.example`) are not real; nothing here is redacted because nothing needed it.

## Red → green, per task

| Task | Red (before the change) | Green |
|------|-------------------------|-------|
| 1 resolver | `tests/test_ghhost.py` — `ModuleNotFoundError: the_loop.ghhost` (collection error) | 37 passed |
| 2 minting | `tests/test_graph_refs.py` — 9 failed (`ref_for() got an unexpected keyword argument 'host'`) | 42 passed |
| 3 writers | `tests/test_comments.py` — collection error (`cannot import name 'gh_host_args'`); `test_reactions.py` host cases failed | 97 passed across comments/reactions/linkage/announce |
| 4 poller | `tests/test_poller.py` — 11 failed (`RepoSpec` has no `host`; `--repo octo/repo`) | 184 passed (poller + poller integration) |
| 5 transports | `tests/test_graph_integrations.py` — collection error (`_ref_parts`) | 60 passed (with refs) |
| 6 review brief | `tests/test_graph_review.py` — 2 failed (a GHE URL dropped; detected pulls hostless) | 64 passed |
| 7 config/docs | — | schema parity, config schema, docs parity: 53 passed; `validate_config.py` VALID ×7 |

## `make check` — the way CI runs it

```text
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Finding: **/*.md !**/node_modules/** !cli/node_modules/** !**/.venv/** !docs/.vitepress/dist/** !docs/.vitepress/cache/** !docs/operating-model/reference/** !docs/specs/*/design/**
Linting: 924 file(s)
Summary: 0 error(s)
uv run ruff format --check cli hooks
274 files already formatted
uv run pyright cli
0 errors, 0 warnings, 0 informations
uv run python scripts/validate_config.py
…
2925 passed, 1 skipped in 173.24s (0:02:53)
exit=0
```

## Test matrix — results

| Row | Outcome | Evidence |
|-----|---------|----------|
| T1 | pass | `tests/test_ghhost.py` — 37 passed |
| T2 | pass | `tests/test_graph_refs.py` — 42 passed |
| T3 | pass | `tests/test_comments.py`, `tests/test_reactions.py`, `tests/test_linkage.py` |
| T4 | pass | `tests/test_poller.py` — 184 passed with `test_poller_integration.py` |
| T5 | pass | `tests/test_graph_integrations.py` |
| T6 | pass | `tests/test_graph_review.py` — 64 passed |
| T7 | pass | `tests/test_ghhost_integration.py` — 6 scenarios (config host, `GH_HOST`, the remote, `prRef`, github.com unchanged, a bad host skipped) |
| T8 | pass | `tests/test_config_schema_parity.py`, `tests/test_configschema.py`, `tests/test_docs_parity.py`; `make validate` |
| T9 | pass | see `security-review.md` |
| T10 | pass | `make check`: ruff, `ruff format --check`, pyright (0 errors), markdownlint (924 files, 0 errors), config validation, 2925 passed / 1 skipped |
