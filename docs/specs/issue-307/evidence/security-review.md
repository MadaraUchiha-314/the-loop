# Evidence: security review (T13)

Tier 4 (`autonomy.tiers`), and `security.review.humanSignOffMinTier: 4` — so this
records the harness's own review against the abuse cases in `requirements.md`, and the
**named human security sign-off is still outstanding**. It is requested in the pull
request's briefing.

## Why this work item is a security review at all

It widens, for the first time since issue-63, the set of people whose text the-loop will
act on. The question is not whether a collaborator can comment — it is whether a
collaborator can reach an *action*.

## The abuse cases, and what closes each

| # | Abuse case | Verdict | Where it is closed, and what proves it |
|---|------------|---------|----------------------------------------|
| A1 | A commenter grants themselves | closed | `Dispatcher.handle`'s named-and-allowlisted-actor re-check runs before any command executes. `test_a_collaborators_own_grant_attempt_is_refused`, `test_a_collaborator_cannot_command_the_daemon` |
| A2 | A collaborator escalates with `the-loop stop` / `cleanup` / `execute` | closed | Same check; and the comment is **not** forwarded either, so it cannot reach the agent as instruction. `test_a_collaborator_cannot_command_the_daemon` asserts both halves |
| A3 | Injection through the login argument | closed | `normalize_login` refuses everything but GitHub's login grammar — no sanitising, no partial match. 14 rejection cases in `test_anything_that_is_not_a_login_is_refused_not_cleaned_up`, plus `test_nothing_but_a_login_reaches_the_caller` (a path and an argv fragment after the keyword reach nothing). Posting is `gh` argv, never a shell |
| A4 | A grant on one work item reaches another | closed | `permits` answers only about the refs handed to it, and both ingresses hand it the event's own refs. `test_membership_is_asked_only_about_the_refs_it_is_given`, `test_a_grant_reaches_one_work_item_and_no_other`, `test_a_grant_on_another_work_item_does_not_carry` |
| A5 | A collaborator satisfies a human gate | closed | The hooks read `config.authorizedUsers`, which this work item does not touch — asserted directly rather than inherited: `test_a_collaborators_comment_does_not_reach_a_human_gate` |
| A6 | A collaborator's comment spawns a session | closed | `_spawn_refusal` returns `collaborator-no-spawn`, settled rather than retried. `test_a_collaborators_comment_cannot_spawn_a_session`, `test_a_collaborators_comment_never_spawns_a_session`; and `test_a_collaborator_cannot_arm_a_spawn` on the poll path |
| A7 | The portable record is edited directly to add a collaborator | accepted, unchanged | Identical to the `control` section beside it: a writer who can forge `control: {command: start}` can already arm the item. The record is tracked and human-readable, so such an edit shows up in a pull-request diff, and `index.json` is derived on every write. A malformed entry grants nobody (`test_a_hand_edited_entry_that_names_no_login_grants_nobody`) |
| A8 | A revoked collaborator keeps reaching the session | closed | Membership is read per event, never cached in the session record. `test_remove_revokes` plus the per-event read at both seams |
| A9 | A closed item's roster is reused when it reopens | closed | Cleared on closure with the control record (`test_closing_the_work_item_forgets_its_roster`) and by `sessions reset` (`test_reset_forgets_the_collaborator_roster`) |

## Two things a reviewer should look at hardest

1. **The spawn seam's condition is deliberately two-part** — outside `authorizedUsers`
   **and** granted on one of the event's refs — rather than the one-part "outside
   `authorizedUsers`". The one-part form is stronger and was tried first; it changes
   behaviour for events that can only occur when the router is bypassed (fixtures that
   drive a dispatcher directly with an empty allow-list), and it is not what R3.2 asks
   for. The reasoning, and why the inference behind the two-part form is written out
   instead of relied upon, is in `design.md` §3 and `decision-102` D4. If a third path
   ever admits a named non-authorized actor, that path must state its own rule.
2. **`authorizedUsers` still matches exactly; the roster matches case-insensitively.**
   Deliberate and asymmetric: GitHub logins *are* case-insensitive, so a roster that
   stored `@Dana` and failed to recognise `dana` would be a silent revocation — but
   widening how the *global* list compares is a different decision, and not this one.

## What is not claimed

No penetration testing, no fuzzing of the login grammar beyond the enumerated cases, and
no review of GitHub's own permission model — a grant is meaningful only for someone who
can already comment on the work item.
