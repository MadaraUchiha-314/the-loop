---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#529"
---

# Security review: a Slack kickoff offers Do or Start

> The `security-review` node's proof (`reference/security.md`). Risk tier **3**: the
> change renders a second command button on one Slack message. It touches no sensitive
> path: no schema, nothing under `.the-loop/` or `.github/workflows/`, and no
> auth/secret/credential file. The autonomous review suffices, and no named human
> sign-off is required at this tier.

## Security review (gate)

- **Mechanism:** the-loop's checklist (`reference/security.md`) applied to
  `git diff origin/main...HEAD -- cli`: ~60 changed lines across `channels/slack.py`,
  `channels/inbound.py`, `channels/commands.py`, `commands/channels_cmd.py` (a status
  label) and a comment in the app manifest. The critic round on PR #530 was briefed on
  the same security questions and found nothing.
- **Outcome:** passed, no findings.
- **Checked:**

  | Question | Answer |
  |----------|--------|
  | New entry point or route? | None. The press arrives on the existing `block_actions` path (`handle_socket_action`), which reads only `the-loop:`-prefixed action ids |
  | Can a press do more than a typed message? | No. The value becomes an `InboundReply`'s **text** and is judged by `process_reply`: the allow-list, the `control.command` grant and the ledger's named-actor check. Tested in `test_an_unlisted_members_do_press_arms_nothing` and `test_a_crafted_do_press_value_arms_nothing` |
  | Untrusted text rendered into the new block? | No. The description section is built from `COMMAND_BUTTONS` and `COMMAND_DESCRIPTIONS` constants only. The member's message never reaches it |
  | Authorization widened? | No. `do` was already a `SPAWN_COMMAND` under the same grant as `start` (issue-225). It is now offered on a message where only `start` was offered |
  | Fail closed? | Yes. `command_buttons_for` renders nothing without push reachability and the grant, and drops a disabled keyword. Tested in `test_a_kickoff_without_the_command_grant_offers_no_loop` and `test_a_disabled_do_keyword_leaves_start_alone` |
  | Secrets, tokens, personal data? | None added, moved or logged |
  | Dependencies? | None added |

- **Abuse cases of the requirements:** 1 (unlisted presser), 2 (crafted value) and 4 (no
  grant) are each covered by a negative test. Abuse 3 (a press on an unrelated message)
  is the unchanged issue-337 behaviour: a press is the presser typing the keyword in
  that thread.
- **Human sign-off:** not required (tier 3).
