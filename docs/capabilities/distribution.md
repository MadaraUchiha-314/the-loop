# Capability: distribution

> Shipping the-loop as an installable plugin for **Claude Code and Cursor** from a
> single repository — no bespoke marketplace publishing.

## What it is

The packaging that makes the-loop installable in both harnesses: two thin plugin
manifests over one shared set of skills, commands and templates.

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
- WHERE Claude Code uses the SessionStart hook (`hooks/hooks.json` →
  `hooks/session-start.sh`) the Cursor package SHALL use the always-applied rule
  `rules/the-loop.mdc` instead.
- On Claude Code, the SessionStart hook SHALL keep the installed plugin current: it
  fast-forwards the plugin's git checkout to `origin` on every new session, so a session
  is always up to date without a manual `/plugin update` (issue #38, decision-022). It is
  best-effort and never blocks or fails a session; skips a dirty/detached checkout;
  opt out with `THE_LOOP_AUTO_UPGRADE=0`. Cursor resolves the plugin from the repo
  directly and needs no hook for this.

## Design

[`docs/specs/issue-12/design.md`](../specs/issue-12/design.md) ·
[architecture § distribution](../architecture/architecture.md)

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-12 | Added Cursor packaging (`.cursor-plugin/`, `rules/the-loop.mdc`) reusing the same skills/commands | [spec](../specs/issue-12/), [decision-015](../decisions/decision-015.md) |
| issue-1 | Shipped the Claude Code plugin + marketplace manifests (v0) | [spec](../specs/issue-1/), [decision-001](../decisions/decision-001.md) |
