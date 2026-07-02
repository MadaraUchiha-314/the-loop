---
type: requirements
phase: requirements-definition
workItem: issue-12
status: approved
approvedBy: ["@MadaraUchiha-314 (issue author intent)"]
collaborators: [architect, engineer]
overrides: {}
---

# Requirements: the-loop should be compatible with Cursor

> **Source of truth:** GitHub [issue #12](https://github.com/MadaraUchiha-314/the-loop/issues/12)
> is the canonical requirements input for this work item. This file distills it into
> reviewable, testable requirements. Design and the task DAG live in `design.md` and
> `tasks.md`.

## Introduction

the-loop ships as a Claude Code plugin; decision-001 left Cursor distribution as a
TODO. This work item researches Cursor's equivalent of Claude plugins and packages
the-loop for Cursor, **reusing** the existing skills, commands and templates rather
than forking them.

## Requirements

### R1 — Research Cursor's plugin equivalent

**User story:** As the-loop's maintainer, I want a documented answer to "what is the
Cursor equivalent of Claude plugins", so that distribution decisions rest on facts.
1. the-loop SHALL document what Cursor offers as the equivalent of Claude Code plugins
   (manifests, component types, discovery, installation) in a decision record.
2. The research SHALL identify which existing artifacts (skills, commands, hooks) are
   reusable as-is and which need a Cursor-native replacement.

### R2 — Installable in Cursor from this repo

**User story:** As a Cursor user, I want to install the-loop directly from GitHub, so
that I get the same loop without a separate distribution channel.
1. The repository SHALL carry a Cursor plugin manifest (`.cursor-plugin/plugin.json`)
   and marketplace manifest (`.cursor-plugin/marketplace.json`).
2. WHEN the plugin is installed in Cursor THEN the existing `skills/` and `commands/`
   SHALL be reused verbatim (no duplicated content per harness).
3. The Claude Code plugin SHALL be unaffected (same `.claude-plugin/` manifests, same
   `hooks/hooks.json`).

### R3 — Session reminder parity in Cursor

1. Cursor sessions SHALL receive the same "the-loop is initialized here" reminder that
   Claude Code gets via the `SessionStart` hook, using a Cursor-native mechanism.
2. The mechanism SHALL NOT fire misleadingly in projects where the-loop is not
   initialized (guarded, like the hook's `test -f .the-loop/config.yaml`).

### R4 — Docs reflect dual-harness support

1. README (install, layout), the skill + its references, the architecture doc, the
   roadmap and the decision log SHALL be updated to describe Claude Code **and** Cursor
   support, resolving the open question "find the Cursor equivalent of marketplace
   distribution".

## Non-functional requirements

- New JSON manifests are validated in CI alongside the Claude ones.
- All quality gates stay green: ruff, pyright, pytest, markdownlint, schema validation.

## Out of scope (this work item)

- Cursor-only surface: `agents/` subagents, Cursor-format hooks (e.g.
  `beforeShellExecution` quality gates), MCP server definitions.
- Publishing to Cursor's curated marketplace listing (install-from-repo suffices).
- Verifying behaviour inside a live Cursor install (no Cursor runtime in CI).
