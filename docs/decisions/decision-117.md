# Decision 117: a Slack command button is a reply with the keyword as its value under the existing `control.command` grant; the outcome is shown by editing the pressed message; Socket Mode stays required and `channels status` says how

- **Status:** proposed
- **Date:** 2026-09-11
- **Work item:** [issue-337](https://github.com/MadaraUchiha-314/the-loop/issues/337)
- **Deciders:** jc1993 (the ask), MadaraUchiha-314 (the Start button), the-loop (design); MadaraUchiha-314 (owner, at the PR)
- **Refines:** [decision-103](decision-103.md) (through the ledger, never around it;
  buttons only where a press can be received), [decision-111](decision-111.md) (an
  accepted message is acknowledged on itself; a refusal leaves no mark),
  [decision-116](decision-116.md) D5 (Socket Mode is required for anything interactive)

## Context

Issue-337 asks for an **Execute** button on the Slack messages that expect
`the-loop execute` typed back — from a phone, typing the exact string is the slowest
possible way to say yes — with the same authorization as the typed command; the owner
adds a **Start** button. Two sub-asks: make the button work without hand-provisioning
a Socket Mode app, or say plainly in `channels status` what is required and how; and
show the outcome in the thread after a press.

At 13.9.0 the channel renders Approve / Request changes buttons on approval-shaped
events, only when a press can be received (`read.mode: socket` and the `gate.feedback`
grant), and a press enters the inbound pipeline as the member's reply carrying the
button's value. Four questions had to be settled: **what a command button is**, in
terms of the grants; **where the outcome of a press is shown**; **whether a press can
be received without an app-level token**; and **which messages get which button**.

## Decision

| # | What was chosen | Why |
|---|-----------------|-----|
| D1 | **A command button is a reply whose value is the configured control keyword, under the existing `control.command` grant — not a new grant, not a new code path.** The press enters `process_reply` exactly as a typed `the-loop execute` does: allow-list, classification (`parse_command` reads the value), the grant, the unmarked record on the ledger, the ingress executes. | Decision-103 D1 is the rule: a channel advances the loop through the ledger, never around it. The grant already lets every authorized member *type* the keyword; a button that types it for them adds no authority, so a new grant would be a second name for the same permission. A dedicated handler that called `core.sessions.control_session` would be a second path with a second set of refusals and a marked comment the ingress ignores — the alternative decision-116 D2 already rejected for the slash command. |
| D2 | **The outcome is written onto the pressed message by editing it** (`chat.update`): the pressed button set is replaced by a context line — ✅ / ⚠️, the button's name, the member, what was recorded and where, or the error — and link buttons stay. A landed press removes the buttons; a failed one keeps them. A dropped press edits nothing. | The message under the member's thumb is where the answer is read; a reply would be one more message on a phone and would leave the button in place to be pressed again by mistake. Removing the buttons after success is the receipt and the guard against a double press in one move; keeping them after a failure is the retry. Not editing on a drop keeps decision-111 D1: a refusal leaves no mark. The issue-325 reactions stay — they are the acknowledgment; this is the outcome. |
| D3 | **Socket Mode, and therefore the app-level token, stays required for every button; the answer to "make it work without provisioning" is a `channels status` that prints the exact steps that still apply.** | Slack delivers an interactive payload to two places only: a public Request URL, or a Socket Mode connection that acknowledges within three seconds. the-loop exposes no endpoint (decision-084) and refuses to (decision-116 D5); a poll cycle has no connection to acknowledge on. So the token is not a the-loop policy but Slack's contract, and the honest response is to say so where the operator looks — with the page in Slack's UI, the scope, the variable's name and presence, and the config keys — rather than a one-line hint. Rendering a button no listener can receive stays refused (decision-103 D5). |
| D4 | **Which message gets which button is decided from the event, by a fixed table**: the phase-selection checklist mirror (recognised by the hook's own marker in the `comment.agent` text) gets Execute; the kickoff's "opened, this thread is now the conversation" reply gets Start. | These are the two messages that today tell the reader to type a keyword. Keying on the marker the hook already leaves — rather than on prose, a node name or a new event type — costs nothing in the graph, needs no new catalog row, and cannot be forged into a different effect: a press is judged by the pipeline whatever message it sat on. The table is where a third button goes when a third message expects a keyword. |

## Consequences

**Good.** The two keywords a phone user types most become one tap each, with the
identical record on the ticket and the identical audit trail. A press has a visible
outcome on the message. `channels status` turns from a hint into instructions. No new
grant, scope, key or state; a 13.9.0 configuration that could receive Approve presses
and holds `control.command` gains the buttons on the next message.

**Costs, accepted.** The app-level token is still a provisioning step (D3). A press
lands on the ledger's next ingress, as a typed keyword does; the edit says so. The
edit is one more Slack call per press, best-effort. A double press before the first
edit lands records the keyword twice — the gates already absorb a repeated `execute`
and the dispatcher a repeated `start`.

## Alternatives considered

| Alternative | Why not |
|-------------|---------|
| A new grant (`control.button`) for buttons | D1: the same permission under a second name; an operator who lets Slack type keywords has already decided |
| A dedicated press handler calling the core facade | D1: around the ledger, a marked comment, four verbs with no CLI form (decision-116 D2's reasoning) |
| A thread reply after the press instead of an edit | D2: one more message on a phone, and the button stays pressable |
| Receiving presses over HTTP (a Request URL) | D3: an exposed endpoint the-loop refuses (decision-084) |
| A `phase-selection-pending` notify event carrying the button | D4: a new catalog row, a graph change and a subscription for what the marker already identifies |
| Buttons for every control keyword on every message | no message expects them; a row of buttons nobody asked for is noise on a phone |
