# Contributing

the-loop dogfoods its own rules: the same checks run locally (pre-commit) and in CI.

## Setup

```bash
make install-dev     # ruff, pyright, pytest, pre-commit, jsonschema, pyyaml, the CLI
pre-commit install   # run the gates on every commit
```

the-loop uses [uv](https://docs.astral.sh/uv/) as its declared Python package manager
(a `uv` workspace with the `cli/` member) — see
[decision-009](/developer/decisions/decision-009).

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
[decision-006](/developer/decisions/decision-006).

## Commits

All commits follow [Conventional Commits](https://www.conventionalcommits.org/),
enforced via [commitizen](https://commitizen-tools.github.io/commitizen/) — see
[decision-008](/developer/decisions/decision-008). `feat`/`fix`/`BREAKING CHANGE`
commits on `main` drive the CLI's automatic semantic release to PyPI — see
[decision-019](/developer/decisions/decision-019).

## This documentation site

The site lives in `docs-site/` (a [VitePress](https://vitepress.dev/) project) and
pulls the canonical `docs/`, `cli/README.md`, and `skills/the-loop/reference/` content
into itself at build time via `docs-site/scripts/sync-content.mjs` — so there is one
source of truth, not a hand-copied fork.

```bash
cd docs-site
npm install
npm run docs:dev     # local preview at http://localhost:5173
npm run docs:build   # production build to docs-site/.vitepress/dist
```

It deploys to GitHub Pages via
[`.github/workflows/docs.yml`](https://github.com/MadaraUchiha-314/the-loop/blob/main/.github/workflows/docs.yml)
on every push to `main`.

## Feedback

All feedback for the-loop is provided through
[GitHub issues](https://github.com/MadaraUchiha-314/the-loop/issues) on this
repository — and, fittingly, the-loop uses the-loop to improve itself.
