# Tooling reference

The harness must use exactly the tooling declared in `.the-loop/config.yaml`
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
  - _Open question (from issue #1):_ validate that "all scripts from root" scales for
    large monorepos; revisit and log a decision if it doesn't.

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
- These are git hooks (e.g. wired via the repo's hook manager); they run the SAME
  commands as CI.

## RULE: CI/CD must use exactly the same tooling as local

No last-minute build failures from config/environment drift. CI jobs invoke the very
same root scripts/commands the pre-commit/pre-push hooks and the harness use locally.
When adding a check, add it in one place and reference it from both local hooks and CI.
