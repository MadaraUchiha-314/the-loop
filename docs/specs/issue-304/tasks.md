---
type: tasks
phase: tasks-breakdown
workItem: "issue-304"
status: locked
approvedBy: []
overrides: {}
---

# Tasks: one Slack surface, two identity allow-lists

> Phase 3 of 3. Small, verifiable tasks; each `_Test:_` names a row of
> `testing-plan.md`.

## Task list

- [x] 1. Retire the collaborator notification shape in the schema
  - `.the-loop/collaborators.schema.json`: drop `$defs/notificationChannel` and
    `collaborator.notifications`; rewrite the file description, the `collaborator`
    description and the `roles` description so none of them describes delivery.
  - _Depends on:_ none
  - _Requirements:_ R1.1, R1.3
  - _Test:_ `T1`

- [x] 2. Retire the CLI config's collaborators/notifications blocks in the schema
  - `.the-loop/cli-config.schema.json`: drop both top-level properties.
  - _Depends on:_ none
  - _Requirements:_ R2.1
  - _Test:_ `T2, T5`

- [x] 3. Name the replacement when a retired key is refused
  - `cli/the_loop/configschema.py`: `RETIRED` table + the normalise-and-look-up in
    `_check_object`'s unknown-key branch.
  - Security-relevant (abuse case A2): the message is the mitigation for silent drop.
  - _Depends on:_ 1, 2
  - _Requirements:_ R1.2, R2.2
  - _Test:_ `T1, T2`

- [x] 4. The fifth retirement in the migration ledger
  - `cli/the_loop/migrations.py`: `CURRENT_CONFIG_VERSION` → `0.6.0`; site constant,
    `needs_migration` probe, `assert_current` refusal, `migrate_cli_config` removal + note.
  - Security-relevant (abuse cases A1, A3): the probe is by key, not by version, and the
    removal touches only the two named top-level keys.
  - _Depends on:_ 2
  - _Requirements:_ R2.2, R3.1, R3.2, R3.3, R3.4
  - _Test:_ `T3, T4`

- [x] 5. Copy the schemas into the package
  - `cli/the_loop/schemas/{cli-config,collaborators}.schema.json`: byte-identical.
  - _Depends on:_ 1, 2
  - _Requirements:_ NFR1
  - _Test:_ `T8`

- [x] 6. Clean the shipped templates and this repo's own configs
  - `skills/the-loop/templates/{cli-config,collaborators}.yaml`,
    `.the-loop/cli-config.yaml` (version `0.6.0`), `.the-loop/collaborators.yaml` —
    commented examples included.
  - _Depends on:_ 1, 2
  - _Requirements:_ R4.1
  - _Test:_ `T9`

- [x] 7. Tests
  - `cli/tests/test_configschema.py`, `cli/tests/test_migrations.py`,
    `cli/tests/test_core_config.py`: the refusals, the round trip, the allow-list
    assertions, and the two re-pointed `$ref` assertions.
  - _Depends on:_ 3, 4
  - _Requirements:_ every R
  - _Test:_ `T1–T5`

- [x] 8. Docs: stop promising per-collaborator delivery
  - `skills/the-loop/reference/collaboration.md`, `docs/config/cli/observability-options.md`,
    `docs/config/cli/index.md`, `docs/config/harness-config.md`,
    `commands/upgrade-the-loop.md`.
  - _Depends on:_ 2
  - _Requirements:_ R4.2, R4.4
  - _Test:_ `T8, T10`

- [x] 9. Capability doc + history row
  - `docs/capabilities/channels.md`.
  - _Depends on:_ 8
  - _Requirements:_ R4.3
  - _Test:_ `T10`

- [x] 10. Verify
  - Full `pytest`, `ruff`, `pyright`, `scripts/validate_config.py`, markdownlint; record
    in `evidence/verification.md` and complete `testing-plan.md`.
  - _Depends on:_ 1–9
  - _Requirements:_ NFR1, NFR2
  - _Test:_ `T6, T7, T8, T9, T11`
