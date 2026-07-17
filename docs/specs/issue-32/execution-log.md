---
type: execution-log
workItem: issue-32
phase: brainstorming
status: in-progress
---

# Execution Log: tmux-backed observable/interactive harness sessions

> Append-only log of progress for the user's visibility. Checked in alongside the spec
> at `docs/specs/issue-32/`. The-loop keeps the work item's phase label in the ticketing
> system in sync with the `phase` front-matter above.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| brainstorming | 2026-07-16 |  | issue #32 is exploratory (asks architecture/alternatives questions) → Phase 0 |
| requirements-definition |  |  | derived from the locked brainstorm |
| design |  |  |  |
| tasks-breakdown |  |  |  |
| implementation |  |  |  |
| needs-review |  |  |  |
| complete |  |  |  |

## Progress entries

### 2026-07-16 — brainstorm drafted

- **Phase:** brainstorming
- **Did:** studied the current spawn/resume path (issue-15: `Dispatcher._spawn_for`,
  `HarnessAdapter`, session registry) and drafted `brainstorm.md` answering the issue's
  four questions — architecture options (tmux-hosts-interactive vs. tmux-as-viewer vs.
  runner abstraction), user-interaction pattern, tmux's role vs. alternatives (screen,
  dtach, Zellij, ttyd/GoTTY, vendor-hosted), and the three access modes (local / SSH /
  web terminal).
- **Checkpoint/tests:** markdownlint on the new docs (spec-only change; no code).
- **Next:** human review of the brainstorm — open questions 1–5 (interaction fidelity,
  injection reliability, id/completion capture, web-mode scope, per-item runner) need
  the owner's answers before the artifact can lock and requirements be derived.
- **Blockers:** waiting on brainstorm review/lock (`requireHumanReviewPerPhase`).

### 2026-07-17 — first human review round on the brainstorm

- **Phase:** brainstorming
- **Did:** owner reviewed on PR #33: **Option A chosen** for question 1 (typing into the
  live TUI is the bar), and asked for more detail on questions 4 (web-mode scope) and 5
  (mixed fleets). Replied on each thread, then edited `brainstorm.md` in place: question 1
  marked resolved, questions 4/5 expanded with the unpacked recommendations, leaning
  updated to "A semantics confirmed".
- **Checkpoint/tests:** markdownlint on the spec docs.
- **Next:** owner's calls on the remaining questions (2–5); then lock the brainstorm and
  derive `requirements.md`.
- **Blockers:** brainstorm still `in-review` (questions 2–5 open).

### 2026-07-17 — second human review round on the brainstorm

- **Phase:** brainstorming
- **Did:** owner resolved more open questions on PR #33: access control is
  **environmental** (VPN / provider network for remote hosts; nothing needed on a local
  laptop — the-loop ships no auth of its own), and question 5 is **receiver-global**
  `routing.runner`. Replied on both threads and updated `brainstorm.md`: security
  constraint rewritten as the environmental-access assumption, question 4 reduced to the
  ship-vs-document call, question 5 marked resolved, leaning updated.
- **Checkpoint/tests:** markdownlint on the spec docs.
- **Next:** owner's calls on questions 2 (injection reliability), 3 (id/completion
  capture — likely a design-phase spike) and the remaining half of 4 (ship vs. document
  the web layer); then lock the brainstorm and derive `requirements.md`.
- **Blockers:** brainstorm still `in-review` (questions 2–4 open).

### 2026-07-17 — third human review round: web layer in scope + installability

- **Phase:** brainstorming
- **Did:** owner ruled that installing the-loop must satisfy the ttyd dependency —
  resolving question 4 fully: the web layer **ships** (not just a documented recipe).
  Replied on the thread with the dependency mechanics (native binaries can't ride the
  Python wheel → preflight/doctor verification with per-platform guidance as the
  baseline; static-binary auto-download parked as enhancement; system-package
  auto-install rejected) and updated `brainstorm.md`: constraints, question 4, leaning
  and hand-off now carry the installability requirement.
- **Checkpoint/tests:** markdownlint on the spec docs.
- **Next:** questions 2 (injection reliability) and 3 (id/completion capture) remain;
  then lock the brainstorm and derive `requirements.md`.
- **Blockers:** brainstorm still `in-review` (questions 2–3 open).

## Review cycles

| Cycle | Type (self/critic) | Reviewer | Outcome | Link |
|-------|--------------------|----------|---------|------|
| 1 | human (brainstorm) | @MadaraUchiha-314 | Option A chosen (Q1); Q4/Q5 explanations expanded | [PR #33 review threads](https://github.com/MadaraUchiha-314/the-loop/pull/33#discussion_r3600112067) |
| 2 | human (brainstorm) | @MadaraUchiha-314 | Access control environmental (Q4 auth half); receiver-global runner (Q5) | [PR #33 review threads](https://github.com/MadaraUchiha-314/the-loop/pull/33#discussion_r3600144073) |
| 3 | human (brainstorm) | @MadaraUchiha-314 | Web layer ships; installing the-loop must satisfy the ttyd dependency (Q4 resolved) | [PR #33 review thread](https://github.com/MadaraUchiha-314/the-loop/pull/33#discussion_r3600170758) |

## Final validation evidence

Pending — the work item is in the brainstorming phase.
