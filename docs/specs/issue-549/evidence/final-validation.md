---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#549"
---

# Final validation: the Slack collaboration experience

## Final validation evidence

Every requirement is met and proved by the verification results in `testing-plan.md`.
The review rounds after verification fixed 23 defects and accepted 1 residual risk. Two
items wait for a human: the risk-tier-4 security sign-off, and the Slack-client view of
the shapes, which moves to the post-merge report.

| Requirement | What proves it | Result |
|-------------|----------------|--------|
| R1 The whole text reaches Slack | T1 splitter tests; T4 read-back (parts `(1/2)`, `(2/2)` in order); critic C4 and C5 and self-review R1-2 and R2-1 (no text lost from fences or tables) | met |
| R2 Markdown drawn natively | T4: the table arrived as a Slack `table` block; T1 table fallback | met |
| R3 A short form the agent writes | `comment --summary` through CLI, API and MCP (T1, T3); 600-character cap (T1, critic C1) | met |
| R4 Where each form goes | T2 placement scenarios (room thread, central reply) | met |
| R5 No link previews | T4: none after post **and** after edit | met |
| R6 Progress edits one message | T2; edits retry 429s and keep order (self-review R1-4, R1-5; critic C3) | met |
| R7 Mention who must act | T2 once-per-wait; mentions only on the awaiting message (R1-6); a failed lookup retries (R1-7) | met |
| R8 State at a glance | T4: reaction ⏳ → ⚙️ → none; T1 state machine | met |
| R9 Recap after a long gap | T1 and T2 recap tests | met |
| R10 Bookkeeping stays out | T2 bookkeeping filter | met |
| R11 Approve from Slack | T2: press in a room approves (lowercased-ref root cause fixed); T8 refusals (unauthorized, stale, other channel) | met; first real press reported after merge (T11) |
| Security, abuse cases 1–9 | T8 (334 passed); security review: 1 finding fixed (cubic heading pattern), about 40 crafted inputs inert | met; **named human sign-off pending** (tier 4) |

**Tests:** `uv run pre-commit run --all-files` on `d2ba0b47`: 7,377 passed and 2 skipped.
One unrelated server-spawning test,
`test_session_secrets_integration.py::test_issue_485_a_spawned_server_and_its_pane_hold_no_secret`,
failed under load and passes when run alone.

**Reviews:** `self-review.md` (2 rounds, 13 fixed), `critic-review.md` (6 findings: 5 fixed,
1 accepted), `security-review.md` (1 fixed, 2 hardening notes acted on).

**Accepted residual risk:** if the process crashes, or Slack's reply is lost, after Slack
accepted a post but before its timestamp was recorded, the retry posts that one message
again (critic C2). `chat.postMessage` takes no idempotency key.

**After merge (T11 and T5):** report on the ticket the first real gate approved from
Slack, with screenshots of the room thread, a central reply, a gate before and after a
press, and a recap.
