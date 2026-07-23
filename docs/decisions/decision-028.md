# Decision 028: Version plugin manifests in lockstep via commitizen `version_files` (no second release tool)

- **Status:** accepted
- **Date:** 2026-07-23
- **Deciders:** @MadaraUchiha-314 (issue #46)
- **Work item:** issue-46
- **Spec:** `docs/specs/issue-46/`

## Context

Issue #46 asks for "semantic-release based updates to the-loop", modelled on
[alter-ego#8](https://github.com/MadaraUchiha-314/alter-ego/issues/8) (automated
*plugin* versioning from conventional commits) and explicitly constrained to **Python
tools, not the TypeScript `semantic-release`**.

the-loop already runs a Python semantic-release pipeline (decision-019): commitizen
derives the version from Conventional Commits on merge to `main`, tags, generates the
changelog, cuts a GitHub Release and publishes to PyPI. But the pipeline only
versioned the CLI package: the Claude Code and Cursor plugin manifests
(`.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`,
`.cursor-plugin/plugin.json`, `.cursor-plugin/marketplace.json`) sat frozen at
`0.1.0` while releases reached `v0.7.0` — the exact manual-version problem alter-ego#8
automates away. Nothing detected the drift; commitizen's file rewriting is a string
replacement of the *current* version, so a drifted file is silently skipped forever.

## Decision

**Extend the existing commitizen configuration rather than adopt any new tool.**

1. The four plugin manifests join `.cz.toml`'s `version_files` (pattern `"version"`,
   which in the marketplace manifests covers both the metadata version and the plugin
   entry version), and are synced from `0.1.0` to the release-current version so replacement
   engages. Every future `cz bump` rewrites CLI package, plugin manifests, changelog
   and tag in one commit.
2. A **PR-time lockstep guard** makes silent drift structurally impossible:
   `scripts/check_version_lockstep.py` (stdlib-only) re-reads `version_files` from
   `.cz.toml` and requires every matching version line in every target to carry the
   current version. It runs as `cli/tests/test_version_lockstep.py` inside the CLI
   test suite, so the existing pytest pre-commit hook and CI enforce it with no
   pipeline changes — `release.yml` and `.pre-commit-config.yaml` are untouched.

## Consequences

- Installed-plugin and marketplace versions now tell the truth; the upgrade flow
  (`/the-loop:upgrade-the-loop`, alter-ego#8's "integration with upgrades" point) has
  a real version to compare against.
- Adding a future versioned artifact is one `version_files` line; the guard covers it
  automatically because it is driven by the same list.
- The bump commit grows to eight rewritten version fields across six files — all
  mechanical, all in one `bump:` commit.
- Versions `0.1.0`-era manifests shipped in older installs simply catch up on the next
  release; no migration is needed.
- **Known gap:** `uv.lock` also records the package version (it lagged one release behind
  on `main`; caught up here) but stays OUT of `version_files` — its `version`
  lines belong to every locked package, and commitizen's per-line string replacement
  could corrupt a third-party pin that coincidentally matches the current version. The
  drift is benign (`uv sync`/`uv run` re-locks it on next use); re-evaluate if that
  churn becomes noisy.

## Alternatives considered

- **`python-semantic-release`** — re-rejected (as in decision-019): commitizen already
  does the job; a second tool would split versioning authority.
- **TypeScript `semantic-release`** (alter-ego's tool) — excluded by the issue itself;
  would also add a Node release dependency to a Python-tooled repo.
- **`cz bump --check-consistency` in `release.yml`** — catches drift only when a
  release is already running (and fails the release); the PR-time guard catches it on
  the offending PR instead. Also, consistency-at-bump only checks
  found-at-least-once, which would pass a half-updated marketplace manifest.
- **A dedicated pre-commit hook for the guard** — equivalent coverage, but requires
  touching `.pre-commit-config.yaml`; riding the existing pytest hook needs no
  pipeline edits at all.
