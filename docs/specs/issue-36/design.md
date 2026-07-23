---
type: design
phase: design
workItem: issue-36
status: approved
approvedBy: ["@MadaraUchiha-314"]
overrides: {}
---

# Design: templates become internal to the-loop

> Phase 2 of 3 (bugfix → design → tasks). Derives from the approved bugfix spec.

## Overview

Move the template set out of the per-project footprint and into the plugin's skill, then
repoint every reference at the internal location and teach `init`/`upgrade` about the
change. Nothing about how an artifact is authored changes — only *where the template is
read from* and *what lands in a consuming repo*.

## Architecture

Templates were being treated as two things at once: (a) plugin-internal source that the
harness reads to author artifacts, and (b) per-project managed files listed in the
manifest and materialized by `init`. This bug is the (b) half. The fix collapses them to
just (a):

```
${CLAUDE_PLUGIN_ROOT}/skills/the-loop/templates/   <- the single, internal home
```

- The plugin ships one copy of the templates inside the `the-loop` skill (Agent Skills
  bundles supporting files alongside `SKILL.md`).
- `manifest.templatesDir` records that location so tooling resolves it from one place.
- `manifest.deprecated` records `.the-loop/templates/` as a path older versions created,
  driving upgrade's cleanup.

See [`docs/architecture/architecture.md`](../../architecture/architecture.md) §1
(Distribution) — the templates bullet now lives there, not under §2 (Project footprint).

## Components & interfaces

- **`skills/the-loop/templates/`** — the moved template set (was `.the-loop/templates/`).
- **`.the-loop/manifest.yaml`** — drops the `templates:` per-project list; gains
  `templatesDir` and a `deprecated` list.
- **`commands/init.md`** — scaffolds files *from* the internal templates but no longer
  copies the templates directory into the project.
- **`commands/upgrade-the-loop.md`** — new "clean up deprecated paths" step removes
  `.the-loop/templates/`; report gains a **removed (deprecated)** group.
- **Commands / skill / reference docs** — every `${CLAUDE_PLUGIN_ROOT}/.the-loop/templates/…`
  and bare `.the-loop/templates/…` reference repoints to `skills/the-loop/templates/…`.
- **`cli/the_loop/webhook/dispatcher.py`** — default template path constants and the
  "kept in sync with" comments point at the new location; the built-in
  `DEFAULT_PROMPT_TEMPLATE` / `DEFAULT_SPAWN_TEMPLATE` remain the source of truth in a
  project repo (the path is absent there, so the dispatcher falls back — unchanged
  behaviour).
- **`config.schema.json` / `config.yaml` (+ template config)** — `templatePath`,
  `promptTemplate`, `spawnPromptTemplate` defaults move to `skills/the-loop/templates/…`
  with descriptions clarifying they resolve under `${CLAUDE_PLUGIN_ROOT}` and are
  override-able.

## UI/UX design

N/A — packaging / CLI / docs change with no user-facing surface.

## Data models

`manifest.yaml` shape change only:

- removed: `templates:` (list of per-project template paths).
- added: `templatesDir: skills/the-loop/templates` (plugin-relative).
- added: `deprecated: [{ path, role, reason, removeIn }]`.

## Error handling

The webhook dispatcher already guards a missing template file (`_load_template` returns
the built-in default and logs at debug). Because a project repo will not contain
`skills/the-loop/templates/…`, that fallback path is the normal case there and keeps the
receiver working. Upgrade's cleanup confirms before deleting when the user has added
their own files under a deprecated path.

## Testing strategy

Primarily a docs/packaging change verified by inspection and the existing suite:

- `ruff`, `pyright`, `pytest` stay green — the dispatcher change is limited to default
  path constants/comments; no behavioural test change (built-in fallback already covered).
- `markdownlint` stays green across the edited docs.
- Manual verification: `rg "\.the-loop/templates"` returns only intentional references
  (the deprecated-path entry in the manifest and upgrade command, plus historical
  per-work-item spec/decision records that are immutable deltas).

## Trade-offs & decisions

- **Home = `skills/the-loop/templates/`** (inside the skill) rather than a new top-level
  `templates/` dir, matching the issue's "artifacts within skills that the-loop has" and
  the Agent Skills convention of bundling supporting files with the skill.
- **Keep the webhook/pr-briefing template *files*** in the plugin (not only the Python
  constants) so they remain readable/override references; the dispatcher's built-in
  defaults stay the runtime source of truth.
- **Data-driven cleanup** via `manifest.deprecated` rather than hard-coding the path in
  the upgrade command, so future removals reuse the same mechanism.

## Open questions

None.
