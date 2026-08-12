---
type: execution-log
workItem: issue-208
phase: needs-review
status: in-progress
---

# Execution Log: `the-loop ask` + `POST /api/v1/sessions/reply`

> Append-only log for issue-208. Ticket:
> [#208](https://github.com/MadaraUchiha-314/the-loop/issues/208).

## How this session ran the loop

One cloud session, one pass, no human at the other end — the same posture as issue-211,
with the same two consequences a reviewer should hold while reading:

1. **`phase-selection` was not run as a gate.** There was nobody to tick the checklist;
   the session was started by the ticket itself. Phases assumed: the full spec chain,
   verification, self-review. `brainstorming` and the opt-in `design-critic-review` were
   not taken — the ticket already states the verb, the route and the substantive change
   (central marker stamping), and no second model was available.
2. **The chain was authored before the code, but approved by nobody.** The artifacts are
   a proposal to ratify, not a locked chain; `status: draft` on all four says so.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-12 | — | Not run as a gate; see above |
| requirements-definition | 2026-08-12 | | [`requirements.md`](requirements.md) — 5 requirements, 3 NFRs, 7 abuse cases. Risk tier **3**: no schema/sensitive path, and the new write capability lands on a plane (`/sessions/control`) that already spawns and kills the same sessions |
| design | 2026-08-12 | | [`design.md`](design.md) — two core functions, one route, one verb; the deliberate absences (no ask route/MCP, no respawn from reply, no poller guessing) |
| test-planning | 2026-08-12 | | [`testing-plan.md`](testing-plan.md) — 8 rows in scope, 7 `n/a` with reasons |
| tasks-breakdown | 2026-08-12 | | [`tasks.md`](tasks.md) — 12 tasks |
| implementation | 2026-08-12 | | Built. Tasks 1–11 complete |
| verification | 2026-08-12 | | Testing plan executed: every activity but T11 (needs a human, a workstation, tmux and `gh`). 1849 tests pass (+30 new); lint, format, types, markdown, schema validation and the UI suite/build clean |
| needs-review | 2026-08-12 | | Handed to the PR |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| `claude/github-issue-208-vc0s4s` | the whole work item | open, awaiting human approval |

## Progress entries

### 2026-08-12 — the shape of the change

Read the seams before writing anything. Three findings shaped the design:

- **The UI already wrote the contract.** issue-207 shipped `awaitingInput` in
  `ui/src/api/model.ts` keyed on `session.awaiting_input`/`session.reply_sent`, a
  question card that lights up from the event alone, and a reply box disabled with copy
  naming `POST /api/v1/sessions/reply` and "bracketed paste into the pane". This work
  item implements the contract the UI states, rather than inventing a second one.
- **The marker producer/consumer already live in one module.** `authz.mark_self_authored`
  is idempotent and documented as "apply only to text the-loop itself composed" — which
  is exactly what the agent's own question and the-loop's own delivery report are. The
  central stamp is a call, not new machinery.
- **`TmuxRunner.deliver` is the delivery.** Bracketed paste + Enter is how every webhook
  event already reaches a session; the reply route reuses it and deliberately does not
  reuse the dispatcher's respawn behaviour around it (a reply must never start an agent).

One scope call, recorded here for the reviewer: the ticket says "no UI work is required".
The question card indeed lights up on its own — but the reply box is hard-disabled with
copy asserting *"the service has no reply route yet"*, which this change makes false.
issue-207's own rationale for shipping it disabled was honesty; leaving it disabled once
the route exists would invert that. The minimal wiring (enable, POST, report, refresh)
is included as R5 and flagged in the PR briefing as strike-able.

## Documentation

| Doc | Change |
|-----|--------|
| [`docs/cli/commands/ask.md`](../../cli/commands/ask.md) | New page: what the verb does, its three effects in order, the gh-failure behaviour, and why it runs in-process; added to the commands index and the VitePress sidebar |
| [`docs/capabilities/control-plane.md`](../../capabilities/control-plane.md) | Current behaviour: the ask/reply/attention contract; the "two disabled surfaces" bullet corrected to one; issue-208 history row |
| [`docs/capabilities/cli.md`](../../capabilities/cli.md) | The `ask` verb's SHALL block and a history row |
| [`docs/capabilities/webhook-triggers.md`](../../capabilities/webhook-triggers.md) | The `work-item` directive's stated behaviour now names the verb |
| [`docs/config/cli/routing-options.md`](../../config/cli/routing-options.md) | The interaction-mode table's `work-item` row names the verb and the reply route |
| [`skills/the-loop/reference/collaboration.md`](https://github.com/MadaraUchiha-314/the-loop/blob/main/skills/the-loop/reference/collaboration.md) | § interaction channel routes questions through `the-loop ask`; § loop prevention gains the "the verb stamps for you" bullet and the reply report as a second daemon-side producer |
| [`docs/api-specs/openapi/the-loop.v1.yaml`](../../api-specs/openapi/the-loop.v1.yaml) | `/api/v1/sessions/reply` + `SessionReplyBody` (the `/api/docs` page is generated from this) |
| [`ui/README.md`](https://github.com/MadaraUchiha-314/the-loop/blob/main/ui/README.md) | § Not yet served: the reply row moved from "disabled" to shipped; one surface remains |
| [`docs/decisions/decision-078.md`](../../decisions/decision-078.md) | New — central stamping, in-process ask, the fail-closed reply, and the four alternatives |

`README.md` and `SKILL.md` are untouched: neither describes the question flow at this
level of detail, and the skill's rules reference `reference/collaboration.md`, which is
updated.

## Capability docs

[`control-plane.md`](../../capabilities/control-plane.md),
[`cli.md`](../../capabilities/cli.md) and
[`webhook-triggers.md`](../../capabilities/webhook-triggers.md) — all updated in this PR
(see the table above).

## Verification results

In [`testing-plan.md`](testing-plan.md) § Verification results, with evidence in
[`evidence/verification.md`](evidence/verification.md). Summary: everything but T11
executed and passing (1849 tests, 52 UI tests, all gates); T11 (a real session, a real
pane, a real ticket) needs a human and is the one thing to do before merge.

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | the-loop (this session) | new finding — against a live service a waiting item produced **two** inbox rows: the event-derived "needs input" entry and the raw `awaiting-input` attention row. Deduplicated in `attentionEntries` (the richer Reply entry wins; the raw row survives only when the event window missed the question), with two tests | [`model.ts`](../../../ui/src/api/model.ts), [`model.test.ts`](../../../ui/src/api/model.test.ts) |
| 2 | self | the-loop (this session) | new finding — `ask`'s `--question-file` read leaked a file handle (`open(...).read()` with no close); now `Path.read_text`. Also caught by this pass: a first-draft test asserted the None-dropping behaviour of the real `emit` against a fake that captures raw kwargs — the assertion was fixed to test `ask`'s behaviour, not the fake's | [`ask_cmd.py`](../../../cli/the_loop/commands/ask_cmd.py) |
| 3 | self | the-loop (this session) | new findings, docs-altitude — two pages still described the pre-verb world: `webhook-triggers.md`'s directive contract and `routing-options.md`'s mode table. Both updated; a sweep for "post its own question"/"no reply route" found nothing else outside historical specs, which stay as written (they are deltas, not state) | [`webhook-triggers.md`](../../capabilities/webhook-triggers.md), [`routing-options.md`](../../config/cli/routing-options.md) |
| 4 | critic | — | **not run.** `reviews.critics` is empty in this repo's harness config and no second harness was available to this session | |
| 5 | security | — | mechanism-level review done against the requirements' 7 abuse cases (each has a mechanism and a negative test — see `design.md` § Security design); risk tier 3, so no named human sign-off is mandated. The one judgement a human should confirm: granting "type into the agent's pane" to the plane that already holds spawn/kill is treated as **no widening in kind** | [`requirements.md`](requirements.md) § Security considerations |
