# `upgrade`

Move an installed the-loop forward: the **CLI** and the plugin, in **Claude Code**,
**Cursor** or both.

```bash
the-loop upgrade [COMPONENT ...] [--scope user|project] [--project-dir .]
                 [--from owner/repo] [--dry-run] [--format table|json]
```

```text
$ the-loop upgrade
the-loop upgrade · components: cli, claude, cursor · scope: user · marketplace: MadaraUchiha-314/the-loop
Component  Outcome  Step                              Command / file
---------  -------  --------------------------------  ------------------------------------------------
cli        applied  upgrade the the-loopy-one CLI     /usr/bin/uv tool upgrade the-loopy-one
claude     applied  refresh the the-loop marketplace  claude plugin marketplace update the-loop
claude     applied  update the-loop@the-loop          claude plugin update the-loop@the-loop --scope user
cursor     applied  update the Cursor plugin checkout /usr/bin/git -C ~/.cursor/plugins/local/the-loop pull --ff-only
```

Same command as [`install`](/cli/commands/install) — same components, flags, outcomes,
scopes and exit codes — with the upgrade path of each installer instead of its install
path. Read that page for the mechanics; this one covers only what differs.

## What differs

- **The CLI is upgraded with the installer that owns it.** `uv tool upgrade`, `pipx
  upgrade`, or `pip install --upgrade`, chosen by where the running package actually
  lives. That is the point of the command: [issue-78](https://github.com/MadaraUchiha-314/the-loop/issues/78)
  was a CLI that kept reporting an old version because nobody remembered which installer
  had put it there.
- **The marketplace is refreshed first.** `plugin marketplace update the-loop` runs before
  `plugin update the-loop@the-loop`, so the update resolves against the current manifest
  rather than a cached one.
- **A source checkout is skipped**, naming the checkout: a development install is updated
  with `git pull` (and `uv sync`), not by installing a release over it.
- **An upgrade never becomes an install.** Where Cursor takes the
  [local-clone route](/cli/commands/install#cursor-the-same-probe-a-different-fallback),
  `upgrade` runs `git -C … pull --ff-only` on an existing checkout and reports `skipped`
  when there is none — naming `the-loop install cursor` rather than quietly creating one.

Both harnesses apply a plugin update on the **next** session — restart the harness after
an upgrade.

## After upgrading the plugin

An upgraded plugin does not update the projects it is used on: a release may add managed
files or change a config schema. Run `/the-loop:upgrade-the-loop` inside a project to
reconcile it — the two commands are named alike because they are the two halves of the
same "move to the current version" job:

| | Moves | Run from |
|---|---|---|
| `the-loop upgrade` | the software (CLI, plugin) | your terminal |
| `/the-loop:upgrade-the-loop` | a project's `.the-loop/` files and schemas | inside a session |

## See also

- [`install`](/cli/commands/install) — the full mechanics, scopes and security notes.
- [Installing the CLI](/cli/installation) · [decision-057](/decisions/decision-057) ·
  [decision-064](/decisions/decision-064)
