# Decision 111: a Slack message the pipeline accepts is acknowledged on that message, best-effort, with Slack's own palette

- **Status:** proposed
- **Date:** 2026-09-08
- **Work item:** [issue-325](https://github.com/MadaraUchiha-314/the-loop/issues/325)
- **Deciders:** jc1993 (the ask), the-loop (design); MadaraUchiha-314 (owner, at the PR)
- **Refines:** [decision-103](decision-103.md) (through the ledger, never around it),
  the issue-84 contract (`routing.reactions`: on by default, best-effort, ids only)

## Context

Issue-84 gave the dispatcher a visible acknowledgment on GitHub: 👀 when an event is
dequeued, 🎉 when the dispatch lands, 😕 when it fails — best-effort, on by default,
reaction-only. Issue-245 and issue-309 then made Slack a channel an operator can drive
the loop *from*: a reply in a bound thread is authorized, classified, recorded on the
ledger and acted on. The acknowledgment did not follow the reply: `target_from_event`
answers `None` for anything that is not GitHub, and the Slack channel never called
`reactions.add`. @jc1993's case is the phone: after replying, the only feedback is a
posted message minutes later, and until then the reply may or may not have been seen.

Three questions had to be settled: **where** the acknowledgment sits in the pipeline,
**which** emoji, and **how much** of the GitHub reactor to reuse.

## Decision

| # | What was chosen | Why |
|---|-----------------|-----|
| D1 | **The acknowledgment sits after the last refusal and before the record.** `received` is added once the message passed map → drop-own → authorize → classify → grant, and before the ledger write; `completed` / `error` after the action, from the outcome the pipeline already computes. A dropped message gets no reaction. | An acknowledgment is a statement that *the-loop will act on this*. Placed any earlier it would confirm the bot's presence to a stranger or acknowledge a message that is then dropped; placed after the record it would lag the very thing the operator is waiting to know. Silence on a drop mirrors the ticket (a drop writes nothing there either) and issue-322's *a refusal leaves no mark*. |
| D2 | **Its own config block, `channels.slack.reactions`, mirroring `routing.reactions`' contract rather than sharing its values.** `enabled` (default `true`), three states, `""` skips one. | The two palettes differ: GitHub's is a fixed eight (`hooray`, not `tada`), Slack's is open and per-workspace. Sharing the *names* would force one surface to a wrong or missing emoji; sharing the *shape* — on by default (the owner's PR #85 call: visibility out of the box is the point), a state per lifecycle moment, best-effort — keeps the two readable side by side. The block lives under `channels.slack` because it is a fact about that channel's token and scope, not about routing. |
| D3 | **Slack's defaults are `eyes`, `white_check_mark`, `warning`.** | Issue-84 asked for ✅ and ⁉️ and settled for 🎉 and 😕 because GitHub has neither. Slack has ✅; it is the mark a phone reader recognises fastest as *done*. ⚠️ is chosen over ⁉️ for the same legibility reason — a failure should look like a failure. 👀 is kept: it is what the operator already knows from GitHub. |
| D4 | **`completed` means the pipeline's own action landed, per event type.** A `work-item.reply` is complete when recorded *and* delivered; a relayed `gate.feedback` / `control.command` when its unmarked record is on the ledger; a kickoff when the issue exists and the thread is bound. | The pipeline does not observe the ledger's ingress locking a gate or starting a session, and a ✅ that claimed it would be a lie the operator acts on. What the pipeline *can* vouch for is that the message reached the ticket the loop reads — which is the contract decision-103 already makes for a relayed reply. The gap is named in the requirements' *Out of scope*, with the seam a later item would use (subscribe the channel to the outcome event). |
| D5 | **A method on the channel, not a reactor module.** `SlackBotChannel.react(reply, state)` with the channel's own client and token rule; the pipeline decides when. | `reactions.py` is a `RoutedEvent` → `gh` argv reactor with a GitHub palette; the Slack call is one SDK method. A shared abstraction over two calls that share nothing but a lifecycle vocabulary is the kind of layer minimalism refuses. The contract — never raises, ids-only events — is copied in words, not in code. |

## Consequences

**Good.** The operator on a phone sees 👀 within a poll interval (or instantly over
Socket Mode) and ✅ / ⚠️ when the pipeline is done — on the message they typed, without
opening GitHub. The two surfaces' acknowledgments read alike. Nothing about what a
message may become, who may speak, or where the record lands changes.

**Costs, accepted.** One more scope on the bot token (`reactions:write`); without it,
every accepted message costs one `channel.reaction_failed` warning until the operator
adds the scope or sets `enabled: false` — loud by design, as the missing-`gh` warning
is. One more Slack API call per accepted message (two when the action finishes), in
the pipeline's own thread, before the record: on a Slack outage the SDK's 30-second
timeout is the worst-case delay before the record is written — the same exposure the
ledger write already has on a GitHub outage, and it never changes the outcome. The
ledger's ingress still acknowledges the relayed record on GitHub, so a gate answer from
Slack ends up with 👀 in two places, which is the mirror the ticket asked for.

## Alternatives considered

| Alternative | Why not |
|-------------|---------|
| Reuse `routing.reactions`' values for Slack | `hooray` and `confused` are not Slack emoji names; the operator would have to choose names that exist on both, or one surface would silently fail |
| Extend `GitHubReactor` with a Slack target (`target_from_event` for a `slack` provider) | The reactor is built around a routed GitHub event and a `gh` argv; a Slack reply is an `InboundReply` in another package with its own client. The seam is the pipeline, not the dispatcher |
| React on the drop too (a ❌ for an unauthorized reply) | Confirms to a stranger that the bot reads the thread, and marks a message the-loop deliberately leaves no record of |
| `completed` only when the ledger's ingress finishes (the gate locked, the session started) | The pipeline cannot see it; faking it means a ✅ on an approval the gate then refused. Left as a seam for a later item |
| Remove 👀 when adding ✅ | GitHub keeps both; a second write to remove a decoration buys nothing |
| Default `enabled: false` | The owner's PR #85 decision for GitHub was the opposite, and the ticket asks for the mirror; the fail-closed defaults that matter (`channels.slack.enabled: false`) already gate everything |
