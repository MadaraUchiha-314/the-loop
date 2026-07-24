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

4. **Migrate schemas.** the-loop has **three** independent config schemas — the per-repo
   **harness (plugin)** config (`.the-loop/harness-config.schema.json` ↔ `.the-loop/harness-config.yaml`),
   the per-repo **collaborators** file (`.the-loop/collaborators.schema.json` ↔
   `.the-loop/collaborators.yaml`, issue-82/decision-035) and the
   **CLI daemon** config (`.the-loop/cli-config.schema.json` ↔ `.the-loop/cli-config.yaml`,
   decision-032). Check each one **independently**: a release may change only one of them
   (e.g. a new `webhooks.ghWebhook.routing.*` key touches only the CLI schema), so never
   gate the CLI-config migration on the plugin schema having changed.

   **Rename migration (issue-82, decision-035):** if the project still has
   `.the-loop/config.yaml` / `.the-loop/config.schema.json` (the pre-rename names),
   `git mv` the config to `.the-loop/harness-config.yaml` preserving every user value,
   replace the schema with the current `.the-loop/harness-config.schema.json`, and then
   migrate the retired people keys: move each `personas` entry into
   `.the-loop/collaborators.yaml` as a collaborator (creating the file from
   `templates/collaborators.yaml` if absent), fold any `messaging.channels` targets into
   a collaborator `notifications.channels` entry (`type: slack` → a slack channel with
   its target in `config.channel-list`; flag `whatsapp`/`email` entries with
   `# TODO: verify` — those types are not supported yet), add the template's default
   `notifications` event filters to harness-config.yaml, and re-validate all three
   files. Report this migration explicitly so the operator sees exactly what moved
   where.

   For **either** schema, when it changed, update the project's copy of that schema file
   and migrate the corresponding config file to the new shape:
   - **Add new keys with defaults.** This is the common case and covers purely additive,
     opt-in keys — e.g. `routing.workspace` (issue-76): add it with `root: ""` (disabled)
     so nothing changes for an operator who doesn't set it, and `spawnWorkdir` keeps its
     existing meaning.
   - For a removed/renamed key whose data has no real operational value (e.g. a stale
     template path that used to point under `.the-loop/templates/`), flag it for the
     user with a `# TODO: verify` comment and move on.
   - For a removed key that carries live operational settings, **migrate the data, do
     not just flag and drop it.** Concretely (decision-032, issue-63): if
     `.the-loop/harness-config.yaml` still carries `webhooks` and/or `polling` and/or
     `observability.eventLog` (the pre-split shape), that block configures the running
     webhook receiver/poller and losing it silently would break routing. Extract it,
     rename `observability.eventLog` → the CLI config's top-level `eventLog`, and ask
     the same yes/no question `/the-loop:init` asks (Requirement 2.4): scaffold it at
     `.the-loop/cli-config.yaml` (repo-tracked) or print the extracted block for the
     operator to place at `~/.the-loop/cli-config.yaml` themselves. Either way, validate
     it against `.the-loop/cli-config.schema.json`, THEN strip `webhooks`/`polling`/
     `observability.eventLog` from `.the-loop/harness-config.yaml` and re-validate it against
     the trimmed `.the-loop/harness-config.schema.json`. Report this migration explicitly (not
     folded into a generic "drifted" line) so the operator sees exactly what moved
     where. Also flag `routing.authorizedUsers` / any poll source's `repos` if they were
     empty and relying on the now-removed `ticketing.github` fallback (Requirement 4) —
     those need an explicit value in the new CLI config or the daemon fails closed.

   Validate each migrated file against its schema. The CLI config is opt-in: only migrate
   `.the-loop/cli-config.yaml` if the project already had one (scaffolded at a previous
   init/upgrade). Never scaffold one now if the project never had one and step 4's data
   migration didn't just create it (that's the operator's choice, not upgrade's to make
   unprompted).

5. **Update manifest.** Bump `theLoopVersion`/`manifestVersion` to match the plugin.

6. **Report.** Summarize grouped as **created / skipped (up to date) / drifted
   (suggested) / removed (deprecated) / migrated / needs-user**. Make no silent
   breaking changes.

`--dry-run` computes and prints the report above **without writing anything** — the same
preview `/the-loop:init --dry-run` gives. Idempotent, non-clobbering, and safe to re-run.
