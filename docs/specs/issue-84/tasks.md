---
type: tasks
phase: tasks-breakdown
workItem: "issue-84"
status: draft
approvedBy: []
collaborators: [engineer]
overrides: {}
---

# Tasks: dispatch-lifecycle emoji reactions

> Phase 3 of 3 (requirements → design → tasks). DAG — a task starts once its
> dependencies are checked.

- [x] **T1 — `ReactionConfig` + palette.** New `cli/the_loop/reactions.py`:
  `REACTION_CONTENTS` (REST↔GraphQL names), state constants, `ReactionConfig`
  (`from_mapping`, `content_for`; enabled default False). *(AC2.1–2.3)*
- [x] **T2 — `target_from_event`.** Pure target resolution per design §1
  (provider guard, owner/repo + id validation, comment REST/GraphQL split,
  issue/PR fallback, None for the rest). *(AC1.4, AC3.1, AC3.2)* — depends
  on T1.
- [x] **T3 — `GitHubReactor`.** `react(routed, state)` with the short-circuit
  ladder, `gh api` REST/GraphQL invocation via injectable runner, warn-once on
  missing gh, `reaction.added`/`reaction.failed` emission, never raises.
  *(AC1.1–1.3, AC1.5, AC3.3, AC4)* — depends on T2.
- [x] **T4 — Dispatcher wiring.** `RoutingConfig.reactions`; optional `reactor`
  ctor param (+ override survives `reload`); `_worker` reacts
  started/completed/error; `_dispatch_one`/`_spawn_for`/`_spawn_tmux`/
  `_respawn_tmux` return `bool`. *(AC1.1–1.3, AC1.6, AC2.4)* — depends on T3.
- [x] **T5 — Event-log types.** Register `reaction.added` / `reaction.failed`
  in `eventlog.EVENT_TYPES`. *(AC4)* — depends on nothing.
- [x] **T6 — Config schema + example.** `routing.reactions` in
  `.the-loop/cli-config.schema.json` (enum-guarded states, defaults) and the
  dogfood block (`enabled: true`) in `.the-loop/cli-config.yaml`; `make
  validate` green. *(AC2.1–2.3)* — depends on T1.
- [x] **T7 — Unit tests.** `cli/tests/test_reactions.py` per design testing
  strategy. — depends on T1–T3.
- [x] **T8 — Integration tests.** Dispatcher-level reaction scenarios with a
  recording fake reactor + Gherkin docstrings. — depends on T4.
- [x] **T9 — Docs.** `cli/README.md` reactions section;
  `docs/capabilities/webhook-triggers.md` behaviour + history row. (The
  observability reference needs no edit: its catalog's source of truth is
  `EVENT_TYPES`, kept in sync by a unit test.) — depends on T4.
- [x] **T10 — Gates.** `make check` (ruff, markdownlint, format, pyright,
  validate, pytest) fully green; evidence in `execution-log.md`. — depends on
  T1–T9.
