---
description: Reconcile a project's "the-loop" files with the installed plugin version — create missing files and migrate schemas. Idempotent, non-clobbering, with --dry-run.
argument-hint: "[--dry-run]"
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

5. **Report.** Summarize grouped as **created / skipped (up to date) / drifted
   (suggested) / migrated / needs-user**. Make no silent breaking changes.

`--dry-run` computes and prints the report above **without writing anything** — the same
preview `/the-loop:init --dry-run` gives. Idempotent, non-clobbering, and safe to re-run.
