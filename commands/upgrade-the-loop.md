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
   copy and migrate `.the-loop/config.yaml` to the new shape:
   - Add new keys with defaults.
   - For a removed/renamed key whose data has no real operational value (e.g. a stale
     template path that used to point under `.the-loop/templates/`), flag it for the
     user with a `# TODO: verify` comment and move on.
   - For a removed key that carries live operational settings, **migrate the data, do
     not just flag and drop it.** Concretely (decision-032, issue-63): if
     `.the-loop/config.yaml` still carries `webhooks` and/or `polling` and/or
     `observability.eventLog` (the pre-split shape), that block configures the running
     webhook receiver/poller and losing it silently would break routing. Extract it,
     rename `observability.eventLog` → the CLI config's top-level `eventLog`, and ask
     the same yes/no question `/the-loop:init` asks (Requirement 2.4): scaffold it at
     `.the-loop/cli-config.yaml` (repo-tracked) or print the extracted block for the
     operator to place at `~/.the-loop/cli-config.yaml` themselves. Either way, validate
     it against `.the-loop/cli-config.schema.json`, THEN strip `webhooks`/`polling`/
     `observability.eventLog` from `.the-loop/config.yaml` and re-validate it against
     the trimmed `.the-loop/config.schema.json`. Report this migration explicitly (not
     folded into a generic "drifted" line) so the operator sees exactly what moved
     where. Also flag `routing.authorizedUsers` / any poll source's `repos` if they were
     empty and relying on the now-removed `ticketing.github` fallback (Requirement 4) —
     those need an explicit value in the new CLI config or the daemon fails closed.
   Validate the result. If the project already had a `.the-loop/cli-config.yaml`
   (scaffolded at a previous init/upgrade), migrate its schema copy the same way; never
   scaffold one now if the project never had one and step above didn't just create it
   (that's the operator's choice, not upgrade's to make unprompted).

5. **Update manifest.** Bump `theLoopVersion`/`manifestVersion` to match the plugin.

6. **Report.** Summarize grouped as **created / skipped (up to date) / drifted
   (suggested) / removed (deprecated) / migrated / needs-user**. Make no silent
   breaking changes.

`--dry-run` computes and prints the report above **without writing anything** — the same
preview `/the-loop:init --dry-run` gives. Idempotent, non-clobbering, and safe to re-run.
