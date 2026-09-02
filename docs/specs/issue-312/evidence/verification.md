# Verification — issue-312

> The testing plan executed (`testing-plan.md`, rows T1, T2, T8, T10, T12). Commands run
> from the repository root at the head of `claude/github-issue-312-1a2s8n`. Fixture ids
> (`C123`, `xoxb-test`, `github:o/r#7`) are not real; nothing here needed redaction.

## Red → green, per task

| Task | Red (before the change) | Green |
|------|-------------------------|-------|
| 1 state + lock | `test_channels.py` — 5 failed: `AttributeError: type object 'ChannelState' has no attribute 'locked'`; `bind() got an unexpected keyword argument 'origin'`; `conversation` missing | 10 passed (state section) |
| 2 root + reply | `test_channels.py` — 9 failed: `len(client.posted) == 2` was 1 (no root); no `channel.thread_opened`; no permalink; `conversation(...)` was `None` | 16 passed (channel section) |
| 3 `channels threads` | `test_channels.py` — 2 failed: `argparse` had no `threads` action; `status` printed no work-item count | 2 passed |
| 4 scenarios | `test_channels_integration.py` — 5 failed (the five scenarios); the re-pointed scenarios in `test_bus_integration.py`, `test_channels_integration.py`, `test_standing_channels_integration.py` — 6 failed on the old indices (`posted[0]` as the event, `len == 1`) | 29 passed across the three files |
| 5 docs | — | `make check` (markdownlint) below |

One of the re-pointed scenarios turned out to have been passing **vacuously** at `2bd6d3b`:
`test_an_agents_comment_reaches_slack_and_a_humans_only_when_subscribed` asserted
`posted[1]["thread_ts"] == posted[0]["thread_ts"]`, which held because **both were
`None`** — the fixture's issue URL (`https://gh/o/r/issues/7`) made the ingress mint
`github:gh/o/r#7` while the ask had bound `github:o/r#7`, so the agent's comment opened
a second top-level thread. Exactly the split this work item removes. The fixture now
names `github.com`, the assertion compares against the reply, and refs spelled with and
without the default host are one conversation (`canonical`,
`test_a_ref_spelled_with_the_default_host_shares_the_thread`).

## Rows T1, T2, T8, T10

```text
== T1  uv run --project cli python -m pytest -q cli/tests/test_channels.py cli/tests/test_eventlog.py
70 passed in 0.88s
== T2  uv run --project cli python -m pytest -q cli/tests/test_channels_integration.py cli/tests/test_bus_integration.py cli/tests/test_standing_channels_integration.py
29 passed in 0.49s
== T8  uv run --project cli python -m pytest -q cli/tests -k "root_shaped or ref_alone or failed_permalink or corrupt_state or without_flock"
5 passed, 2946 deselected in 1.84s
== T10 uv run --project cli python -m pytest -q cli/tests/test_channels.py cli/tests/test_channels_integration.py -k pre_issue_312
2 passed, 67 deselected in 0.10s
```

## `make check` — the way CI runs it (T12)

```text
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Finding: **/*.md !**/node_modules/** !cli/node_modules/** !**/.venv/** !docs/.vitepress/dist/** !docs/.vitepress/cache/** !docs/operating-model/reference/** !docs/specs/*/design/**
Linting: 933 file(s)
Summary: 0 error(s)
uv run ruff format --check cli hooks
274 files already formatted
uv run pyright cli
0 errors, 0 warnings, 0 informations
uv run python scripts/validate_config.py
…
All checks passed!
2950 passed, 1 skipped in 137.10s (0:02:17)
exit=0
```

## Test matrix — results

| Row | Outcome | Notes |
|-----|---------|-------|
| T1 | pass | 70 (channels unit + the event-type catalog, which pins `channel.thread_opened`) |
| T2 | pass | 29 across the three scenario files; the five new scenarios among them |
| T8 | pass | A1–A5, one negative test each |
| T10 | pass | the threads-only file is read, answered and rewritten keyed |
| T12 | pass | lint, format, typecheck, config validation, full suite — the block above |
| T13 | pass | `security-review.md`; no human sign-off at tier 3 |
