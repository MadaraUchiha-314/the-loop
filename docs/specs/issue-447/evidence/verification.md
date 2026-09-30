# Verification (issue-447)

Executed at the `verification` node on 2026-09-30, on this work item's PR branch
(`claude/github-issue-447-1tf7jh`), in the work item's cloud checkout: `uv 0.12.21`,
Python 3.11, **no `gh` on `PATH`**, and `GH_TOKEN`/`GITHUB_TOKEN` deleted for every test
by `conftest.py`, with no network. One section per row of `testing-plan.md`. The
summaries are as the runner printed them, from `cli/`.

## T1: unit, the client

```text
$ uv run python -m pytest -q tests/test_ghapi.py
70 passed
```

The seven new methods run over the real PyGithub with HTTP replaced by `ghreplay`. The
tests assert each exchange's verb, path, query and JSON body, and the refusals before
any exchange. Outcome: **pass**.

## T2: unit, core

```text
$ uv run python -m pytest -q tests/test_github_ops.py
70 passed
```

Red → green: `test_discover_keeps_the_repositorys_own_spelling` went red first. It
exposed that the fake answered only the lower-cased key while core asks in the work
item's spelling, so the test data was fixed. The review round's tests (the host
allow-list, `merged: false`, a zero number, the reviewed-head pin, the created PR's
spelling) went red against the code before its fixes. Outcome: **pass**.

## T3: unit, the commands and routing

```text
$ uv run python -m pytest -q tests/test_github_verbs_cli.py
24 passed
```

Red → green: the two branch-reading tests failed on a fresh `git init` checkout with
`rev-parse --abbrev-ref`, which led to `symbolic-ref` (self-review S1). Outcome: **pass**.

## T4: integration (scenario)

```text
$ uv run python -m pytest -q tests/test_github_verbs_integration.py tests/test_mcp_integration.py
15 passed
```

These carry Gherkin docstrings: the comment is recorded, mirrored, and never
re-published; `pr create` records its link; the service serves every verb; a caller
mistake is a 400; the service and the MCP tool merge only by their own policy; the tools
are listed; and `link_pull_request` discovers. Outcome: **pass**.

## T5: contract and docs parity

```text
$ uv run python -m pytest -q tests/test_api_contract_parity.py tests/test_standing_security_integration.py tests/test_docs_parity.py
15 passed
```

Red → green: `test_p1_every_registered_command_has_a_page` failed for `comment`, `pr`
and `ticket` until their pages existed. Outcome: **pass**.

## T6: unit, the hook

```text
$ uv run python -m pytest -q tests/test_harness_link_pr.py
34 passed
```

Outcome: **pass**.

## T7: security and abuse cases

```text
$ uv run python -m pytest -q tests -k abuse_447
32 passed, 5161 deselected
```

There is at least one test for each of A1–A7; `security-review.md` maps each test to
its abuse case. Outcome: **pass**.

## T8: performance (bounded)

`test_pr_status_reads_are_bounded_at_three_exchanges`, in T1, asserts exactly three
exchanges. Outcome: **pass**.

## T9, T10: end-to-end and manual

`n/a`, as planned: a live exchange needs a token and a scratch repository this session
does not hold. The reviewer can check it in one line on a box with the daemon (PR
briefing, open question 2).

## T11: the repository's gates (`make check`, run step by step)

```text
uv run ruff check cli hooks                  -> All checks passed!
uv run ruff format --check cli hooks         -> 401 files already formatted
uv run pyright cli                           -> 0 errors, 0 warnings, 0 informations
uv run python scripts/validate_config.py     -> VALID (every config)
npx markdownlint-cli2@0.18.1 "**/*.md"       -> Summary: 0 error(s)
cd cli && uv run python -m pytest -q         -> 5192 passed, 1 skipped, 2 warnings
```

The baseline on `b473ced` was `5055 passed, 1 skipped, 1 warning`. The second warning
is pydantic's `UnsupportedFieldAttributeWarning` for the alias `body`. It is the same
class the suite already emits for the alias `repo`: the MCP SDK builds an argument
model from each tool's signature, and `post_comment` has a `body` parameter. It is
harmless. Outcome: **pass**.

## T12: security review

See `security-review.md`. No unresolved finding. Tier 3, so the autonomous review
suffices. Outcome: **pass**.
