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
— `docs/architecture/`, `docs/capabilities/`, `docs/decisions/`, `docs/specs/` and
`docs/reports/` are the site's pages, not a copy of them. The only synced content is the
two sources that must physically live elsewhere for functional reasons: `cli/README.md`
(also the CLI's PyPI package readme) and `skills/the-loop/reference/*.md` (read at
runtime by the harness from that exact path) — `docs/scripts/sync-content.mts` copies
those two into `docs/cli.md` and `docs/operating-model/reference/` at build time
(git-ignored). The `docs/specs/` sidebar is generated from the filesystem in
`docs/.vitepress/config.mts`, so new work items appear automatically.

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
