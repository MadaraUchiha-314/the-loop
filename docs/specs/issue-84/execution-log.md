---
type: execution-log
workItem: "issue-84"
phase: needs-review
status: in-progress
---

# Execution Log: emoji reactions acknowledging that the-loop is processing an entity

> Append-only log of progress for the user's visibility. Checked in alongside
> the spec at `docs/specs/issue-84/`.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-07-24 |  | Issue #84 body: 👀 started / ✅ completed / ⁉️ error, CLI-config-driven, no-op where unsupported. GitHub-palette constraint surfaced (✅/⁉️ unavailable → closest defaults, configurable). |
| design | 2026-07-24 |  | Dispatcher-level seam (covers webhook + poll); `reactions.py` (config, target resolution, `gh api` reactor); default off (first daemon write surface). |
| tasks-breakdown | 2026-07-24 |  | 10-task DAG |
| implementation | 2026-07-24 |  | Implemented on `claude/github-issue-84-me696x` |
| needs-review | 2026-07-24 |  | PR opened; awaiting human review (tier-3, `human-approves-pr`) |
| complete |  |  |  |

## Progress entries

### 2026-07-24 — spec drafted, implementation started

- **Phase:** requirements → design → tasks → implementation
- **Did:** Read the trigger path end-to-end (router → dispatcher → poller).
  Established that both ingress paths share the dispatcher, making it the one
  seam where "started/completed/error" is truthfully observable; confirmed the
  poll path's comment ids are GraphQL node ids while webhook ids are numeric
  (drives the REST/GraphQL split). Drafted the 3-phase spec.
- **Next:** implement T1–T10.
- **Blockers:** none. Human approval of the spec + code happens at the PR
  (tier-3, `human-approves-pr`).

### 2026-07-24 — implemented (T1–T10)

- **Phase:** implementation → needs-review
- **Did:**
  - `reactions.py`: `ReactionConfig`, `target_from_event`, `GitHubReactor`
    (REST + GraphQL via `gh api`, warn-once missing gh, never raises).
  - `webhook/dispatcher.py`: `RoutingConfig.reactions`; injectable reactor
    surviving `reload`; `_worker` reacts started/completed/error;
    `_dispatch_one`/`_spawn_for`/`_spawn_tmux`/`_respawn_tmux` return `bool`.
  - `eventlog.py`: registered `reaction.added` / `reaction.failed`.
  - Config: `routing.reactions` in `cli-config.schema.json` (enum-guarded) +
    dogfood block in `cli-config.yaml` (`enabled: true`).
  - Tests: `test_reactions.py` unit suite + dispatcher integration scenarios
    (success/failure/spawn/no-reaction paths) with a recording fake reactor.
  - Docs: `cli/README.md` reactions reference; `webhook-triggers.md` behaviour
    and history row (the observability reference defers to `EVENT_TYPES`,
    which a unit test keeps in sync — no edit needed).
- **Checkpoint/tests:** `make check` green — ruff, markdownlint, ruff format,
  pyright 0 errors, `validate_config.py` VALID, pytest all passed.
- **Next:** open PR with the reviewer briefing; request review.
- **Blockers:** none.

### 2026-07-24 — owner decision on PR #85: default-on

- **Decision:** the owner answered the briefing's open question — reactions
  default to **enabled: true** (was drafted default-off as the conservative
  posture for the daemon's first GitHub write). Paper trail: the owner's
  comment on PR #85 ("default should be on").
- **Did:** flipped the default in `ReactionConfig` (+ `from_mapping`), the
  config schema, both `cli-config.yaml`s (repo + template), README, capability
  doc and this spec (AC2.3, security section, design decision). Added a
  conftest autouse fixture stubbing the dispatcher's default reactor so the
  suite stays hermetic now that a bare `RoutingConfig()` enables reactions;
  updated the default-asserting tests.
- **Checkpoint/tests:** `make check` green again.

## Review cycles

| Cycle | Type (self/critic) | Reviewer | Outcome | Link |
|-------|--------------------|----------|---------|------|
|       |                    |          |         |      |

## Final validation evidence

_Recorded on the PR: local gate output (ruff/markdownlint/pyright/validate/
pytest) and the unit/integration scenarios demonstrating each acceptance
criterion (started/completed/error targets, config gating, no-op paths)._
