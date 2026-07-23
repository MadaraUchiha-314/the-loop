---
type: requirements
phase: requirements-definition
workItem: issue-63
status: approved
approvedBy: ["@MadaraUchiha-314 (issue #63)"]
collaborators: [product-manager, architect]
overrides: {}
---

# Requirements: split the-loop's config into CLI config and plugin config

> **Source of truth:** GitHub [issue #63](https://github.com/MadaraUchiha-314/the-loop/issues/63).
> Design and the task DAG live in [`design.md`](design.md) and [`tasks.md`](tasks.md).

## Introduction

the-loop ships two things with different lifecycles: a **plugin** (Claude Code / Cursor)
installed and configured per repository, and a **CLI** companion (webhook receiver +
event routing) that runs once per machine and works across many repos. Both read from a
single `.the-loop/config.yaml`, which conflates repo-independent CLI settings (the
`webhooks:` block) with per-repo plugin settings. This work item separates them.

## Requirements

### R1 — Two independent configs

**User story:** As a maintainer, I want the CLI's config separated from the per-repo
plugin config, so that a cross-repo CLI setting isn't duplicated into (and drifting
across) every repo where the plugin is installed.

#### Acceptance criteria (EARS)

1. WHEN configuration is defined THEN the system SHALL provide a **per-repo plugin
   config** (`.the-loop/config.yaml`, validated by `.the-loop/config.schema.json`) and a
   **user/machine-level CLI config** (validated by `.the-loop/cli-config.schema.json`).
2. WHEN the plugin config is validated THEN it SHALL NOT contain the `webhooks:` block
   (it moves to the CLI config).
3. WHILE both configs exist, the plugin config SHALL NOT be required for the CLI to read
   its own settings, and the CLI config SHALL NOT be required to drive the plugin.

### R2 — CLI config location is repo-independent

**User story:** As a CLI user, I want the CLI config to live outside any repo, so the
receiver can be configured once and route across many checkouts.

#### Acceptance criteria (EARS)

1. WHEN the CLI resolves its config THEN it SHALL use `$THE_LOOP_CLI_CONFIG` if set,
   else `$XDG_CONFIG_HOME/the-loop/config.yaml` (`XDG_CONFIG_HOME` defaulting to
   `~/.config`).
2. WHEN the CLI config is absent or PyYAML is unavailable THEN the CLI SHALL fall back to
   built-in defaults (preserving the zero-runtime-dependency guarantee).

### R3 — Backward compatibility

**User story:** As an existing user, I want my current `.the-loop/config.yaml`
`webhooks:` block to keep working, so the split doesn't break me on upgrade.

#### Acceptance criteria (EARS)

1. WHEN no CLI config is present AND the repo's `.the-loop/config.yaml` still carries a
   `webhooks:` block THEN the CLI SHALL read it and SHALL emit a deprecation warning
   naming the new location.
2. WHEN both a CLI config and a legacy block are present THEN the CLI config SHALL win.

### R4 — Documentation and scaffolding stay coherent

**User story:** As a reader, I want docs, templates and the manifest to reflect the two
configs, so the contract is discoverable.

#### Acceptance criteria (EARS)

1. WHEN the split ships THEN the system SHALL provide a CLI config template
   (`.the-loop/templates/cli-config.yaml`) and record both the new schema and template in
   `.the-loop/manifest.yaml`.
2. WHEN the split ships THEN the READMEs and capability docs SHALL describe the two
   configs and the CLI config location.
