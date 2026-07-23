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
   (`${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json`; in Cursor,
   `.cursor-plugin/plugin.json` under the plugin's install directory —
   `${CLAUDE_PLUGIN_ROOT}` below means that same plugin root).

2. **Reconcile files.** Using `${CLAUDE_PLUGIN_ROOT}/.the-loop/manifest.yaml` as the
   source of truth:
   - Create any missing managed files / directories.
   - Never clobber user-owned files (`managed: false`) — diff and suggest changes
     instead.
   - Templates are **internal to the-loop** and are **not** materialized in the project;
     read them from `${CLAUDE_PLUGIN_ROOT}/skills/the-loop/templates/`
     (`manifest.templatesDir`) rather than creating a `.the-loop/templates/` folder.

3. **Clean up deprecated paths.** For each entry under `manifest.deprecated`, if the path
   is present in the project, remove it — this is how projects initialized by older
   versions shed the duplicated, internal-only artifacts (notably
   `.the-loop/templates/`, superseded by the plugin's own skill templates in issue #36).
   If a user has clearly added their own files under a deprecated path, surface them in
   the report and confirm before deleting rather than removing silently.

4. **Migrate schema.** If `.the-loop/config.schema.json` changed, update the project's
   copy and migrate `.the-loop/config.yaml` to the new shape (add new keys with
   defaults, flag removed/renamed keys for the user — e.g. template paths that used to
   point under `.the-loop/templates/`). Validate the result. If the project also
   scaffolded `.the-loop/cli-config.yaml` (the operator opted into a repo-local CLI
   config at init time — decision-032), migrate its schema copy the same way; never
   scaffold it now if the project never had one (that's the operator's `/init`-time
   choice, not upgrade's to make).

5. **Update manifest.** Bump `theLoopVersion`/`manifestVersion` to match the plugin.

6. **Report.** Summarize grouped as **created / skipped (up to date) / drifted
   (suggested) / removed (deprecated) / migrated / needs-user**. Make no silent
   breaking changes.

`--dry-run` computes and prints the report above **without writing anything** — the same
preview `/the-loop:init --dry-run` gives. Idempotent, non-clobbering, and safe to re-run.
