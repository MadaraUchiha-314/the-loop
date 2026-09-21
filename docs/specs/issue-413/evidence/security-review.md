---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#413"
---

# Security review: the listener measures its own share of the traffic (issue-413)

## Security review (gate)

- **Mechanism:** the-loop checklist (`reference/security.md`), against the diff.
- **Outcome:** pass. Risk tier 3, so the PR approval is the human gate; no named security
  sign-off is required (that threshold is tier 4).
- **Findings:** none unresolved. Two accepted, documented properties below.

## What the change touches

| Surface | Change | Assessment |
|---|---|---|
| credentials | none. The check reads `channels.slack.botTokenEnv` for **presence** and hands the value to the same `WebClient` the listener already built | no new handling, no new storage, no fingerprint |
| scopes | none. Posting and deleting the heartbeat is `chat:write`, held already | a deployment without it records `unverifiable`, never escalates |
| new output | `<state.root>/local/slack-split.json`, two event types, three rendered surfaces | ids, counts and timestamps only — asserted by a substring search for both token values on the clean, short and unverifiable paths (T9) |
| new config | `channels.slack.read.splitCheckBeats`, integer 0–5 | clamped fail-safe; `0` posts nothing |
| authorization | none | the state drives a report, never a decision |

## Accepted property 1 — a member can forge a heartbeat

The heartbeat is a fixed marker plus a nonce in a channel members can read. A member who
posted `the-loop doctor heartbeat <nonce>` for a nonce the check is currently waiting on
would make a short check look clean.

Accepted:

- `heartbeat_nonce` counts **only a bot-posted message** (`bot_id`, or the `bot_message`
  subtype), so a member's typed marker is an ordinary message read through the ordinary
  pipeline — the forgery needs a bot in the room, not a member;
- the failure direction is a **missed warning**, never a false accusation. Nothing here
  can be made to report a split that is not happening;
- the nonce is 8 random bytes and the window is 5 seconds, so guessing one is not a
  practical attack, and observing one means already being in the room.

## Accepted property 2 — the state file is forgeable, and therefore inert

Anyone who can write `state.root` can write any verdict. This is the same exposure
`poll-status.json` carries, and it is handled the same way: the file drives a **report**
and nothing else. No gate, no authorization decision, no routing and no exit code reads
it — `status`'s `ok` is explicitly unmoved (R3.7), and a test pins that.

## Abuse cases considered

| Abuse case | Outcome |
|---|---|
| noise as denial of service | bounded by construction: at most 5 beats per reconcile, each deleted; the default is 2 per 900s. `0` is off |
| a split report leaking workspace structure into a ticket | the report names a channel id, counts and a timestamp — nothing a member of that workspace does not already have |
| the check used to probe channels the bot is not in | it posts only into `channels.slack.channel`, resolved through the doctor's one resolver; an unresolvable name is `unverifiable`, not a different room |
| a diagnostic used to take the listener down | `run_cycle` never raises, and the listener guards the call as well; pinned by `test_a_check_that_raises_never_ends_the_listener` |
| rate-limit exhaustion hiding a real split | an `unverifiable` check does not clear the ladder or the window, so a finding survives a rate limit |
