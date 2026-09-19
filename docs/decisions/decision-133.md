<!-- Written per the `the-loop:writing` skill. -->

# Decision 133: a Slack conversation addresses the-loop by mention; the acts it asks for are marked records that end in the session

- **Status:** proposed
- **Date:** 2026-09-19
- **Work item:** [issue-389](https://github.com/MadaraUchiha-314/the-loop/issues/389)
- **Deciders:** MadaraUchiha-314 (owner, on PR #390); the-loop (design)
- **Refines:** [decision-103](decision-103.md) (through the ledger, never around it; a
  grant is what a message may become), [decision-117](decision-117.md) (a button is
  exactly the typed keyword), [decision-130](decision-130.md) (a declared room is the
  conversation), [decision-102](decision-102.md) (a work-item collaborator is input only)

## Context

A declared room (issue-375, issue-378) made every authorized member's message a message
on the work item. In a room with six people that is a firehose into the ticket and into
the agent, and the stakeholders the room exists for, who are on no allow-list, cannot
address the-loop at all. The ticket asked for three things: the-loop acts only when
mentioned; a thread can be handed to it as context; a decision made in the room is
recorded. The owner decided the shape on the brainstorm's review and the design settled
what the code makes of it.

## Decision

| # | What was chosen | Why |
|---|-----------------|-----|
| D1 | **The mention is the address, in every conversation shape**, delivered as Slack's `app_mention` event; a `message.*` event is input only in a DM with the bot or in a room an authorized user switched to `all`. | The owner's rule, read literally. A DM has no `app_mention` (Slack does not deliver it there) and is addressed by construction; the switch exists because a small room may want the old firehose, and only an authorized user may ask for it. |
| D2 | **Text is never matched for the mention.** Addressed messages are therefore socket-only, and the poll transport skips mention-gated conversations without moving their cursors; a mention posted while no listener was connected is lost after Slack's retries. | The owner refused text matching. A reconcile-time fallback would reintroduce it; the cost is documented rather than hidden. |
| D3 | **A fixed grammar after the mention, with natural language as the fallthrough**: `record-context`, `record-decision <text>`, `add-collaborator`, any control keyword's last word, `help`; anything else is a reply. No model classifies. | The owner chose the grammar and asked that it be taught; a keyword's last word is composed into the configured keyword exactly as the slash command composes it (decision-116), so one grammar serves three surfaces. |
| D4 | **Both new records are marked**, quoted, scrubbed and defanged like a reply mirror, enveloped with the person's ids, and **delivered by the channel** into the session with a preset frame per act. | The requirement that a decision never be read as a gate answer can be met on this ledger only by the marker: an unmarked comment under the operator's credential is an authorized human's comment to every gate. The person is named by the envelope either way. |
| D5 | **`context.added` and `decision.recorded` are grants, not subscriptions.** | The catalog pins that what a message may become and what a channel hears are disjoint sets (decision-103); `comment.agent` already carries every marked record for a channel that wants to hear it. |
| D6 | **The session keeps the auditable view**: `docs/specs/<id>/context.md` (a fifth, optional artifact with provenance per entry) and `docs/decisions/decision-<nnn>.md` for a Slack-born decision; a read-only `the-loop channels records` verb lets a later session find what it has not folded. | The owner asked for `context.md` with provenance and for decisions to reuse the existing log. The daemon never writes into a spec tree; the ledger record is the copy and the file is the view. |
| D7 | **Two tiers of speaker, per act**: input (`record-context`, a reply, `help`) from authorized users and the work item's collaborators; binding acts (`record-decision`, keywords, the switch) from authorized users only. A collaborator may be known by Slack id alone, added from the room by `@the-loop add-collaborator slack:U…`. | The owner chose the tiers and the gesture. A collaborator was already defined as input-only (decision-102); the roster gains an id, not a power. |
| D8 | **A message shortcut is exactly the typed mention**; the decision shortcut opens a modal whose submission composes the typed form. | Decision-117's rule applied to the next interactive surface: no new authority, the same pipeline, socket-only by construction. |

## Consequences

**Good.** A room is a room for people again: nothing reaches the ticket or the agent
unless somebody addressed the-loop, and what does reach them is one of a few named acts
with a durable, attributed record and a file a reader can audit. Stakeholders on no
allow-list can feed the loop from the room they are in, without gaining any power over
it. The three interactive surfaces share one grammar and one authorization.

**Costs, accepted.** An existing Slack app must be re-imported and re-installed for the
new scope and event, and until it is, nothing typed reaches the-loop; `channels status`
and the connect-time probe say so. A declared room that heard everything now hears only
mentions unless switched. Poll mode hears no channel or thread message any more, and a
mention during listener downtime is lost. A typed gate answer and a kickoff now need the
mention too; button presses and slash commands do not change. Other people's words are
copied, scrubbed, onto a ticket and into a repository that may be public — a
`record-context` is an act of an authorized user or a collaborator, and the guide says
what it copies.

## Alternatives considered

- **Match `<@bot>` in message text** (the brainstorm's first lean) — refused by the owner;
  it also would have kept poll mode working, which is the cost D2 accepts instead.
- **Exempt the-loop's own threads from the mention rule** — refused by the owner: one rule,
  no exceptions.
- **Reactions as verbs** — refused by the owner: harder to learn and dependent on the
  workspace's emoji set.
- **An unmarked decision record**, as the requirement first said — it cannot coexist with
  "never a gate answer" (D4).
- **Subscribable records** — would break the catalog's grant/subscription invariant (D5).
- **A per-work-item `decisions.md`** — refused by the owner in favour of the existing log.
- **The daemon writing `context.md`** — the ledger rule and the daemon's boundary (D6).
- **A reconcile-time text fallback for missed mentions** — reintroduces what D2 refused.
