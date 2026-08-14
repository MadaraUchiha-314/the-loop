# Decision 080: the-loop's config schemas ship with the plugin, not with your repo

- **Status:** proposed
- **Date:** 2026-08-14
- **Deciders:** @MadaraUchiha-314 (owner), the-loop (engineer)
- **Work item:** [issue-220](https://github.com/MadaraUchiha-314/the-loop/issues/220)

## Context

`/the-loop:init` copied the-loop's own JSON schemas into every repository it initialized:
`harness-config.schema.json` (57 KB), `collaborators.schema.json` (5 KB), and
`cli-config.schema.json` (56 KB) for operators tracking the CLI config in the repo. Up to
118 KB of the harness's internals, checked in next to the operator's actual configuration
— visible on [Konoha-14/morsel](https://github.com/Konoha-14/morsel/tree/main/.the-loop),
which is what raised the ticket.

Nothing needed the copy. The plugin ships the schemas; the CLI never loads one at runtime
(`harness_config.READS` reads keys, not JSON Schema); and the only readers — `/init` and
`/upgrade` — run *inside* the plugin, where `${CLAUDE_PLUGIN_ROOT}` already resolves. The
copy's one real effect was staleness: it froze at whichever plugin version wrote it, so
`/upgrade` had to re-copy bytes nobody had edited, and a schema change arrived in a
project as a 57 KB machine-generated diff.

[Decision-002](decision-002.md) established the schema as the thing "the plugin owns and
exposes", and issue-36 had already drawn this exact line for templates: internal to the
plugin, read from `${CLAUDE_PLUGIN_ROOT}`, never materialized per project. The schemas
were the last internal asset on the wrong side of it.

## Decision

**The schemas are plugin assets. A project keeps only what its operator wrote.**

1. **One declared home.** `.the-loop/manifest.yaml` gains `schemasDir` (plugin-root
   relative, `.the-loop`), mirroring `templatesDir`. Every command that validates a config
   or drives the `x-onboarding` walkthrough resolves the schema through it, **from disk** —
   never over the network, never from a project copy.
2. **`/init` writes no schema.** The three paths leave the manifest's `meta` list. The
   opt-in `.the-loop/cli-config.yaml` is scaffolded alone.
3. **`/upgrade` sheds the copies.** The three paths join `manifest.deprecated` with
   reasons that mark them *safe to delete, not a migration*, so the cleanup step that
   already retired `.the-loop/templates/` retires these too. Deletion is name-driven and
   closed: only the exact declared paths, never one resolving outside the project's
   `.the-loop/`, and a copy that differs from the plugin's is reported before it is
   removed — somebody may have been relying on the edit.
4. **The editor keeps its validation.** Every scaffolded config opens with
   `# yaml-language-server: $schema=<published raw url>` on its **first line**, where the
   directive is honoured. It is a comment: the loop never reads it, so a tampered URL
   reaches nothing the loop does, and an operator who deletes the line loses completion
   while typing and nothing else. Because adoption (issue-193) prepends a provenance
   header to the packaged default, `harness_config.scaffold()` now places that header
   *below* a leading modeline rather than above it.
5. **The URL tracks `main`, not a release tag.** A pinned tag would freeze an operator's
   editor at whichever plugin version happened to run `/init` — the same staleness this
   decision removes, moved one layer out. The cost is that an editor may briefly know a
   key the installed plugin does not; the loop's own validation, which is the one that
   gates anything, always reads the installed plugin's file.
6. **The schemas stay in this repository's `.the-loop/`.** It doubles as the plugin's
   shipped directory, and every existing reference, test and CI step already resolves
   there. `schemasDir` makes the location explicit without moving a byte.

## Cost

- **A project loses offline schema validation of its own config outside the loop.** A tool
  that opened `.the-loop/harness-config.schema.json` by path finds nothing. Accepted:
  `/init` and `/upgrade` still validate locally, and the modeline covers the editor case.
- **`/upgrade` now deletes files from operators' repositories.** New authority, bounded by
  the three declared names, the escape check and the report-the-difference rule. Leaving a
  stale copy costs 57 KB; deleting the wrong file is unrecoverable, so the ambiguous case
  fails closed to **needs-user**.
- **An editor reaches out to `raw.githubusercontent.com`.** An operator in an air-gapped
  environment sees a failed schema fetch in their editor. Nothing else degrades, and the
  line is a comment they can delete.
- **A `main`-tracking URL can describe an unreleased key.** Bounded to editor
  autocompletion (cost 5); the gate never consults it.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Keep copying the schemas | The problem statement. Stale by construction, and it puts the plugin's contract in the operator's diff |
| Copy them but `.gitignore` them | Still 118 KB per checkout, still stale, and a config the operator *can't* commit validation for is worse than one they don't have to |
| Move the schemas to a top-level `schemas/` in this repo | A large rename touching every reference, test and CI step, for no user-visible gain; `schemasDir` names the location without moving anything |
| Pin the modeline URL to the released tag | Freezes the operator's editor at install time — the staleness this decision exists to remove |
| No modeline at all | A strict loss for anyone who had editor validation; one comment line is a far cheaper replacement than 57 KB of JSON |
| Publish to SchemaStore for automatic association | A registry submission and an external dependency for a plugin-scoped file; the raw URL answers the same need today |
| Validate at runtime in the Python CLI against the shipped schema | A new dependency on a hot path to solve a problem nobody has — the CLI reads keys and degrades to defaults by design |
