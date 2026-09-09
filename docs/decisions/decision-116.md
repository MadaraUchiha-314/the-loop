# Decision 116: Slack addresses the-loop itself through a slash command, not a workflow; a work-item verb still goes through the ledger, and the other verbs are grants of their own

- **Status:** proposed
- **Date:** 2026-09-09
- **Work item:** [issue-334](https://github.com/MadaraUchiha-314/the-loop/issues/334)
- **Deciders:** MadaraUchiha-314 (the ask), the-loop (design); MadaraUchiha-314 (owner, at the PR)
- **Refines:** [decision-103](decision-103.md) (through the ledger, never around it;
  grants are event types), [decision-100](decision-100.md) (the control plane is not a
  channel; three ways to reach a standing session)

## Context

Issue-334 asks that everything an authorized user can do on a work item's ticket be
possible from Slack, that the control plane's operator workflows — *upgrade the loop*,
restart, status — be reachable from Slack too, ideally as something "reusable and
importable", and that starting a work item or a standing session from Slack be a
documented gesture.

At 13.8.0 the first ask is already true by grant and unwritten: `control.command` in
`channels.slack.publish` relays a keyword typed in a bound thread onto the ledger,
unmarked, and the ingress executes it (decision-103 D1). The rest shares a single
structural gap — every inbound Slack message is bound to a conversation, and the things
the owner names have none: the instance itself, a work item that has not started, a
standing session that is not running.

Four questions had to be settled: **which Slack mechanism** carries a message with no
thread; **how a work-item verb executes** when it arrives that way; **what grants** the
new verbs; and **where the target of a work-item verb may point**.

## Decision

| # | What was chosen | Why |
|---|-----------------|-----|
| D1 | **A slash command, `/the-loop`, received over Socket Mode — not Slack Workflow Builder, not a Slack "workflow app".** | Workflow Builder fails three tests at once. (1) It cannot reach the-loop: its only outbound step is an HTTP webhook, and the control plane binds loopback and exposes nothing (decision-084) — the whole point of Socket Mode is that nothing is exposed. (2) A workflow that posts a message into the channel posts it **as the workflow**, `bot_id` set, which the pipeline drops as self-authored — and rightly: the person who filled the form is not recoverable from the message, so authorization would have to be invented. (3) There is no importable, checked-in definition of a Workflow Builder workflow an operator can carry between workspaces; the Deno-based "workflow apps" have one, but they run on Slack's infrastructure and again need an endpoint to call. A slash command is delivered into the same Socket Mode connection `channels listen` already holds, carries the invoking member's id (the same allow-list judges it), is discoverable in Slack's own UI, and is declared in the **app manifest** — which *is* the importable YAML the owner asked about. |
| D2 | **A work-item verb from the slash command publishes `control.command` and stops at the ledger record — the same record a thread keyword makes.** The handler starts, spawns and delivers nothing. | Decision-103 D1 is the rule: a channel advances the loop through the ledger, never around it, so every guard a typed comment meets (the marker check, `authorizedUsers`, the control seam's named-actor re-check, the instance's scope) runs unchanged. Calling `core.sessions.control_session` from the listener would be a second path to the same effect, with a second set of refusals and a *marked* comment the ingress ignores — and it would make `execute`, `contribute`, `do` and `review` (which have no CLI form by design) special cases. The one cost — the effect lands on the ledger's next ingress, a delivery or a poll interval — is the cost the thread path already pays, and the thread that opens when the start is accepted (issue-317) is the feedback. |
| D3 | **`status`, `restart`, `upgrade` and the `standing` verbs call the core facade directly, and each family is a grant of its own: `instance.command`, `standing.command`, beside `control.command`.** None is granted by default. | These verbs have no ticket, so there is nothing to record on and no ingress to defer to; the facade is the one implementation the CLI and the API already share (decision-084), and a Slack verb that rendered its `messages` is one more thin client of it. They are **separate** grants because they act on a different thing: a work-item verb writes a comment under the operator's credential; an instance verb restarts the process the listener runs in; a standing verb spawns a tmux session on its host. An operator who let Slack answer gates should not thereby have let Slack restart the daemon. "Grants are event types" (decision-103 D2) is kept: the two new names are catalog rows, printed by `channels status` and pinned to the docs like the rest, `recorded: false` because there is no ticket — the event log is their paper trail, as it is for a standing session's reply (issue-277). |
| D4 | **The work item a slash command names must be one this instance is configured for**: its repository is `kickoff.repo` or a poll source, or the work item is already managed (declared, session, control) or has a bound thread. Anything else is refused and nothing is recorded. | The thread path never had to ask — the work item came from a binding the-loop itself made. An argument can name anything, and the record is a comment under the **operator's** credential: an authorized member could otherwise make the-loop write onto a repository the operator never pointed it at. The four sources are the ones the instance already reads to know what it manages; no new list is introduced. |
| D5 | **Slash commands need `read.mode: socket`, as buttons do; there is no poll form.** | Slack requires an acknowledgment within three seconds through the connection it delivered on; a poll cycle has no such connection, and an inbound HTTP endpoint is what the-loop refuses to expose. `channels status` says so rather than leaving the command to fail silently in Slack. |

## Consequences

**Good.** Slack becomes a complete operator surface: a work item can be started from
a thread it does not have yet, a standing session brought up, the instance restarted or
upgraded — each with the same person, the same grant model and, for a work item, the
same record on the ticket. The app is defined once, in a manifest an operator imports,
and the guide names every mode of interaction with the grant that turns it on. Ask 1
of the ticket needs no code: the pinning tests and the guide are its delivery.

**Costs, accepted.** A work-item verb's effect is deferred to the ledger's next
ingress (D2). The listener is still a foreground process (`channels listen`) rather
than one `the-loop start` hosts — unchanged by this work item, and stated in the
guide. Two more grants to understand; the guide's table is the mitigation. A slash
command cannot bind to the thread it was typed in (Slack's payload carries no
`thread_ts`), so the work item is always an argument.

## Alternatives considered

| Alternative | Why not |
|-------------|---------|
| Slack Workflow Builder, with a form that posts into the channel | D1: unreachable control plane, bot-authored message, no importable definition |
| Top-level "command" messages in the channel (`the-loop start #7` as a message) | The channel's top-level messages are the kickoff surface (`work-item.create`); a message that is sometimes an issue and sometimes a command is an ambiguity the pipeline resolves by guessing |
| One grant, `slack.command`, for every verb | D3: an operator who wants Slack to start work items would be handing it the daemon's restart too |
| Executing a work-item verb locally through `core.sessions.control_session` | D2: a second path around the ledger, a marked comment the ingress skips, and four verbs with no CLI form |
| Any GitHub work item as a target | D4: the operator's credential on a repository the operator never configured |
| Answering every invocation, including an unlisted member's, with an error | The channel's rule is that a refusal leaves no mark; an answer would confirm the bot's presence to someone it does not act for (decision-111 D1's reasoning) |
