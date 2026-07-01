# Decision 009: Dogfood uv (workspace + uv.lock) for the-loop's own tooling

- **Status:** accepted
- **Date:** 2026-07-01
- **Deciders:** @MadaraUchiha-314 (PR #2 review)
- **Work item:** issue-1

## Context

the-loop's config declares `uv` as the Python package manager
(`tooling.packageManager.python: uv`), and preaches "CI must use exactly the same
tooling as local." But the repo's own `Makefile` and CI used raw `pip install`. PR #2
review: "why are we not using uv for this project along with a pyproject.toml?" /
"practice what you preach."

## Decision

- Add a root `pyproject.toml` as a **uv workspace** (virtual root; member: `cli`) with a
  `dev` dependency group (ruff, pyright, pytest, pre-commit, commitizen, jsonschema,
  pyyaml). Commit **`uv.lock`** for reproducibility.
- `make install-dev` → `uv sync`; all task-runner targets and pre-commit hook entries run
  tools via **`uv run`**, so the exact locked versions are used whether invoked by
  `git commit`, `pre-commit run`, or CI.
- CI installs uv (`astral-sh/setup-uv`), runs `uv sync`, then
  `uv run pre-commit run --all-files` — same path as local.

## Consequences

- the-loop now uses the tooling it prescribes (see `learning-005`).
- `uv.lock` pins every version, directly serving the "no local-vs-CI drift" rule
  (`decision-006`): local and CI resolve identically.
- Contributors need `uv` installed; `make install-dev` (`uv sync`) is the one-step setup.

## Related fix (same change)

CI markdownlint was failing not on lint errors (0 errors) but on an unpinned
`npx --yes markdownlint-cli2` resolving a version combo that crashes under Node 20.
Fixed by pinning `markdownlint-cli2@0.18.1` and bumping CI Node 20 → 22 to match the
local environment — the same "pin versions, match runtimes, no drift" principle.

## Alternatives considered

- **Keep pip + per-tool installs** — rejected: contradicts the declared package manager
  and the no-drift rule.
- **Poetry / PDM** — rejected: uv is what the-loop already prescribes and is the fastest,
  simplest fit for the existing stack.
