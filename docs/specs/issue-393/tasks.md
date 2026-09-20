---
type: tasks
phase: tasks-breakdown
workItem: "github:MadaraUchiha-314/the-loop#393"
status: draft
overrides: {}
---

# Tasks: the Slack room becomes a colleague

> Phase 3. Derived from the approved [`requirements.md`](requirements.md),
> [`design.md`](design.md) and [`testing-plan.md`](testing-plan.md). A DAG: a task lists
> its dependencies; unlisted ⇒ independent. Each task names the requirement(s) it
> satisfies and the testing-plan row that proves it. TDD: the test lands with (or
> before) the change in the same task.

## Track A — bug fixes (independent of each other)

- [x] **A1 — park at publish (B8).** In the graph runtime, entering a human-actor node
      sets its status to `waiting` and persists `work-item-state.json` in the same step
      that publishes the approval request; `at_human_gate` (graphlink.py:274) unchanged.
      _Req:_ R4 · _Test:_ T2 `Scenario: the first authorized answer after a gate
      publishes advances the gate` + T1 unit on the entry path.
- [x] **A2 — session inherits the daemon's bus (B6).** Spawn env (runner.py:379–390)
      adds `THE_LOOP_CLI_CONFIG` = the daemon's resolved config path, skipped when
      already present/empty; `ask` (and shared publish path) warns when the bus names
      no channels. _Req:_ R3 · _Test:_ T2 two Scenarios (spawn env; channel-less warn).
- [ ] **A3 — membership-first channel resolution (B1).** `SlackDirectory` gains
      `_read_memberships` (`users.conversations`, public+private) consulted before the
      workspace listing; listings record `truncated`; refusals distinguish
      truncated/exhausted and name paths + remedy. _Req:_ R1 · _Test:_ T1 unit rows.
- [ ] **A4 — critic timeout & detach (B9).** Regression test pinning `--timeout`
      threading; `critic run --detach` + `critic collect` with round state under
      `.the-loop/critic-rounds/`; `critic policy` prints effective timeout; timeout
      error names the flag. _Req:_ R5 · _Test:_ T1 rows.
- [ ] **A5 — listener & refusal observability (B3 part).** Socket listener logs every
      ignored envelope (type, channel, reason) at debug; `control.rejected` posts a
      marked reply with reason + remedy at the attempt site. _Req:_ R2.4, R2.5 ·
      _Test:_ T2 two Scenarios.
- [ ] **A6 — deployment doctor (F2).** `probe_subscription` prints the manifest's bot
      events + the unverifiability caveat; new `doctor slack`: second-consumer
      heartbeat probe (labelled evidence, not proof) + declared-channel directory
      check. _Deps:_ A3 (directory truncated flag), A5. _Req:_ R2.1–R2.3 · _Test:_ T1
      probe unit + T4 live.

## Track B — the room rework (ordered)

- [ ] **B1 — `Event.summary` transport.** Optional field bus→render; escaped, capped,
      mentions neutralised; `ask --summary` and the graph-complete artifact path accept
      it; digest fallback when absent. _Req:_ R8.1–R8.2, R12.2 (abuse case 3) ·
      _Test:_ T1 escape/cap rows + T8 hostile summary.
- [ ] **B2 — `ChannelState` delivery memory.** `last_delivered`, `progress_ts{phase}`,
      `gate_ts{node}`, `phase_selection_ts`; absent keys ⇒ classic; corrupt file ⇒
      classic + one warn. _Req:_ R6 NFR, error handling · _Test:_ T10 degradation row.
- [ ] **B3 — `room_policy.py`.** Pure `decide(event, state)`: dedupe, gate-collapse,
      transition-collapse, progress-edit, ack-thread, session-wins, operator-docs;
      every drop/edit logs its rule. _Deps:_ B2. _Req:_ R6, R10, R11.3, R12.3 ·
      _Test:_ T1 one test per rule row.
- [ ] **B4 — `voice.py` + header removal.** Event→(emoji, first-person template) table;
      rooms lose the header, central channels get short id + title link; single
      signature at render. _Deps:_ B1. _Req:_ R7, R11.1–R11.2, R11.4 · _Test:_ T1
      voice rows.
- [ ] **B5 — delivery integration.** `SlackBotChannel.post` consults RoomPolicy:
      `chat.update` for progress (stale ts ⇒ fresh post), thread replies via stored
      `gate_ts`, suppressions applied; GitHub path untouched. _Deps:_ B2–B4. _Req:_
      R6, R10 · _Test:_ T2 suppression/edit/thread Scenarios.
- [ ] **B6 — phase selection control (F1).** Slack rendering of the checklist as
      in-message checkboxes + outer-loop element + Execute composing the signed
      execute (attributed, authorized); typed `execute without <n,…>` / `skip <phase>`
      grammar; no-interactivity fallback copy; adversarial copy removed. _Deps:_ B5.
      _Req:_ R9 (abuse cases 2, 4) · _Test:_ T2 checkbox/fallback Scenarios + T1
      grammar + T8 unauthorized submit & hostile skip.
- [ ] **B7 — PR gate & digest guard.** `pr-review-pending` names PR
      number/title/link/diffstat, leads with the briefing, button opens the PR; `fit`
      gains protected regions (questions/controls never cut; overflow says what was
      cut). _Deps:_ B1. _Req:_ R8.3–R8.4 · _Test:_ T1 digest rows + T2 PR-gate
      Scenario.
- [ ] **B8 — `room.style` config.** `channels.slack.room.style: agentic|classic`
      (default agentic) + schema + docs; `classic` byte-preserves today's rendering —
      existing outbound suites stay green unchanged. _Deps:_ B5. _Req:_ NFR config
      compat · _Test:_ T10 schema row + full existing suites.
- [ ] **B9 — session voice in the room.** With A2 landed: `session.awaiting_input`
      renders per R12.1 (question, options, default button); session summary announces
      the artifact; `session-wins` proven end-to-end. _Deps:_ A2, B3–B5. _Req:_ R12 ·
      _Test:_ T2 session-voice Scenarios.

## Track C — self-service

- [ ] **C1 — the daemon ensures labels (F3).** `github.ensure_labels` (idempotent,
      declared repos only, cached per daemon lifetime) on first contact;
      `set-phase-label` creates-and-retries once; failure posts once on the ticket.
      _Req:_ R13 (abuse case 5) · _Test:_ T1 ensure rows + T8 undeclared-repo.

## Closing tasks

- [ ] **D1 — capability docs + decision records.** Update affected
      `docs/capabilities/` pages in the same PR; log the two durable decisions
      (park-at-publish; delivery-policy seam) under `docs/decisions/`. _Deps:_ all.
- [ ] **D2 — verification.** Execute `testing-plan.md` (T1/T2/T8/T10 suites; T4 live
      re-run with hard redaction; T5 screenshots; T11 verdict); fill Verification
      results; evidence under `evidence/`. _Deps:_ all.
