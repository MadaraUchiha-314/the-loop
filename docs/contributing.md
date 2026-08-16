# Contributing

the-loop dogfoods its own rules: the same checks run locally (pre-commit) and in CI.

## Setup

```bash
make install-dev     # ruff, pyright, pytest, pre-commit, jsonschema, pyyaml, the CLI
pre-commit install   # run the gates on every commit
```

the-loop uses [uv](https://docs.astral.sh/uv/) as its declared Python package manager
(a `uv` workspace with the `cli/` member) — see
[decision-009](/decisions/decision-009).

## Quality gates

```bash
make check                    # ruff (lint+format) · pyright · schema validation · pytest
pre-commit run --all-files    # exactly what CI runs
```

- **ruff** (lint + format) and **pyright** for `cli/`
- **pytest** for the CLI
- **markdownlint** for all docs
- **schema validation** for `.the-loop` config

### Hunting wait-ordering flakes

```bash
uv run --project cli python -m pytest --dispatch-lag=0.5 cli
```

Delays every dispatcher write that *follows* a spawn or a delivery — registry records,
dedup releases, announcements, graph moves — so a test that waits on the attempt and then
depends on its outcome fails on every run instead of about one in three
([issue-251](https://github.com/MadaraUchiha-314/the-loop/issues/251),
[decision-089](/decisions/decision-089)). Nothing is patched unless the flag is passed, so
`make check` is unaffected; run it when you add a test that drives work onto a background
thread, or when a flake needs a cause. The rule it enforces is in
[`reference/testing.md`](/operating-model/reference/testing).

CI ([`.github/workflows/ci.yml`](https://github.com/MadaraUchiha-314/the-loop/blob/main/.github/workflows/ci.yml))
runs the very same pre-commit hooks — no local-vs-CI drift. See
[decision-006](/decisions/decision-006).

## Commits

All commits follow [Conventional Commits](https://www.conventionalcommits.org/),
enforced via [commitizen](https://commitizen-tools.github.io/commitizen/) — see
[decision-008](/decisions/decision-008). `feat`/`fix`/`BREAKING CHANGE`
commits on `main` drive the CLI's automatic semantic release to PyPI — see
[decision-019](/decisions/decision-019).

## This documentation site

The site is [VitePress](https://vitepress.dev/) reading `docs/` directly as its source
— `docs/architecture/`, `docs/capabilities/`, `docs/cli/`, `docs/config/`,
`docs/decisions/`, `docs/specs/` and `docs/reports/` are the site's pages, not a copy of
them. The only synced content is the one source that must physically live elsewhere for a
functional reason: `skills/the-loop/reference/*.md` is read at **runtime** by the harness
from that exact path, so `docs/scripts/sync-content.mts` copies it into
`docs/operating-model/reference/` at build time (git-ignored). The `docs/specs/` sidebar is
generated from the filesystem in `docs/.vitepress/config.mts`, so new work items appear
automatically.

`cli/README.md` used to be synced in as `docs/cli.md` too. issue-117 replaced that single
page with authored pages under `docs/cli/` and `docs/config/`, leaving `cli/README.md` to
be what it also has to be — the CLI's PyPI package readme. Two rules follow, and a test
enforces both: **a registered CLI command needs a page** under `docs/cli/commands/`, and
**a CLI-config key needs a documented option** under `docs/config/cli/`. See
[documentation](/capabilities/documentation).

The site toolchain uses [bun](https://bun.sh/) (the-loop's declared TS package manager,
`tooling.packageManager.ts`); scripts are TypeScript (`.mts`), run by bun directly.

```bash
cd docs
bun install
bun run docs:dev     # local preview at http://localhost:5173
bun run docs:build   # production build to docs/.vitepress/dist
```

It deploys to GitHub Pages via
[`.github/workflows/docs.yml`](https://github.com/MadaraUchiha-314/the-loop/blob/main/.github/workflows/docs.yml)
on every push to `main`.

## Feedback

All feedback for the-loop is provided through
[GitHub issues](https://github.com/MadaraUchiha-314/the-loop/issues) on this
repository — and, fittingly, the-loop uses the-loop to improve itself.
