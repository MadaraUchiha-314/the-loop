---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#389"
---

# Security tests (T8): one negative test per abuse case

> Row T8 of [`testing-plan.md`](../testing-plan.md) § Evidence plan. The twelve abuse
> cases of [`requirements.md`](../requirements.md) § Security considerations, each named as
> [`design.md`](../design.md) § Security design names it. Run at the PR's head on
> 2026-09-19.

## Command

```bash
cd cli && uv run python -m pytest -q tests/test_channels_mentions_security.py
```

**12 passed** in 0.16 s.

## One section per abuse case

| Case | Test (`cli/tests/test_channels_mentions_security.py`) | What it asserts |
|------|------|-----------------|
| A1 | `test_a_strangers_mention_is_dropped_in_silence` | five mentions from a member on no list (`help`, `record-context`, `start`, `approved`, prose) are `unauthorized-actor`: no reaction, no ephemeral, no record, no delivery |
| A2 | `test_a_collaborator_cannot_record_a_decision_or_command` | `record-decision`, `start` and `add-channel … --listen all` from a collaborator are `unauthorized-act` with nothing recorded or delivered |
| A3 | `test_a_forged_message_action_buys_nothing` | a payload naming an authorized member in its text but an unlisted `user.id` is refused; a bad channel id or ts is `ignored` / `bad-metadata`; no record |
| A4 | `test_the_context_frame_marks_the_snapshot_untrusted` | an instruction inside a snapshot reaches the session only inside the context frame, after the untrusted rule |
| A5 | `test_a_snapshot_cannot_forge_a_record_or_broadcast` | a pasted marker, envelope, `<!here>` and keyword inside the thread leave one marker, one envelope, no broadcast and a defanged keyword in the record |
| A6 | `test_a_decision_is_never_a_gate_answer` | a decision record whose text reads `approved` is marked, so `classify-feedback`'s authorized-comment filter (`_authorized_comments`) returns nothing |
| A7 | `test_a_mention_is_processed_once_whatever_the_order` | `message` then `app_mention` (and the reverse, and a redelivery) act once — the second is `duplicate` / `not-addressed` |
| A8 | `test_a_mention_in_an_unknown_channel_records_nothing` | a mention in a channel with no room and no binding is `unmapped`; no record, no reaction |
| A9 | `test_a_snapshot_is_scrubbed_and_a_huge_one_refused` | a token and an email in the thread are redacted in the record; a snapshot over the comment limit is `snapshot-too-large` with ⚠️ and an ephemeral |
| A10 | `test_an_unaddressed_message_leaves_no_trace` | a plain message in a `mentions` room: `not-addressed`, no record, no delivery, no reaction, no cursor moved |
| A11 | `test_an_unresolvable_collaborator_authorizes_nobody` | a roster entry with a bad `slack` id, a bad login or neither is skipped and grants nobody |
| A12 | `test_a_bad_listen_value_reads_as_mentions` | a forged `listen` value reads as `mentions`; an invalid declaration is refused whole |

The fail-closed list of the requirements (no scope, no grant, empty lists, a used
trigger, a refused record) is covered across T2 (`unpublishable-event`, `duplicate`,
`record-failed`) and T10 (the scope finding).
