---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#413"
---

# Self-review: the listener measures its own share of the traffic (issue-413)

## Round 1 — self

Read the whole diff against the requirements, the minimalism ladder and
`reference/security.md`.

### What I changed as a result

1. **Two defects the rendered output found that the unit tests did not.** Writing the
   surfaces was not enough — rendering them against a real state file was:
   - `summary_line` printed `"{short} of the last {len(recent)} checks short"` with the
     **lifetime** total against the **window's** length. On a deployment with 12 checks
     and 4 retained it read `5 of the last 4 checks short`, which is the kind of line an
     operator stops trusting. Both counts now come from the window.
   - `cadence_line` said `none short` unconditionally whenever the last check was not
     `unverifiable`, so `channels status` printed `8 retained, none short` immediately
     above a `[!]` naming four. It counts the window too now.

   Both are pinned by tests that fail without the fix.
2. **`/the-loop status` was emitting three `• slack:` bullets** — one per sentence —
   turning one finding into three list items in a Slack message. One bullet now, with
   the caveat and the remedy as its continuation.
3. **Moved `SPLIT_CAVEAT` / `SPLIT_REMEDY` into `channels/slack.py`.** They started in
   `splitwatch`, which would have made the doctor import the watch — a new edge from the
   older module to the newer one for two strings. They now sit beside `HEARTBEAT_MARKER`,
   which is the same kind of thing, and both modules read them from there. R4.2's
   "the same sentence everywhere" is then structural rather than a convention.
4. **`window_seconds` resolves through the module rather than binding in the signature.**
   A default bound at import is unreachable from a test driving the listener, which has no
   argument to pass one down — the same reason the doctor resolves `build_client` through
   `_slack` at call time.
5. **An `unverifiable` check no longer touches the ladder or the window.** The first draft
   folded it in as a non-short check, which meant a rate limit would retire a live
   finding. A check that could not run is not evidence either way.

### What I deliberately did not change

- **No second cadence key.** The check rides the reconcile's deadline. A split makes
  "how late may an envelope be" urgent, which is the question `catchUpSeconds` already
  answers, and a second key is a second thing to get wrong.
- **No thread.** The window is 5 seconds and aborts on the stop event; `catch_up` already
  does more network work inline on the same tick.
- **No automatic remediation.** Rotating a credential has an operator's name on it.

## Round 2 — critic

Read as the reviewer who has to say yes or no.

| Question | Answer |
|---|---|
| Can this check make the listener worse? | It posts and deletes at most 2 messages per 900s and never raises out of `run_cycle`; the listener also guards the call itself. A `chat_delete` the app cannot perform leaves a marker message in the room — litter, stated in the design. |
| Can it produce a false accusation? | Only in the direction of silence. A forged heartbeat can make a short check look clean, never the reverse. A genuinely lost message reads as short, which is why every sentence says **evidence, not proof**. |
| Is the sticky report defensible against the ticket, which asked for one clean cycle to clear it? | Yes, and it is argued in `design.md` § Trade-offs from the reporter's own `2/3 → 1/3 → 3/3 → 1/3`. The *escalation* does clear on one clean check, which is what the "no warning storm" half of the ask needs; the *report* clears after a full clean window. |
| Does anything read the state file that should not? | No. `status`, `channels status` and `render_status` only. It is forgeable by anyone who can write `state.root`, so it drives no gate, no authorization and no routing — the same contract `poll-status.json` carries. |
| Does the doctor still work? | The heartbeat branch emits `channel.heartbeat` first and unconditionally, then feeds the watch. Pinned by `test_the_doctors_receipt_is_still_written`. |
