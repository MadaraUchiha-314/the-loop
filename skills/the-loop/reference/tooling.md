# Tooling reference

The harness must use exactly the tooling declared in `.the-loop/harness-config.yaml`
(`repository`, `tooling`, `localOrchestration`, `hooks` sections). This file explains
the rules and the per-language matrix so the essence is not lost.

## Repository management

- **Monorepo is configurable; default is Nx.** Other supported tools: yarn workspaces,
  pnpm workspaces, bun workspaces. Read `repository.monorepoTool`.
- **the-loop MUST also work in a non-monorepo setup** (`repository.monorepo: false`,
  `monorepoTool: none`). Never assume a workspace tool exists.
- **All scripts run from the project root** (`repository.runScriptsFromRoot: true`).
  Invoke build/test/lint/typecheck from the root, delegating to the workspace tool
  (e.g. `nx run <project>:test`) rather than `cd`-ing into packages.
  - _Open question:_ validate that "all scripts from root" scales for large monorepos;
    revisit and log a decision if it doesn't.

## Per-language tooling matrix

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
- **Linting covers ALL files, including markdown** (`tooling.lint.markdown`, default
  `markdownlint`). Lint markdown too — docs are first-class.
- **Integration tests carry Gherkin scenario docstrings** and REST/GraphQL contracts
  live under `specs/` (`config.testing` / `config.apiSpecs`) — see
  `reference/testing.md` for the conventions and the `the-loop scenarios` query.

## Artifact & release management

- TS/JS packages → **npm**; Python packages → **pypi**; Go → **module proxy / VCS
  tags**; container images → **GitHub Container Registry (ghcr)**.
- Releases use the same commands locally and in CI.

## Multi-artifact & multi-entity testing (`localOrchestration`)

When several entities in a monorepo must be tested together:
1. **All packages are locally linkable** (`linkPackagesLocally: true`) — use the
   workspace tool's linking so cross-package changes are exercised without publishing.
2. **All services run under `podman`** (`containerRuntime`).
3. **Each service can point local or remote** — `localOrchestration.remoteServices`
   lists services that should target a remote instead of running locally, so a
   developer/harness can run a subset locally.

## Pre-commit & pre-push hooks (`hooks`)

- **pre-commit**: `lint`, `typecheck`, `unit-test` (default).
- **pre-push**: `lint`, `typecheck`, `unit-test` (add `integration-test` where cheap).
- **commit-msg**: enforce the commit convention (`hooks.commitConvention`).
- These are git hooks (e.g. wired via the repo's hook manager); they run the SAME
  commands as CI.

## RULE: Conventional Commits

All commits MUST follow Conventional Commits v1.0.0
(https://www.conventionalcommits.org/en/v1.0.0/):
`<type>[optional scope][!]: <description>`, where type is one of
`feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert`.
`hooks.commitConvention` (default `conventional-commits`) wires a `commit-msg` hook that
rejects non-conforming messages. **Prefer a well-maintained library over custom code:**
enforcement uses **[commitizen](https://commitizen-tools.github.io/commitizen/)**
(`cz check`) — configured in `.cz.toml` — not a bespoke validator. Merge/revert messages
are allowed through (`--allow-abort`). commitizen also offers `cz commit` (guided
messages) and `cz bump` (versioning/changelog) for later.

## RULE: CI/CD must use exactly the same tooling as local

No last-minute build failures from config/environment drift. CI jobs invoke the very
same root scripts/commands the pre-commit/pre-push hooks and the harness use locally.
When adding a check, add it in one place and reference it from both local hooks and CI.

## Tooling detection (`/the-loop:init`)

`init` must never blindly stamp the defaults above onto an existing project — it must
first look for signals of what the project already uses, and only fall back to a
default where no signal exists. Check, per language present in the repo:

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

- Where a signal is unambiguous, write the detected tool directly into
  `tooling.<concern>.<language>`.
- Where signals conflict, are absent, or only partially cover a concern (e.g. a test
  runner is inferred but no linter can be determined), write the plugin default but
  append a same-line comment `# TODO: verify — no signal found, defaulted` so it's
  flagged in the init report's needs-user section rather than silently applied.
- Never silently apply a default when the project has _some_ tooling for that concern
  that merely wasn't recognized — prefer flagging over guessing wrong.
