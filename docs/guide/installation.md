# Installation

the-loop is installable directly from GitHub via each harness's marketplace construct —
no bespoke marketplace publishing. One repo, one set of skills/commands/templates, two
plugin manifests (`.claude-plugin/` and `.cursor-plugin/`).

## From a terminal (either harness)

If you have [the CLI](/cli/installation), one command installs the plugin without opening
a session — at user scope, or for one project only:

```bash
pip install the-loopy-one            # once
the-loop install                     # the CLI + every harness found on PATH
the-loop install cursor              # Cursor only
the-loop install claude --scope project --project-dir .   # this repository only
the-loop upgrade                     # later, when a release lands
```

It drives each harness's own plugin installer where there is one — asking the binary
rather than assuming — prints every command before running it (`--dry-run` to preview),
and reports what it skipped and why. Where Cursor exposes no plugin CLI it falls back to
the local checkout described below, and a project-scoped Cursor install is reported
`skipped` rather than widened. See [`install`](/cli/commands/install) ·
[`upgrade`](/cli/commands/upgrade).

The in-session routes below work exactly as before for both harnesses, and are the
shortest path if you do not want the CLI.

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

  This is also what `the-loop install cursor` falls back to when `cursor-agent` exposes no
  plugin CLI — same path, same command, so the two cannot drift. `the-loop upgrade cursor`
  fast-forwards that checkout (`git pull --ff-only`), and leaves a clone you have committed
  on alone.

Skills follow the [Agent Skills](https://agentskills.io) open standard, so the same
`SKILL.md` powers both harnesses; commands appear in Cursor's slash menu (by filename,
e.g. `/init`); the Claude Code SessionStart hook is replaced by the always-applied rule
`rules/the-loop.mdc`.

## CLI companion (optional)

Besides the plugin, the-loop ships a lightweight, extensible Python CLI for
quality-of-life commands the plugin uses (webhook routing, polling, observability).
See [installing the CLI](/cli/installation) for install instructions, and
[the-loop CLI](/cli/) for what it does and why you might want it.

## Next

Run [`/the-loop:init`](/reference/commands#superset-commands) in your target repo, then
follow the [quickstart](/guide/quickstart).
