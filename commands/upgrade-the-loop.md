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
   - Templates and config **schemas** are **internal to the-loop** and are **not**
     materialized in the project; read them from
     `${CLAUDE_PLUGIN_ROOT}/skills/the-loop/templates/` (`manifest.templatesDir`) and
     `${CLAUDE_PLUGIN_ROOT}/.the-loop/*.schema.json` (`manifest.schemasDir`) rather than
     creating a `.the-loop/templates/` folder or a `.the-loop/*.schema.json` copy
     (issue-220).

3. **Clean up deprecated paths.** For each entry under `manifest.deprecated`, if the path
   is present in the project, act on it — this is how projects initialized by older
   versions shed the duplicated, internal-only artifacts: `.the-loop/templates/`,
   superseded by the plugin's own skill templates (issue #36), and the three
   `.the-loop/*.schema.json` copies, superseded by the plugin's own schemas (issue #220 —
   up to 118 KB of the-loop's internals per repository).
   **Read the entry's `reason` first:** an entry whose reason describes a MIGRATION
   (e.g. `.the-loop/config.yaml`, renamed in issue-82) is **never deleted here** — it is
   handled by step 4's rename migration, which preserves the data; only remove a path
   whose reason marks it as safe-to-delete. If a user has clearly added their own files
   under a deprecated path, surface them in the report and confirm before deleting rather
   than removing silently.
   - **Only the exact paths the manifest names.** A candidate that resolves outside the
     project's `.the-loop/` directory — a symlink, a `..` segment, an absolute path — is
     **refused and reported**, never deleted. Removal is name-driven; it is never
     inferred from a pattern.
   - **A schema copy that differs from the plugin's shipped schema is a signal.** Diff it
     before removing and say so in the report — somebody may have been relying on a local
     edit, and this is their one chance to find out. If you cannot establish that a file
     is a the-loop schema copy, leave it and report it under **needs-user**.

