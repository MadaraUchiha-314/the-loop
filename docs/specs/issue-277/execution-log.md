---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#277"
phase: needs-review
status: in-progress
---

# Execution Log: sessions that outlive every work item

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-08-20 |  | `requirements.md` derived from the ticket |
| design | 2026-08-20 |  | `design.md` |
| test-planning | 2026-08-20 |  | `testing-plan.md` |
| tasks-breakdown | 2026-08-20 |  | `tasks.md` |
| implementation | 2026-08-20 |  | tasks 1–10 |
| verification | 2026-08-20 |  | every activity in `testing-plan.md` ran; results and evidence recorded there |
| needs-review | 2026-08-20 |  | reviewer briefing posted on the pull request |
| complete |  |  |  |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| (see the ticket) | the whole work item — spec chain, the standing-sessions capability and every surface it reaches, documentation and tests | open |

## Capability docs

_Pending._

## Documentation

_Pending._

## Progress entries

### 2026-08-20 — spec chain written

- **Phase:** requirements-definition → design → test-planning → tasks-breakdown
- **Did:** derived the four spec artifacts from the ticket. The one judgement call worth
  a reviewer's attention is the name: the ticket says _ad-hoc sessions_, and "ad-hoc" is
  already `pdlc-adhoc-loop`/`the-loop do` in this codebase, so these are **standing
  sessions** (decision-099).
- **Next:** implementation.

### 2026-08-20 — implemented and verified

- **Phase:** implementation → verification → needs-review
- **Did:** tasks 1–11. The runner split first (`spawn_in`/`deliver_to`/`kill_target`/
  `terminate_harness_in`, work-item methods delegating), then `the_loop/standing.py`
  (ref grammar, declaration parser, record store, `StateLayout.standing_dir`), then
  `the_loop/core/standing.py` (the six verbs, the boot directive, the resume probe, every
  `standing.*` event), then the surfaces: the lifecycle rows, `the-loop standing`, four
  REST operations with their authored contract entries, three MCP tools (control
  deliberately excluded), `loop.standing` on the SDK, and the two `parse_standing_ref`
  branches that let a Slack thread carry a standing session. Schema, shipped template,
  capability doc, config docs, command page, state page, SDK reference and decision-099.
- **Two things worth a reviewer's eye**, both recorded where they happened rather than
  done quietly: `pattern` had to be implemented in the hand-written config validator (the
  name constraint is load-bearing — the value becomes a tmux target and a file name), and
  `CURRENT_CONFIG_VERSION` was **not** bumped, because the block is purely additive and a
  bump would push every existing config through an upgrade for nothing.
- **Checkpoint/tests:** `make test` — 2584 passed, 1 skipped (2501 on `main` at `b6bfda1`,
  +83). `make lint`, `make format-check`, `pyright cli`, `make validate`, markdownlint —
  all clean, first run. Evidence under `evidence/`.
- **Spotted, not fixed:** `docs/api-specs/openapi/the-loop.v1.yaml` carries the
  `/api/v1/stream` path **twice** (two near-identical blocks; YAML's last-key-wins hides
  it, and the parity test compares path/method/operationId sets so it passes). Pre-existing
  and unrelated to this work item — worth its own ticket rather than widening this PR.
- **Next:** human review.
