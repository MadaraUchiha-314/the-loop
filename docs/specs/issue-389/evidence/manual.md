---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#389"
---

# Manual exploratory (T11): against a real workspace

> Row T11 of [`testing-plan.md`](../testing-plan.md) § Evidence plan. **Not executed
> here**: the verification ran in a cloud checkout with no Slack workspace and no bot
> credentials (the plan's *Verification environment* names them by reference only), so
> the procedure is recorded for the owner or a reviewer to run, one section per step,
> with the outcome column empty. The same code paths are driven by T2 with Slack's payload
> shapes as fixtures (`cli/tests/fixtures/slack/`).

## Bring-up

1. `the-loop channels manifest` → *Create New App → From a manifest* (or re-import on the
   existing app), then **Reinstall** so `app_mentions:read` is granted.
2. A scratch config with `channels.slack.read.mode: socket`, both tokens exported under
   the names `botTokenEnv` / `appTokenEnv` resolve to, and `publish` holding
   `work-item.reply`, `context.added`, `decision.recorded`, `control.command`.
3. `the-loop start`; `the-loop channels status --probe` reports no `[!]` for
   `app_mentions:read`.
4. A scratch public channel and a scratch issue; `the-loop add-channel <ref> slack@#room`.

## Procedure

| # | Step | Expected | Outcome |
|---|------|----------|---------|
| 1 | Post a plain message in the room | nothing: no reaction, no reply, no comment on the ticket; `the-loop events --tail` shows `channel.dropped reason=not-addressed` | |
| 2 | `@the-loop help` | an ephemeral answer only you see, listing the grammar and this channel's grants; nothing on the ticket | |
| 3 | In a thread of three messages, `@the-loop record-context` | 👀 then ✅ on the mention; one marked `📎 context` comment on the ticket quoting the three messages with names and permalinks; one reply in the thread with the comment's link; the running session receives the context frame; `the-loop channels records <ref>` lists it | |
| 4 | `@the-loop record-context` again in the same thread | ✅ and an ephemeral *Nothing new in this thread*; no second comment | |
| 5 | ⋯ → *Add to the-loop as context* on a message in another thread | exactly step 3's outcome for that thread, the answer ephemeral | |
| 6 | ⋯ → *Record a decision with the-loop* | the modal, pre-filled from the message; submit with kind `tech` and a rationale → a marked `📌 decision` comment with `kind: tech`, `_why:_` and `_discussed at:_` the message's permalink; the session receives the decision frame | |
| 7 | `@the-loop add-collaborator slack:U…` (a member not on the allow-list), then that member's `@the-loop record-context` | the roster entry lands (`the-loop sessions collaborators <ref>`); the member's act is recorded and ✅ | |
| 8 | That member's `@the-loop record-decision we ship` | ⚠️ and an ephemeral *only an authorized user may …*; nothing on the ticket | |
| 9 | `the-loop add-channel <ref> slack@#room --listen all`, then a plain message | the message is a `work-item.reply` again; `channels status` counts one room hearing every message; `channels threads` shows `listen: all` | |
| 10 | A plain DM to the bot | input, as before this change | |
| 11 | `read.mode: poll` and `the-loop channels status` | `mentions: off (read.mode is poll — nothing addressed can arrive …)` | |

## Captures

Redacted screenshots of the room message, the ticket record, `context.md`, the modal and
the decision file, and the shortcut → modal → record capture, go under `ui/` when the
procedure is run; none is committed with this PR.

## Tear-down

`the-loop stop`; delete the scratch room and issue after the captures.
