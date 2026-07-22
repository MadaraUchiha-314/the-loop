# Capability: distribution

> Shipping the-loop as an installable plugin for **Claude Code and Cursor** from a
> single repository — no bespoke marketplace publishing.

## What it is

The packaging that makes the-loop installable in both harnesses: two thin plugin
manifests over one shared set of skills, commands and templates. The templates are
**internal** to the plugin — read from it when authoring artifacts, never copied into
the projects the-loop is run on.

## Current behaviour

- the-loop SHALL be installable in Claude Code directly from GitHub
  (`/plugin marketplace add MadaraUchiha-314/the-loop` +
  `/plugin install the-loop@the-loop`) via `.claude-plugin/plugin.json` +
  `marketplace.json`.
- the-loop SHALL be installable in Cursor (≥ 2.5) from the same repo via
  `.cursor-plugin/plugin.json` + `marketplace.json`, or by cloning under
  `~/.cursor/plugins/local/`.
- Both plugins SHALL reuse the SAME `skills/` (Agent Skills standard) and `commands/`;
  nothing is forked per harness.
- WHERE Claude Code uses the SessionStart hook (`hooks/hooks.json`) the Cursor package
  SHALL use the always-applied rule `rules/the-loop.mdc` instead.
- Work-item and process templates SHALL be internal to the plugin, shipped under
  `skills/the-loop/templates/` (`manifest.templatesDir`) and read from
  `${CLAUDE_PLUGIN_ROOT}` when an artifact is authored. `/the-loop:init` SHALL NOT copy
  them into a project; a project carries only its own generated artifacts.
- WHEN `/the-loop:upgrade-the-loop` runs on a project that an older version scaffolded a
  `.the-loop/templates/` folder into THEN it SHALL remove that folder (per
  `manifest.deprecated`), confirming first only if the user has added their own files
  under it.

## Design

[`docs/specs/issue-12/design.md`](../specs/issue-12/design.md) ·
[architecture § distribution](../architecture/architecture.md)

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-36 | Templates made internal to the plugin (`skills/the-loop/templates/`); init no longer copies them into projects, and upgrade cleans up the deprecated `.the-loop/templates/` folder | [spec](../specs/issue-36/) |
| issue-12 | Added Cursor packaging (`.cursor-plugin/`, `rules/the-loop.mdc`) reusing the same skills/commands | [spec](../specs/issue-12/), [decision-015](../decisions/decision-015.md) |
| issue-1 | Shipped the Claude Code plugin + marketplace manifests (v0) | [spec](../specs/issue-1/), [decision-001](../decisions/decision-001.md) |
