---
type: requirements
phase: requirements-definition
workItem: issue-46
status: draft
approvedBy: []
collaborators: [product-manager, architect, engineer]
overrides: {}
---

# Requirements: semantic-release based updates for the plugin manifests

> Phase 1 of 3 (requirements → design → tasks). Ticket:
> [issue #46](https://github.com/MadaraUchiha-314/the-loop/issues/46). This phase should
> be reviewed and approved before moving to design.

## Introduction

Issue #46 asks for semantic-release based updates to the-loop, modelled on
[alter-ego#8](https://github.com/MadaraUchiha-314/alter-ego/issues/8) — *automate plugin
versioning from conventional commits* — but with **Python tooling instead of the
TypeScript `semantic-release`**.

Most of that pipeline already exists (issue-21, decision-019): on merge to `main`,
commitizen (`cz bump`) derives the next semver from Conventional Commits, rewrites the
version, tags, generates the changelog, cuts a GitHub Release and publishes to PyPI.
What alter-ego#8 automates — the **plugin manifest version** — is exactly the piece
the-loop still misses: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`,
`.cursor-plugin/plugin.json` and `.cursor-plugin/marketplace.json` were frozen at
`0.1.0` while the release train reached `v0.7.0`. A user checking their installed
plugin version, or a marketplace listing, sees a version six releases stale — and the
plugin upgrade flow (`/the-loop:upgrade-the-loop`) has no truthful version to reason
about.

This work item closes that gap: plugin manifests become release-versioned artifacts,
bumped in lockstep by the existing Python release engine, with a guard so they can
never silently drift again.

## Requirements

### Requirement 1 — plugin manifests are versioned by the release engine

**User story:** As a plugin user (Claude Code or Cursor), I want the installed plugin's
manifest version to be the released version, so that what `/plugin` shows matches what
was actually released and upgrades are meaningful.

#### Acceptance criteria (EARS)

1. WHEN `cz bump` computes a new version THEN the system SHALL rewrite the `version`
   fields of `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` (both the
   marketplace metadata version and the plugin entry version),
   `.cursor-plugin/plugin.json` and `.cursor-plugin/marketplace.json` in the same bump
   commit as `.cz.toml` and `cli/pyproject.toml`.
2. WHEN this change lands THEN all plugin manifests SHALL carry the current released
   version (as of the merge) so the next bump's string replacement finds them.
3. WHERE versioning tooling is concerned the system SHALL use the already-adopted
   Python tool (commitizen, decision-008/019) — no TypeScript `semantic-release`, and
   no second release tool.

### Requirement 2 — version drift is caught at PR time, not release time

**User story:** As a maintainer, I want any version file that falls out of lockstep to
fail CI on the offending PR, so that a release never silently leaves an artifact
behind again.

#### Acceptance criteria (EARS)

1. WHEN any `version_files` target stops carrying the current `.cz.toml` version THEN
   the CLI test suite SHALL fail, naming the drifted file, line and expected version.
2. WHERE a target file has multiple version lines matching its pattern (the
   marketplace manifests) the check SHALL require EVERY matching line to carry the
   current version, so a half-updated file also fails.
3. The check SHALL be driven by `.cz.toml`'s own `version_files` list — adding a future
   versioned artifact to `version_files` SHALL bring it under the guard with no extra
   wiring.
4. The guard SHALL run via the existing pytest pre-commit hook and CI (RULE: no
   local-vs-CI drift) without new pipeline steps.

### Requirement 3 — the release pipeline itself is unchanged

**User story:** As the owner, I want this to be a pure extension of the existing
release machinery, so that nothing about triggering, tagging or publishing needs
re-review.

#### Acceptance criteria (EARS)

1. `.github/workflows/release.yml` SHALL NOT change: the same `cz bump --yes
   --changelog` invocation picks the new targets up from `.cz.toml`.
2. WHEN no releasable commit exists THEN behaviour SHALL remain a no-op, manifests
   untouched.

## Out of scope

- Commit-format enforcement at PR time (alter-ego#8 open question) — already covered
  by the `cz check` commit-msg hook (decision-008).
- Auto-detecting breaking skill-contract changes (alter-ego#8 open question) — not
  pulled into this work item.
- Versioning `.the-loop/config.yaml`'s `version` key — that is the config *format*
  version, not the release version.
