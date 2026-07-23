# Installation

the-loop is installable directly from GitHub via each harness's marketplace construct —
no bespoke marketplace publishing. One repo, one set of skills/commands/templates, two
plugin manifests (`.claude-plugin/` and `.cursor-plugin/`).

## Claude Code

```text
/plugin marketplace add MadaraUchiha-314/the-loop
/plugin install the-loop@the-loop
```

## Cursor

Cursor (≥ 2.5) resolves the plugin from this repo's `.cursor-plugin/` manifests. Install
it either way:

- **From the marketplace** — in the slash menu run `/add-plugin`, or open
  **Settings → Plugins → Add**, and point it at the repository URL:

  ```text
  https://github.com/MadaraUchiha-314/the-loop
  ```

- **Locally** (for development) — check the repo out under Cursor's local plugins dir:

  ```bash
  git clone https://github.com/MadaraUchiha-314/the-loop \
    ~/.cursor/plugins/local/the-loop
  ```

Skills follow the [Agent Skills](https://agentskills.io) open standard, so the same
`SKILL.md` powers both harnesses; commands appear in Cursor's slash menu (by filename,
e.g. `/init`); the Claude Code SessionStart hook is replaced by the always-applied rule
`rules/the-loop.mdc`.

## CLI companion (optional)

Besides the plugin, the-loop ships a lightweight, extensible Python CLI for
quality-of-life commands the plugin uses (webhook routing, polling, observability).
See the [CLI reference](/cli/) for install instructions and the full command set.

## Next

Run [`/the-loop:init`](/reference/commands#the-loop-init) in your target repo, then
follow the [quickstart](/guide/quickstart).
