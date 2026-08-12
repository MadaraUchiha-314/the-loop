---
type: tasks
phase: tasks-breakdown
workItem: issue-208
status: draft
approvedBy: []
overrides: {}
---

# Tasks: `the-loop ask` + `POST /api/v1/sessions/reply`

> Derived from [`design.md`](design.md) and [`testing-plan.md`](testing-plan.md). Ticket:
> [#208](https://github.com/MadaraUchiha-314/the-loop/issues/208).

## Task list

- [x] 1. Register the two event types
  - `session.awaiting_input` and `session.reply_sent` in `eventlog.EVENT_TYPES`, mirrored
    in the observability reference.
  - _Depends on:_ none
  - _Requirements:_ R3.2
  - _Test:_ T12 — docs parity
- [x] 2. `post_issue_comment_with_url` in `comments.py`
  - Shared private implementation with `post_issue_comment`; parses `html_url` from gh's
    JSON, degrading to empty on unparsable output.
  - _Depends on:_ none
  - _Requirements:_ R1.2
  - _Test:_ T1 — `test_comments.py` (red→green)
- [x] 3. `ask_session` in `core/sessions.py`
  - Parse/refuse, central `mark_self_authored`, post, emit (success and gh-failure
    paths), `{messages, exitCode}` shape.
  - _Depends on:_ 1, 2
  - _Requirements:_ R1.1–R1.4
  - _Test:_ T1 — `test_core_sessions.py` (red→green)
- [x] 4. `reply_session` in `core/sessions.py`
  - Registry lookup, paused/missing/dead refusals (no respawn), provenance framing,
    `TmuxRunner.deliver`, emit, marked best-effort report comment.
  - _Depends on:_ 1
  - _Requirements:_ R2.1–R2.6
  - _Test:_ T1 — `test_core_sessions.py` (red→green)
- [x] 5. `the-loop ask` command
  - `commands/ask_cmd.py`: `--work-item`, `--question`/`--question-file` (`-` = stdin),
    in-process execution with the documented exception rationale.
  - _Depends on:_ 3
  - _Requirements:_ R1.1–R1.5
  - _Test:_ T2 — CLI scenario with fake gh
- [x] 6. `POST /api/v1/sessions/reply` route + contract
  - `SessionReplyBody`, one delegation line, `operationId: replySession`; the authored
    OpenAPI file gains the path.
  - _Depends on:_ 4
  - _Requirements:_ R2.1–R2.5, R2.7
  - _Test:_ T2, T3 (red→green)
- [x] 7. `awaiting-input` kind in `core/attention.py`
  - Event-log derivation with the open/answered rule; question text as detail.
  - _Depends on:_ 1
  - _Requirements:_ R3.1
  - _Test:_ T1 — `test_core_attention.py` (red→green)
- [x] 8. The interaction directive names the verb
  - `_WORK_ITEM_DIRECTIVE` in `interaction.py`: ask through `the-loop ask`; manual
    gh + marker stays as the stated fallback. Constant text, no interpolation.
  - _Depends on:_ 5
  - _Requirements:_ R4.1
  - _Test:_ T1 — existing `test_interaction.py` assertions updated
- [x] 9. Integration scenarios
  - `test_ask_reply_integration.py` with Gherkin docstrings: delivery, refusals,
    no-respawn, marked bodies, the CLI verb end-to-end.
  - _Depends on:_ 5, 6, 7
  - _Requirements:_ R1, R2, R3.1; abuse cases 2–5
  - _Test:_ T2, T8
- [x] 10. UI: the reply box goes live
  - `client.replySession`, the demo transport simulating the delivery (its control
    verbs' convention), enabled controls + submit/busy/error/refresh, stale copy
    removed (`WorkItemDetail.tsx`, `model.ts`, `useControlPlane.ts`, `App.tsx`,
    `ui/README.md`), tests updated; the `awaiting-input` attention row deduplicated
    against the event-derived question entry.
  - _Depends on:_ 6
  - _Requirements:_ R5.1, R5.2
  - _Test:_ T15
- [x] 11. Docs + decision
  - `docs/capabilities/control-plane.md` and `docs/capabilities/cli.md` (current
    behaviour + history rows), `docs/capabilities/webhook-triggers.md` (the directive's
    stated behaviour), `skills/the-loop/reference/collaboration.md` § where questions
    go + loop prevention, CLI command doc for `ask` (+ index + sidebar),
    `docs/config/cli/routing-options.md`, `docs/decisions/decision-078.md` (central
    stamping; in-process ask; no reply-from-ticket closure). The event catalog lives in
    `eventlog.EVENT_TYPES` (the observability reference points there, no mirror to
    edit).
  - _Depends on:_ 1–10
  - _Requirements:_ R3.2, R4.2
  - _Test:_ T12, T14
- [x] 12. Verification
  - Execute the plan, tick activities with evidence under `evidence/`.
  - _Depends on:_ 1–11
  - _Requirements:_ all
  - _Test:_ the plan itself
