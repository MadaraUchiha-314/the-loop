# Decision 006: Dogfood the-loop's own quality gates (pre-commit + CI parity)

- **Status:** accepted
- **Date:** 2026-06-30
- **Deciders:** @MadaraUchiha-314 (via PR #2 review)
- **Work item:** issue-1

## Context

the-loop declared per-language tooling in config but did not actually run any linting,
type-checking, tests or pre-commit/CI on its own repository. Issue #1 requires
pre-commit hooks (lint/typecheck/unit-test) and that **CI uses exactly the same tooling
as local**. the-loop should dogfood this.

## Decision

Wire real quality gates for the-loop's own sources (a Python CLI + markdown docs):
- **ruff** (lint + format) for `cli/`, **pyright** (type check), **pytest** (unit
  tests), **markdownlint-cli2** for all markdown, and a **schema validation** script for
  `.the-loop` config.
- A single **pre-commit** config drives all of them. Hooks are `local`/`system` (they
  call the binaries on PATH) so there is one tool per check and no duplicate installs.
- **CI** (`.github/workflows/ci.yml`) installs the same pinned tools and runs
  `pre-commit run --all-files` — literally the same hooks as local. RULE satisfied.
- A root **Makefile** (`make check`, `lint`, `typecheck`, `test`, `validate`) wraps the
  same tools; all scripts run from the root.
- Updated the-loop's own `.the-loop/config.yaml` to reflect Python (was mistakenly `ts`).
- Markdown style: a curated `.markdownlint-cli2.jsonc` keeps structural rules and relaxes
  stylistic ones (line length, ASCII diagrams, `<placeholder>` tokens) that fight
  technical-doc style.

## Consequences

- the-loop now practises what it preaches; every push is gated by the same checks CI
  runs.
- Scaffolding these gates into *user* projects via `/init` remains a separate deferred
  task (this decision covers the-loop's own repo).
- Pinning is done at the install step (pip/npx) rather than via pre-commit's remote
  repos, which the sandboxed environment cannot fetch.

## Alternatives considered

- pre-commit's remote hook repos (ruff-pre-commit, etc.) — rejected here: the
  environment's git proxy blocks cloning them; local/system hooks are reproducible and
  keep local == CI.
- A heavier task runner (nox/tox) — unnecessary for a small CLI; Makefile + pre-commit
  suffice.
