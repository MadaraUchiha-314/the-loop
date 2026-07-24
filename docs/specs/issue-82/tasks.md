---
type: tasks
phase: tasks-breakdown
workItem: "issue-82"
status: approved
approvedBy: ["@MadaraUchiha-314"]
overrides: {}
---

# Tasks: make the notification/escalation mechanism coherent

> Phase 3 of 3 (requirements → design → tasks).
>
> **Provenance note (paper trail):** authored retroactively during PR #83 review (see
> requirements.md). All tasks below shipped in PR #83's single commit; checkmarks
> reflect the delivered state, and each task's proof is listed as executed.

## Task list

- [x] 1. Author `collaborators.schema.json` + rewrite `templates/collaborators.yaml`
  - `$defs/collaborator` + `$defs/notificationChannel` (per-user/per-channel enabled,
    `type: slack`, `via: mcp|cli|api`, slack `channel-list`)
  - _Depends on:_ none — _Requirements:_ R1
  - _Test:_ `scripts/validate_config.py` validates `.the-loop/collaborators.yaml` +
    template against the new schema (run: VALID)
- [x] 2. Rename plugin config → `harness-config.{yaml,schema.json}` (repo + template),
  drop `personas`/`messaging`, add `notifications.events` (harness taxonomy → roles),
  update `x-onboarding`
  - _Depends on:_ 1 — _Requirements:_ R2, R4
  - _Test:_ `scripts/validate_config.py` (run: VALID both files)
- [x] 3. Migrate this repo's own `personas` entry into a real
  `.the-loop/collaborators.yaml` (dogfooding; notifications `enabled: false` until a
  channel-list is filled)
  - _Depends on:_ 1, 2 — _Requirements:_ R1
  - _Test:_ `scripts/validate_config.py` (run: VALID)
- [x] 4. cli-config: add `collaborators` via cross-file `$ref` + daemon-side
  `notifications.events`; extend repo copy + template
  - _Depends on:_ 1 — _Requirements:_ R3
  - _Test:_ ref-store probe — valid collaborator accepted, entry missing `roles`
    rejected through the `$ref` (run: passed); `scripts/validate_config.py` (VALID)
- [x] 5. `scripts/validate_config.py`: third schema target + local ref store;
  `hooks/hooks.json` + CI json-sanity list updated
  - _Depends on:_ 1, 2, 4 — _Requirements:_ R1.5, NFR
  - _Test:_ `make validate` (run: 6× VALID)
- [x] 6. `scenarios.py`: read `harness-config.yaml` with pre-rename fallback
  - _Depends on:_ 2 — _Requirements:_ R4.3
  - _Test:_ `cli/tests/test_cli.py::test_load_config_globs_prefers_harness_config_with_config_yaml_fallback`
    (red→green; run: passed)
- [x] 7. Rename sweep through living files only (commands, skills, README, CLAUDE.md,
  docs site, capability docs, manifest); historical records untouched
  - _Depends on:_ 2 — _Requirements:_ R4.1
  - _Test:_ `grep` audit — zero stray `personas`/`messaging`/`config.yaml` refs in
    living files (run: clean); `markdownlint` (run: 0 errors)
- [x] 8. Migration path: `manifest.deprecated` entries + `upgrade-the-loop.md`
  migration section; `collaborators.yaml` → `managed: true`
  - _Depends on:_ 2, 3 — _Requirements:_ R4.2
  - _Test:_ manifest YAML parses; upgrade doc names every moved key (reviewed)
- [x] 9. Paper trail + docs: decision-035 (+ index), `collaboration.md` rewrite,
  `docs/reference/configuration.md`, `cli/README.md` config tables,
  `docs/capabilities/cli.md` history
  - _Depends on:_ 1–8 — _Requirements:_ R1–R4
  - _Test:_ `markdownlint` (run: 0 errors)
- [x] 10. Full gate: `make check`
  - _Depends on:_ all — _Requirements:_ NFR
  - _Test:_ ruff + markdownlint + ruff-format + pyright + validate + pytest
    (run: 257 passed)
