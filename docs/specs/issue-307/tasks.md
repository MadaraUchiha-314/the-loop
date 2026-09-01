---
type: tasks
phase: tasks-breakdown
workItem: "issue-307"
status: locked
approvedBy: []
overrides: {}
---

# Tasks: per-work-item collaborators

> Phase 3 of 3. Small, verifiable tasks; each `_Test:_` names a row of `testing-plan.md`.

## Task list

- [x] 1. The roster, and its place in the portable record
  - `cli/the_loop/collaborators.py`: `normalize_login`, `parse_logins`, `CollaboratorRecord`,
    `CollaboratorStore` (`list`/`add`/`remove`/`is_collaborator`/`permits`/`clear`).
  - `cli/the_loop/workitem.py`: `COLLABORATORS` joins `SECTIONS` (no legacy fallback — the
    section did not exist before this work item).
  - Security-relevant (A3, A4): `normalize_login` _is_ the injection mitigation, and
    `permits` asking only about the refs it is given _is_ the scoping one.
  - _Depends on:_ none
  - _Requirements:_ R1.1–R1.5, R1.7, R3.7, R4.2
  - _Test:_ `T1, T2 — uv run pytest tests/test_collaborators.py`

- [x] 2. Two more words in the vocabulary
  - `cli/the_loop/control.py`: `ADD_COLLABORATOR`/`REMOVE_COLLABORATOR`, `COMMANDS`,
    `COLLABORATOR_COMMANDS`, `DEFAULT_KEYWORDS`; `ControlResult.subjects` and the
    login scan in `parse_command`; `command_comment(subject=…, invocation=…)`.
  - _Depends on:_ 1
  - _Requirements:_ R4.1, R4.3–R4.6, R5.2
  - _Test:_ `T3 — uv run pytest tests/test_control.py`

- [x] 3. Both schema copies, the template and this repo's own config
  - `.the-loop/cli-config.schema.json` and `cli/the_loop/schemas/cli-config.schema.json`
    (kept byte-identical), `skills/the-loop/templates/cli-config.yaml`,
    `.the-loop/cli-config.yaml`.
  - _Depends on:_ 2
  - _Requirements:_ R4.1, R4.6
  - _Test:_ `T11 — uv run pytest tests/test_configschema.py tests/test_config_schema_parity.py`

- [x] 4. The webhook ingress seam
  - `cli/the_loop/webhook/router.py`: `Router(collaborators=…)`; a comment from a granted
    login falls through the authorization guard and emits `routing.collaborator`.
  - `cli/the_loop/webhook/daemon.py`: inject the dispatcher's store, and keep it injected
    across a hot reload.
  - _Depends on:_ 1
  - _Requirements:_ R3.1
  - _Test:_ `T6 — uv run pytest tests/test_routing.py tests/test_webhook_routing_integration.py`

- [x] 5. The dispatcher: execute the two verbs, and refuse everything else
  - `cli/the_loop/webhook/dispatcher.py`: own a `CollaboratorStore`; branch
    `COLLABORATOR_COMMANDS` in `handle()`; `_apply_collaborator`; `collaborator-no-spawn`
    in `_spawn_refusal` + `SETTLED_SUPPRESSED`; clear the roster where the control record
    is cleared on closure.
  - Security-relevant (A1, A2, A6): the control seam's named-actor re-check becomes
    load-bearing, and the spawn seam gains the same one.
  - _Depends on:_ 2, 4
  - _Requirements:_ R2.1–R2.3, R3.2–R3.4, R4.4, R4.7, R1.6, R6.1, R6.2
  - _Test:_ `T4, T5, T6, T13 — uv run pytest tests/test_control_integration.py tests/test_webhook_routing_integration.py`

- [x] 6. The poll ingress seam
  - `cli/the_loop/poller/poller.py`: a granted author's comment is a candidate;
    `spawn_authorized` and `_pending_control_ids` unchanged, and asserted so.
  - _Depends on:_ 5
  - _Requirements:_ R3.1, R3.3, R3.4
  - _Test:_ `T7 — uv run pytest tests/test_poller.py tests/test_poller_integration.py`

- [x] 7. Forgetting a roster
  - `cli/the_loop/reset.py`: the section joins `PIECES` so `sessions reset` drops it.
  - _Depends on:_ 1
  - _Requirements:_ R1.6
  - _Test:_ `T9 — uv run pytest tests/test_reset.py`

- [x] 8. The two CLI verbs
  - `cli/the_loop/core/collaborators.py`: `manage_collaborators` — local effect, then the
    ticket comment as a report.
  - `cli/the_loop/commands/collaborators_cmd.py` + registration in `commands/__init__.py`.
  - _Depends on:_ 2
  - _Requirements:_ R5.1–R5.5, R2.4
  - _Test:_ `T10 — uv run pytest tests/test_collaborators_cli.py`

- [x] 9. Tests
  - New: `tests/test_collaborators.py`, `tests/test_collaborators_cli.py`.
  - Extended: `test_control.py`, `test_routing.py`, `test_control_integration.py`,
    `test_webhook_routing_integration.py`, `test_poller.py`, `test_reset.py`,
    and a gates-unchanged regression (A5).
  - Every new test is run against the unfixed tree first and seen to fail.
  - _Depends on:_ 1–8
  - _Requirements:_ all
  - _Test:_ `T1–T13`

- [x] 10. Documentation of record, in this PR
  - `docs/capabilities/webhook-triggers.md` (the second allow-list),
    `docs/capabilities/cli.md`, `docs/cli/commands/{add,remove}-collaborator.md` +
    `docs/.vitepress/config.mts` nav, `docs/config/cli/routing-options.md`,
    `docs/reference/commands.md`, `docs/cli/state.md`,
    `skills/the-loop/reference/collaboration.md`, `docs/decisions/decision-102.md` and the
    decisions index.
  - _Depends on:_ 8
  - _Requirements:_ —
  - _Test:_ `T14 — uv run pytest tests/test_docs_parity.py; markdownlint`

- [x] 11. Verification and evidence
  - Lint, types, the full suite; results in `evidence/verification.md`, security verdict
    against the abuse-case table in `evidence/security-review.md`.
  - _Depends on:_ 9, 10
  - _Requirements:_ all
  - _Test:_ `T13, T14`
