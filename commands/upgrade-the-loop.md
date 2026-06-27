---
description: Reconcile a project's "the-loop" files with the installed plugin version — create missing files and migrate schemas.
argument-hint: ""
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# the-loop: upgrade-the-loop

Updating the plugin from the marketplace does not guarantee that a project has all
the files (or the latest schema) that the current version of the-loop needs. This
command reconciles them.

## Steps

1. **Read versions.** Compare `theLoopVersion` in the project's
   `.the-loop/manifest.yaml` with the plugin's version
   (`${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json`).

2. **Reconcile files.** Using `${CLAUDE_PLUGIN_ROOT}/.the-loop/manifest.yaml` as the
   source of truth:
   - Create any missing managed files / templates / directories.
   - Never clobber user-owned files (`managed: false`) — diff and suggest changes
     instead.

3. **Migrate schema.** If `.the-loop/config.schema.json` changed, update the project's
   copy and migrate `.the-loop/config.yaml` to the new shape (add new keys with
   defaults, flag removed/renamed keys for the user). Validate the result.

4. **Update manifest.** Bump `theLoopVersion`/`manifestVersion` to match the plugin.

5. **Report.** Summarize what was created, migrated, or needs user attention. Make no
   silent breaking changes.

Idempotent and safe to re-run.
