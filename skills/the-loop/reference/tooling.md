# Tooling reference

The harness uses exactly the tooling the repository already uses — **inferred from the
repository itself, every session**, never declared in a config (issue-352, third pass).
This file carries the inference rules (§ Tooling detection), the per-language matrix that
is the fallback where no signal exists, and the rules that hold whatever the tooling is.

## Repository management

- **Monorepo or not is inferred, never declared.** `nx.json` → Nx; `pnpm-workspace.yaml`
  → pnpm workspaces; a `workspaces` field in the root `package.json` → yarn or bun
  workspaces, whichever package manager was detected. None of those → not a monorepo,
  which is the common case (PR #195 review).
- **the-loop MUST also work in a non-monorepo setup.** Never assume a workspace tool
  exists; when none was detected, run the project's own scripts directly.
- **All scripts run from the project root.** Invoke build/test/lint/typecheck from the
  root, delegating to the workspace tool when there is one (e.g. `nx run <project>:test`)
  rather than `cd`-ing into packages.
  - _Open question:_ validate that "all scripts from root" scales for large monorepos;
    revisit and log a decision if it doesn't.

## Per-language tooling matrix

These are the **fallback defaults** — what the harness uses for a concern only when the
detection below finds no signal for it, and says so in the execution log.

| Concern | Python | JS/TS | Go (proposed defaults) |
|---------|--------|-------|------------------------|
| Package manager | `uv` | `bun` | `go` modules |
| Unit tests | `pytest` | `vitest` | `go test` |
| Integration tests | `pytest` | `playwright` | `go test` (+ testcontainers) |
| Lint | `ruff` | `oxlint` | `golangci-lint` |
| Type check | `pyright` | `tsc` | `go build` / `go vet` (compiler-enforced) |
| Release | `pypi` | `npm` | Go modules (VCS tags) |
| Containers | — | — | published to GitHub Container Registry (`ghcr`) |

- **Golang choices are proposed defaults** (the issue left them as "??"). Confirm with
  the user and record a decision before relying on them.
- **Linting covers ALL files, including markdown** (the repository's markdown linter,
  `markdownlint` where it has none). Lint markdown too — docs are first-class.
- **Integration tests carry Gherkin scenario docstrings** and REST/GraphQL contracts
  live under `specs/` (`config.testing` / `config.apiSpecs`) — see
  `reference/testing.md` for the conventions and the `the-loop scenarios` query.

## Artifact & release management

- TS/JS packages → **npm**; Python packages → **pypi**; Go → **module proxy / VCS
  tags**; container images → **GitHub Container Registry (ghcr)**.
- Releases use the same commands locally and in CI.

## Multi-artifact & multi-entity testing

When several entities in a monorepo must be tested together, link the packages locally
with the workspace tool so cross-package changes are exercised without publishing, and
run the services the project's own way (its compose file, its task runner). Which
container runtime a machine has is the operator's business, not the repository's — the
`localOrchestration` block that once named one was removed in issue-352.

## Pre-commit & pre-push hooks

The git hooks are the **repository's own**: run what its hook manager runs —
`.pre-commit-config.yaml`, a husky or lefthook config, the `package.json` scripts they
call, a `Makefile`/`justfile` check target — and those must be the SAME commands CI
runs. When the repository has none, the loop's baseline before a commit or a push is:

- **pre-commit**: lint, typecheck, unit tests.
- **pre-push**: lint, typecheck, unit tests (add integration tests where cheap).
- **commit-msg**: enforce Conventional Commits (the rule below).

## Hooks the PROJECT brings to the loop (`graph.hooks`)

Different hooks entirely from the section above: those are git hooks running the project's
own commands; these are **process-graph hooks** — a check of the project's own, appended to
a node boundary the-loop already declares (issue-248, decision-096). A project declares the
module and where it attaches; the-loop loads it and runs it in the same chain as its shipped
hooks.

- Names are `x-<something>`; the unprefixed namespace is the-loop's.
- An attached hook runs **after** every shipped hook at that node and can therefore only
  add a constraint: it can block or wait, never approve, and any `outcome` it declares is
  ignored.
- A module that cannot load fails the graph load rather than silently disappearing.
- When a node blocks on an `x-` hook, the finding is the **project's** rule, not the-loop's:
  read that module before treating it as a harness defect.

## RULE: Conventional Commits

All commits MUST follow Conventional Commits v1.0.0
(https://www.conventionalcommits.org/en/v1.0.0/):
`<type>[optional scope][!]: <description>`, where type is one of
`feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert`.
A `commit-msg` hook rejects non-conforming messages — this is a rule, not a setting.
**Prefer a well-maintained library over custom code:**
enforcement uses **[commitizen](https://commitizen-tools.github.io/commitizen/)**
(`cz check`) — configured in `.cz.toml` — not a bespoke validator. Merge/revert messages
are allowed through (`--allow-abort`). commitizen also offers `cz commit` (guided
messages) and `cz bump` (versioning/changelog) for later.

## RULE: CI/CD must use exactly the same tooling as local

No last-minute build failures from config/environment drift. CI jobs invoke the very
same root scripts/commands the pre-commit/pre-push hooks and the harness use locally.
When adding a check, add it in one place and reference it from both local hooks and CI.

## Tooling detection (every session)

Nothing declares the tooling: at the start of a work item, look for the signals of what
the project already uses, and fall back to the matrix above only where no signal exists.
Never stamp the defaults onto a project that has tooling of its own. Check, per language
present in the repo (manifests and file extensions say which languages are present):

### JS/TS

- `package.json` → `packageManager` field (e.g. `"pnpm@9.0.0"`) is authoritative for
  the package manager if present.
- Otherwise, lock file presence: `package-lock.json` → `npm`, `yarn.lock` → `yarn`,
  `bun.lockb` / `bun.lock` → `bun`, `pnpm-lock.yaml` → `pnpm`.
- `package.json` `devDependencies`/`dependencies` → infer:
  - unit/integration test runner: `jest`, `vitest`, `mocha`, `@playwright/test`, `cypress`.
  - linter: `eslint` (+ config flavor), `oxlint`, `biome`.
  - type checker: `typescript` (`tsc`), `ts-node`.
- Monorepo tool: `nx.json` → `nx`; `pnpm-workspace.yaml` → `pnpm`; `workspaces` field in
  root `package.json` → `yarn` or `bun` depending on the detected package manager.

### Python

- `pyproject.toml` → `[tool.poetry]`/`[project]` sections, `[tool.uv]`; `setup.cfg`;
  `requirements.txt`.
- `pyproject.toml` / lock files → package manager: `uv.lock` → `uv`, `poetry.lock` →
  `poetry`, bare `requirements.txt` → `pip`.
- Dependencies/dev-dependencies → test runner (`pytest`, `unittest`), linter (`ruff`,
  `flake8`), type checker (`pyright`, `mypy`).

### Go

- `go.mod` present → Go stack, package manager is always `go modules`.
- Look for `golangci.yml`/`.golangci.yaml` → `golangci-lint`; absence doesn't rule it out,
  check `go.sum`/tool directives too.

### Cross-check with CI

- Read `.github/workflows/*.yml` (or other CI config) for the actual commands invoked
  (e.g. `npm test`, `pytest`, `golangci-lint run`) and use them to confirm or override
  inferred tooling — CI is often the most reliable signal since it's what actually runs.

### Applying results

- Nothing is written into a config. The detected tooling is what this session runs —
  the package manager, test runner, linter, type checker and workspace tool behind every
  command in the work item — and the execution log records what was detected and from
  which signal, so the next session and a reviewer can check the inference.
- Where signals conflict, are absent, or only partially cover a concern (e.g. a test
  runner is inferred but no linter can be determined), use the matrix default for that
  concern and say so in the execution log ("defaulted — no signal found"), so a guess
  is visible as a guess rather than silently applied.
- Never silently apply a default when the project has _some_ tooling for that concern
  that merely wasn't recognized — prefer surfacing it to the user over guessing wrong.
