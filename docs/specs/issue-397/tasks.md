---
type: tasks
phase: tasks-breakdown
workItem: "github:MadaraUchiha-314/the-loop#397"
status: approved
approvedBy: ["the-loop"]
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Tasks: minor Slack polish — room-declaration confirmation, ephemeral help, connector signature

> Phase 4 of 4. Each task names the requirement it satisfies and the testing-plan row
> that proves it; the test lands with the change.

- [x] **A1 — confirm the room from the dispatcher (O1).** `_apply_channel` calls a new
      `_confirm_room(target.ref)` after a *new* declaration; `_confirm_room` calls
      `self.opener` when set and swallows every failure. *Req:* R1.1–R1.4 · *Test:* T2
      `test_a_new_declaration_confirms_the_room_through_the_opener`,
      `test_a_failing_confirmation_never_undoes_the_declaration`.
- [x] **A2 — confirm the room from the CLI (O1).** `manage_channels` calls
      `_confirm_room(work_item, config, messages)` after an applied `add-channel`;
      opens through `bus.open_conversation` only with a `channels` section; a failed
      result is one `err` line. *Req:* R1.1, R1.3 · *Test:* T2
      `test_add_confirms_the_room_when_channels_are_configured`.
- [x] **B1 — `help public` (O4).** `verbs.wants_public_help` + `PUBLIC_HELP`;
      `process_reply` answers with `bot.say` in the member's thread when it holds,
      the ephemeral otherwise; `help_text` names the visible form. *Req:* R2.1–R2.4 ·
      *Test:* T1 `test_help_public_is_read_from_the_first_line_only`, T2
      `test_help_public_answers_as_a_reply_everyone_can_see`.
- [x] **C1 — pin the first-line rule (O5).** No production change; the tests above plus
      `test_a_connectors_signature_line_does_not_change_help`. *Req:* R3 · *Test:* T1, T2.
- [x] **D1 — docs.** `docs/capabilities/channels.md` (room bullet, grammar bullet,
      history row); the follow-ups index and file link the issue; evidence files.
      *Deps:* A1–C1.
