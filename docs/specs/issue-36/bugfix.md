---
type: bugfix
phase: requirements-definition
workItem: issue-36
status: approved
approvedBy: ["@MadaraUchiha-314"]
severity: medium
collaborators: [engineer]
overrides: {}
---

# Bugfix spec: the-loop duplicates its internal templates into every project

> Phase 1 of 3 for a bug (bugfix → design → tasks).

## Summary

When `/the-loop:init` runs in a project, it copies the whole template set into that
project's `.the-loop/templates/` directory (e.g.
<https://github.com/MadaraUchiha-314/alter-ego/tree/main/.the-loop/templates>). These
templates are **internal to the-loop** — the harness reads them when it authors an
artifact — so materializing them in every consuming repo produces duplicated, noisy,
never-edited files that drift from the plugin's own copy. Tracked as
[issue #36](https://github.com/MadaraUchiha-314/the-loop/issues/36).

## Steps to reproduce

1. Install the-loop as a plugin.
2. Run `/the-loop:init` in a fresh project repository.
3. Inspect the project: `.the-loop/templates/` now holds ~18 copied template files that
   the user never authored and does not maintain.

## Expected vs actual

- **Expected:** `/the-loop:init` scaffolds only the project's own artifacts (config,
  manifest, user-owned registries, docs/learnings skeleton). Templates stay inside the
  plugin and are read from there when needed.
- **Actual:** the whole template set is duplicated into `.the-loop/templates/` in every
  project the-loop is initialized in.

## Root cause (confirmed)

`.the-loop/manifest.yaml` listed the templates under a `templates:` section and
`commands/init.md` step 2 instructed init to create `.the-loop/templates/` in the target
repo. Commands and config referenced templates by the repo-relative path
`.the-loop/templates/...`, which only resolves because init had copied them in.

## Acceptance criteria (EARS)

1. WHEN `/the-loop:init` runs in a project THEN the system SHALL NOT create a
   `.the-loop/templates/` directory in that project.
2. The templates SHALL live with the plugin under `skills/the-loop/templates/` and be
   read from `${CLAUDE_PLUGIN_ROOT}` when an artifact is authored.
3. WHEN `/the-loop:upgrade-the-loop` runs on a project that an older version scaffolded a
   `.the-loop/templates/` folder into THEN the system SHALL remove that folder, confirming
   first only if the user added their own files under it.
4. All command/skill/config references to templates SHALL point at the internal
   `skills/the-loop/templates/` location; runtime consumers with a built-in fallback (the
   webhook dispatcher) SHALL keep working when the path is absent in a project repo.

## Out of scope

- Restructuring the artifact chain or the templates' contents.
- Changing how user-owned files (`config.yaml`, `collaborators.yaml`,
  `external-tools.md`) are scaffolded — these are still created per project, just read
  from the internal template location.

## Open questions

None.
