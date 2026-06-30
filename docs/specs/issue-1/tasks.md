---
type: tasks
phase: tasks-breakdown
workItem: issue-1
status: approved
approvedBy: ["@MadaraUchiha-314 (issue author intent)"]
overrides: {}
---

# Tasks: the-loop (create itself)

> Phase 3. The implementation DAG for the-loop. **v0** tasks (1–10) are done and form
> the current PR; **deferred** tasks (11–20) are the planned forward DAG and remain
> unchecked until taken up as follow-up work items (per `decision-003`). Each task
> references the requirement(s) it satisfies and its dependencies.

## v0 — foundation (this PR)

- [x] 1. Plugin distribution: `plugin.json`, `marketplace.json`
  - _Depends on:_ none — _Requirements:_ R7
- [x] 2. Project footprint: `config.schema.json` (+ `workflow`), default `config.yaml`,
       `manifest.yaml`, `external-tools.md`, `collaborators.yaml`
  - _Depends on:_ none — _Requirements:_ R2, R3, R5, R7
- [x] 3. Templates: epic/story/bug + requirements/bugfix/design/tasks/execution-log/
       decision/learning
  - _Depends on:_ 2 — _Requirements:_ R1, R4, R6
- [x] 4. Commands: `init`, `work-on` (3-phase), `upgrade-the-loop`
  - _Depends on:_ 2, 3 — _Requirements:_ R4, R7
- [x] 5. Skill + reference docs (workflow, tooling, collaboration, observability,
       automation-and-roadmap) + SessionStart hook
  - _Depends on:_ 2 — _Requirements:_ R2, R3, R4, R5
- [x] 6. Knowledge: architecture index, decisions 001–004, learnings index
  - _Depends on:_ none — _Requirements:_ R6
- [x] 7. Self-referential 3-phase spec + execution log for issue #1
  - _Depends on:_ 3 — _Requirements:_ R4, R6
- [x] 8. README with install/usage/roadmap
  - _Depends on:_ 1, 4 — _Requirements:_ R7
- [x] 9. Phase state machine + labels modeled in config/commands
  - _Depends on:_ 2, 4 — _Requirements:_ R4
- [x] 10. Validate (JSON, schema, manifest tree); commit; push
  - _Depends on:_ 1–9 — _Requirements:_ R2, R7
- [x] 11. CLI: extensible `the-loop` Python CLI (zero-dep core) + `gh-webhook start|stop`
       receiver (HMAC verify, `/health`, pytest); `webhooks.ghWebhook` config
  - _Depends on:_ 2 — _Requirements:_ R9, R8 (receiver)

## Deferred — runtime & integrations (follow-up work items)

- [ ] 12. Make `init` actually scaffold (write files, detect tooling, create labels)
  - _Depends on:_ 4 — _Requirements:_ R7
- [ ] 13. Per-language tooling integrations: uv/bun, pytest/vitest, playwright, ruff/
       oxlint, pyright/tsc, markdownlint, with root scripts
  - _Depends on:_ 2 — _Requirements:_ R2
- [ ] 14. Pre-commit/pre-push hooks + CI workflow sharing the SAME commands
  - _Depends on:_ 13 — _Requirements:_ R2
- [ ] 15. Multi-entity testing: local linking, podman service orchestration, local-vs-
       remote selection
  - _Depends on:_ 13 — _Requirements:_ R2
- [ ] 16. Observability wiring: shared logger, configurable levels, chrome-devtools MCP
       browser logs
  - _Depends on:_ none — _Requirements:_ R3
- [ ] 17. Messaging integrations (slack/whatsapp/email) for escalations
  - _Depends on:_ none — _Requirements:_ R5
- [ ] 18. Predictability: decide hooks vs custom code/scripts; enforce PDLC steps
  - _Depends on:_ 5 — _Requirements:_ R4
- [ ] 19. Route received webhook events (PR comments, Actions) from the CLI → harness
  - _Depends on:_ 11, 18 — _Requirements:_ R8
- [ ] 20. Remote-workspace auto-trigger on ticket creation ("the dream")
  - _Depends on:_ 19 — _Requirements:_ R8
- [ ] 21. Project-wide DAG orchestration (depends-on/blocked-by) + Cursor packaging
  - _Depends on:_ 18 — _Requirements:_ R8, R7

## Dependency graph (DAG)
v0: `{1,2,6} → 3 → {4,5,7,9} → 8 → 10`; `2 → 11` (2 also feeds 4/5/9; 1 also feeds 8).
Deferred: `4 → 12`; `2 → 13 → {14,15}`; `16,17` independent; `5 → 18`;
`{11,18} → 19 → 20`; `18 → 21`.

## Checkpoints
- v0: after task 10 — JSON + schema validation + manifest tree check; after task 11 —
  `pytest` for the CLI (see execution-log).
- Each deferred task: tests at logical checkpoints per `reference/workflow.md`.
