# Decision 015: Ship the-loop as a Cursor plugin from the same repo

- **Status:** accepted
- **Date:** 2026-07-02
- **Deciders:** @MadaraUchiha-314 (via issue #12)
- **Work item:** issue-12

## Context

Decision-001 shipped the-loop as a Claude Code plugin and left Cursor distribution as a
TODO ("find the Cursor equivalent of marketplace distribution"). Issue #12 asks to
research Cursor's equivalent of Claude plugins and make the-loop work in Cursor,
reusing the existing skills and content.

Research findings (Cursor 2.4/2.5, early 2026):

- **Cursor plugins** are the direct equivalent of Claude Code plugins: a
  `.cursor-plugin/plugin.json` manifest per plugin, an optional
  `.cursor-plugin/marketplace.json` at the repo root, installable from the marketplace,
  `/add-plugin`, a GitHub repo URL, or locally via `~/.cursor/plugins/local/`.
- Plugins bundle **skills** (`skills/<name>/SKILL.md` — the
  [Agent Skills](https://agentskills.io) open standard, same format Claude Code uses),
  **commands** (`commands/*.md`, surfaced in the slash menu), **rules** (`rules/*.mdc`),
  **agents**, **hooks** (`hooks/hooks.json`) and **MCP servers** — auto-discovered from
  those default directory names, with explicit paths in `plugin.json` overriding
  discovery.
- **Cursor hooks use a different format and event model** than Claude hooks
  (`beforeShellExecution`, `afterFileEdit`, `stop`, … — no `SessionStart` equivalent),
  so the one hook the-loop ships cannot be shared as-is.

the-loop's repo layout (`skills/`, `commands/`, `hooks/hooks.json`) already matches
Cursor's default component directories.

## Decision

Ship Cursor support from this same repository, reusing the existing content:

- Add `.cursor-plugin/plugin.json` + `.cursor-plugin/marketplace.json` mirroring the
  `.claude-plugin/` manifests. The Cursor manifest points explicitly at `skills/`,
  `commands/` and `rules/` — deliberately **not** at `hooks/`, whose `hooks.json` is
  Claude-format.
- `skills/` and `commands/` are shared verbatim between both harnesses (Agent Skills is
  a cross-harness standard; commands are plain markdown). Command prose that referenced
  `${CLAUDE_PLUGIN_ROOT}` now notes that it means the installed plugin's root in either
  harness.
- Replace the Claude `SessionStart` reminder hook, in Cursor, with an **always-applied
  rule** (`rules/the-loop.mdc`) carrying the same reminder — the Cursor-native mechanism
  for session-scoped context. Claude Code ignores `rules/`, so there is no duplication
  in either harness.

## Consequences

- One repo, one set of skills/commands/templates, two thin manifests — no content forks
  to keep in sync; version bumps touch both `plugin.json` files.
- Claude Code users are unaffected; `hooks/hooks.json` stays Claude-format.
- Cursor users get the same loop, commands under Cursor's slash-menu naming (`/init`
  instead of `/the-loop:init`), and the config reminder via the rule.
- Future Cursor-only surface (e.g. `beforeShellExecution` quality gates, subagents in
  `agents/`) has a natural home without restructuring.

## Alternatives considered

- **A separate Cursor repo / fork** — rejected: duplicates skills, commands and
  templates; the whole point is reuse.
- **Converting commands to per-command skills** — rejected: Cursor plugins support
  `commands/` markdown directly; skills-as-commands would fork content Claude Code
  already consumes as commands.
- **Porting the SessionStart hook to a Cursor hook** — rejected: Cursor's hook events
  (`beforeSubmitPrompt`, …) fire per-prompt, not per-session, and their JSON contract is
  permission-oriented; an always-applied rule is the idiomatic Cursor mechanism.
