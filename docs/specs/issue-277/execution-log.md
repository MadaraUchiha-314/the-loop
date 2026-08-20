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
| needs-review | 2026-08-20 |  | reviewer briefing posted on the pull request; owner's ruling (decision-100) worked back into the spec chain and implemented |
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

### 2026-08-20 — the owner's ruling, worked back through the chain

- **Phase:** needs-review (the spec chain is `in-review`, so the artifacts were **edited**,
  not appended to — the reference-don't-duplicate rule)
- **The decision** ([decision-100](../../decisions/decision-100.md), from
  [the PR thread](https://github.com/MadaraUchiha-314/the-loop/pull/278#issuecomment-5358714877)):
  _"Forget about control plane as a channel"_, the three interaction surfaces are tmux /
  Slack / the control plane's messaging path, _"we already have a way to interact with a
  tmux session through control plane, let's reuse that"_, and — the one addition —
  _"let's just do the APIs that create the adhoc session and delete that adhoc session"_.
  So **both** options I had proposed were withdrawn, and create/delete took their place.
- **Did:** requirements gained R6 (seven criteria) and a settled R3.0 naming the three
  surfaces; design gained §D8 (`_entry_for` — a definition comes from the config _or_ the
  registry, and the verbs cannot tell); the record grew to carry a whole definition;
  `create_standing`/`delete_standing` on the CLI, REST (with authored contract entries)
  and SDK, and **not** on MCP; `start_all` now restores created sessions that auto-start,
  because `stop_all` already stops every recorded one.
- **Two judgement calls a reviewer should check:** `create` refuses a name already declared
  or recorded rather than adopting it, and `delete` refuses a _declared_ session rather
  than removing a record `the-loop start` would recreate. Both are argued in decision-100.
- **Checkpoint/tests:** `make test` — 2600 passed, 1 skipped (+99 over `main` at
  `b6bfda1`). `make lint`, `make format-check`, `pyright cli`, `make validate`,
  markdownlint — clean. Every verb also exercised by hand against a real tmux + `claude`:
  create → list → the two refusals → delete, and `stop`/`start` proving a created session
  comes back on the **same** conversation id (R6.6). Evidence refreshed under `evidence/`.
- **Next:** human review.

### 2026-08-20 — the third surface, wired

- **Phase:** needs-review
- **The question** ([PR thread](https://github.com/MadaraUchiha-314/the-loop/pull/278#issuecomment-5361545849)):
  _"Can I do the same action from the control plane ui?"_ The answer was no — and checking
  it showed the gap was wider than the question: `say` was not reachable from the dashboard
  either, so the third surface decision-100 named ("Control Plane messaging ui", the
  owner's own words) did not exist for standing sessions at all.
- **Did:** a **Standing** screen on the dashboard — list both kinds and label which is
  which, create, delete, start/stop/restart, and a per-session message box — plus the five
  client methods, the demo transport (which models the refusals, not only the successes),
  the route, the tab, the styles, and eight tests.
- **Two judgement calls:** it is its **own tab** rather than a row on Sessions, because
  that screen is a tree of work items and a session with no ticket would be a row lying
  about being part of one; and the create form asks for four fields, not eleven — the rest
  have `routing` defaults, and the CLI and API still take them all.
- **Checkpoint/tests:** `bun run lint`, `bun run test` (157 passed, 149 before),
  `bun run build` — clean. Python suite unchanged at 2600 passed, 1 skipped.
- **Next:** human review.
