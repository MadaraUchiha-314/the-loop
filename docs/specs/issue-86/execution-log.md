---
type: execution-log
workItem: "issue-86"
phase: needs-review
status: in-progress
---

# Execution Log: keep tmux sessions after the work completes, and announce how to attach

> Append-only log of progress for the user's visibility. Checked in alongside
> the spec at `docs/specs/issue-86/`.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-07-24 |  | Issue #86 body: don't kill the tmux session on completion; post the attach command as a GitHub comment when the session is created. |
| design | 2026-07-24 |  | Three seams: `runner.py` (remain-on-exit + pane liveness), `dispatcher.py` (retain on close, announce on spawn/respawn), new `announce.py` (`gh`-shelling comment poster in the `reactions.py` mould). |
| tasks-breakdown | 2026-07-24 |  | 12-task DAG |
| implementation | 2026-07-24 |  | Implemented on `claude/github-issue-86-pa73ti` |
| needs-review | 2026-07-24 |  | PR opened; awaiting human review (tier-3, `human-approves-pr`) |
| complete |  |  |  |

## Progress entries

### 2026-07-24 — spec drafted

- **Phase:** requirements → design → tasks
- **Did:** Traced the tmux lifecycle end-to-end (`TmuxRunner.spawn/deliver/kill`,
  the dispatcher's PR-close branch, `sessions close/attach`). Surfaced the
  non-obvious coupling that shapes the design: keeping panes alive with tmux's
  `remain-on-exit` makes `has-session` return true for sessions whose harness
  has died, which would silently break the issue-80 respawn path — so retention
  ships together with a `has_live_session()` pane-liveness check. Drafted the
  3-phase spec.
- **Next:** implement T1–T12.
- **Blockers:** none. Human approval of the spec + code happens at the PR
  (tier-3, `human-approves-pr`).

### 2026-07-24 — implemented (T1–T12)

- **Phase:** implementation → needs-review
- **Did:**
  - `runner.py`: `TmuxResult.output`; `TmuxRunner(remain_on_exit=True)` setting
    `remain-on-exit` best-effort after spawn; `has_live_session()` from
    `list-panes -F "#{pane_dead}"` (unreadable output degrades to "live");
    `deliver()` now guards on liveness so a retained dead pane takes the
    issue-80 respawn path.
  - `announce.py` (new): `AnnounceConfig`, the pure `announcement_body`, and
    `SessionAnnouncer` posting `gh api … /issues/<n>/comments` — no-op ladder
    (disabled, process runner, non-github, malformed coordinates, missing `gh`
    warn-once), never raises.
  - `webhook/dispatcher.py`: `TmuxConfig` + `AnnounceConfig` on `RoutingConfig`
    (hot-reloaded, overrides preserved); PR-close retains the tmux session by
    default via `_close_tmux` (`session.retained`); `_spawn_tmux` /
    `_respawn_tmux` announce after registration.
  - `sessions` CLI: `close --keep-tmux/--kill-tmux` (default from
    `routing.tmux.keepSessionOnClose`); `attach` reaches a **closed** work
    item's retained session, with a note.
  - `sessions/registry.py`: `find_by_work_item(..., include_closed=False)`.
  - `eventlog.py`: registered `session.retained`, `session.announced`,
    `session.announce_failed`.
  - Config: `routing.tmux` / `routing.announce` in `cli-config.schema.json`
    plus both yamls (repo dogfood + packaged template).
  - Tests: `test_announce.py` unit suite; `test_tmux_runner.py` additions
    (remain-on-exit, pane liveness, the `sessions close/attach` paths);
    integration scenarios for retention, kill-when-configured-off, respawn
    through a dead retained pane, announce on spawn/respawn, and an
    announcement failure leaving the dispatch untouched.
  - Docs: `cli/README.md` (two new config sections + `sessions` notes) and
    `docs/capabilities/interactive-sessions.md` (behaviour bullets + history).
- **Checkpoint/tests:** `make check` green — ruff, markdownlint, ruff format,
  pyright 0 errors, `validate_config.py` VALID, pytest 315 passed.
- **Next:** open PR with the reviewer briefing; request review.
- **Blockers:** none.

### 2026-07-24 — owner decisions on PR #87

- **Decision 1 — retention default.** The owner confirmed
  `keepSessionOnClose: true` as the default ("Make it true by default"), which
  is what shipped; no code change.
- **Decision 2 — announce on first spawn only.** The owner answered the
  briefing's second open question ("Keep it to first spawn only"). Paper trail:
  the owner's comment on PR #87.
- **Did:** dropped the `_respawn_tmux` announcement and the now-dead
  `respawned` parameter from `SessionAnnouncer.announce` /
  `announcement_body` / the `session.announced` record; the body now says the
  attach commands survive a respawn (the name is reused, so the first comment
  stays correct). Updated the spec (AC3.2, AC4.2, security section, design
  overview/diagram/decisions/tasks), the schema and both cli-config yamls, the
  README, the capability doc, and the tests — the respawn scenario now asserts
  a respawn happens **and** posts nothing.
- **Checkpoint/tests:** `make check` green again (315 passed).

## Review cycles

| Cycle | Type (self/critic) | Reviewer | Outcome | Link |
|-------|--------------------|----------|---------|------|
|       |                    |          |         |      |

## Final validation evidence

_Recorded on the PR: local gate output (ruff/markdownlint/pyright/validate/
pytest) and the unit/integration scenarios demonstrating each acceptance
criterion (retention on close, respawn through a dead retained pane,
announcement on spawn/respawn, no-op ladder)._