4. **Migrate configs to the current schemas.** the-loop has **three** independent config
   schemas, all of them the **plugin's** (`manifest.schemasDir`) — the per-repo
   **harness (plugin)** config (`harness-config.schema.json` ↔ `.the-loop/harness-config.yaml`),
   the per-repo **collaborators** file (`collaborators.schema.json` ↔
   `.the-loop/collaborators.yaml`, issue-82/decision-035) and the
   **CLI daemon** config (`cli-config.schema.json` ↔ `.the-loop/cli-config.yaml`,
   decision-032). What migrates is the **project's config file**; the schema itself is
   never written into the project (issue-220). Check each one **independently**: a release
   may change only one of them (e.g. a new `routing.*` key touches only the CLI schema),
   so never gate the CLI-config migration on the plugin schema having changed.

   **Rename migration (issue-82, decision-035):** if the project still has
   `.the-loop/config.yaml` (the pre-rename name),
   `git mv` the config to `.the-loop/harness-config.yaml` preserving every user value,
   delete any leftover `.the-loop/config.schema.json` without replacing it (step 3), and
   then migrate the retired people keys: move each `personas` entry into
   `.the-loop/collaborators.yaml` as a collaborator (creating the file from
   `templates/collaborators.yaml` if absent) with its `handle`, `kind` and `roles` only,
   add the template's default `notifications` event filters to harness-config.yaml, and
   re-validate all three files. Report this migration explicitly so the operator sees
   exactly what moved where.

   Any `messaging.channels` targets are **not** folded into a collaborator: per-person
   notification config was retired in issue-304 because nothing ever read it. Slack is
   declared once, for the whole daemon, under the CLI config's `channels.slack` — tell
   the operator what their old targets were and point them there, rather than writing a
   shape the schema now refuses.

   **Retired-block migration (issue-304):** if `.the-loop/cli-config.yaml` still carries
   a top-level `collaborators` or `notifications` block, or a collaborator in
   `.the-loop/collaborators.yaml` still carries a `notifications` sub-object, those are
   the unread shapes. Run `the-loop migrate-config` for the CLI config (it removes both
   blocks and bumps the version, idempotently, keeping a `.bak`); strip the collaborator
   sub-object by hand and report what it said, since no code ever acted on it. The
   runtime refuses a CLI config that still declares either block, so this is not
   optional cleanup.

   For **any** of the three schemas, when it changed, migrate the corresponding config
   file to the new shape (there is no project copy of the schema to update — read the
   plugin's):
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
     it against the plugin's `cli-config.schema.json`, THEN strip `webhooks`/`polling`/
     `observability.eventLog` from `.the-loop/harness-config.yaml` and re-validate it against
     the trimmed `harness-config.schema.json`. Report this migration explicitly (not
     folded into a generic "drifted" line) so the operator sees exactly what moved
     where. Also flag `routing.authorizedUsers` / any poll source's `repos` if they were
     empty and relying on the now-removed `ticketing.github` fallback (Requirement 4) —
     those need an explicit value in the new CLI config or the daemon fails closed.

   **The learnings tree moved into `docs/` (issue-224, decision-082).** `workflow.learningsDir`
   is a new, additive harness-config key whose default is `docs/learnings` — where the old
   hardcoded location was `learnings/` in the project root. The key itself is the ordinary
   add-with-defaults case; **the directory is not**, because it holds the operator's data.
   So when the project carries a root-level `learnings/` and no `workflow.learningsDir`,
   present both supported outcomes and take neither on your own:
   - **Move it** — `git mv learnings docs/learnings` (or wherever the project's docs live),
     fix the relative links inside the moved files, and leave `learningsDir` at its
     default (or set it to the chosen directory).
   - **Pin it** — add `workflow.learningsDir: learnings` and change nothing on disk.

   **Never move or delete a learnings tree without the operator's confirmation**, and if
   they do not answer, leave it exactly as it is and report it under **needs-user**: an
   un-migrated tree is a directory the loop stops reading, which is recoverable; a
   relocated one they did not ask for is a diff they did not expect. This entry is
   deliberately **not** in `manifest.deprecated` — everything there is safe-to-delete
   plugin internals, and these files are neither.

   **Execution control + one state root (issue-106, decision-040).** Two purely
   additive CLI-config blocks — `state` and `routing.control` —
   but one of them **changes runtime behaviour by default**, so this one is not the
   ordinary add-with-defaults case:
   - Add `state.root: .the-loop` and the `control` block (with the four default
     keywords) from `templates/cli-config.yaml`. Leave every existing explicit path
     (`routing.registryDir`, `polling.stateFile`, `eventLog.path`,
     `webhooks.ghWebhook.pidfile`) **exactly as it is** — the root only supplies
     defaults, so a config that names its paths keeps behaving identically.
   - **Report `control.requireStartCommand` as `needs-user`, never as a silent
     add.** Its default (`true`) means the auto-execute label alone no longer starts
     a session: an authorized user must comment `the-loop start` (issue-135; the
     pre-issue-135 default was `the-loop:start-execution`) (or run
     `the-loop sessions start`). Ask which the operator wants — keep the pre-issue-106
     behaviour (write `requireStartCommand: false`) or adopt the new gate (`true`) —
     and say what each means. Do not decide it for them.
   - If `polling.stateFile` is **unset** and a pre-issue-106 `.the-loop/poll-state.json`
     exists, *offer* to move it to `<state.root>/sessions/poll-state.json` (its new
     default home). Never move it silently, and never just delete it: the daemon keeps
     using a legacy file that exists (warning once), and an empty state file would
     re-baseline every watched thread and re-forward its whole comment history.
   - Note in the report that a **home-directory** CLI config (`~/.the-loop/cli-config.yaml`)
     is outside this command's reach: print the two blocks for the operator to paste, and
     say that leaving the file untouched is safe — both blocks are optional and the daemon
     falls back to the same defaults, `requireStartCommand: true` included (which is
     precisely why the decision above must be surfaced, not assumed).

   **Integrations + the first breaking CLI-config change (issue-109, decision-041).**
   Unlike everything above, this one **removes** keys and the CLI **refuses to start**
   until it is applied — a config that still declares a removed key is an error, never a
   silently ignored value (ignoring a setting the operator deliberately made would change
   their behaviour without telling them). Do not hand-migrate it: run
   `the-loop migrate-config --path <cli-config.yaml>` (`--dry-run` to preview), which is
   the same deterministic, idempotent key-move the runtime tests, and paste its report
   into the **migrated** group.
   - `webhooks.ghWebhook.routing.{control,reactions,announce}.ghBinary` (three copies of
     one setting) → **`integrations.github.cli.binary`**, declared once. WHEN the three
     copies disagree THEN the migration keeps the first and reports the conflict as
     **needs-user** — pick deliberately rather than inherit an accident.
   - `polling.stateFile` → **removed** (issue-128). The poller's ledger is now the `poll`
     section of each work item's record under `<state.root>/portable/`, so a file path has
     nothing to point at; `state.root` is the knob that replaced it. The old file keeps
     being READ until each work item is written forward, so nothing is re-forwarded — say
     so in the report, and offer to delete `<state.root>/sessions/` once the operator has
     confirmed `the-loop sessions list` looks right.
   - `webhooks.ghWebhook.routing` → **`routing`**, at the top level (issue-142). The block
     is moved key for key, nothing inside it changes, and `webhooks.ghWebhook` keeps only
     what is genuinely the receiver's (`host`, `port`, `path`, `secretEnv`, `pidfile`,
     `events`). It moved because the poller reads that same block verbatim for dispatch —
     the nesting claimed a scope it never had. WHEN a config declares **both** the old and
     the new block THEN the migration keeps the top-level value key by key and reports each
     one it dropped; surface those as **needs-user**, since a dropped `authorizedUsers`
     entry is a change to who may drive the daemon.
   - The config gains a top-level `version` (now `0.3.0`). Detection is by version, not by
     key-sniffing, so re-running is exact and cheap.
   - Add the `integrations` block from `templates/cli-config.yaml` if absent. Each provider
     takes `transport: auto|api|cli|sdk` — `auto` preserves today's behaviour, so an
     operator who does not care changes nothing. Only the Slack `sdk` transport needs the
     extra install (`pip install "the-loopy-one[slack]"`); the `webhook` transport is
     dependency-free.
   - A **home-directory** CLI config is outside this command's reach as usual — but here
     that matters more, because the CLI will refuse to start against it. Say so explicitly
     and print the migrated block for the operator to paste.

   Validate each migrated file against its schema, read from `manifest.schemasDir` under
   `${CLAUDE_PLUGIN_ROOT}` — locally, never over the network. The CLI config is opt-in: only migrate
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
