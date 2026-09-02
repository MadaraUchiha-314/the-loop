# Decision 103: every channel is a peer on one event bus, and one channel is the ledger

- **Status:** proposed
- **Date:** 2026-09-02
- **Work item:** [issue-309](https://github.com/MadaraUchiha-314/the-loop/issues/309)
- **Deciders:** MadaraUchiha-314 (owner, via the ticket comment), jc1993 (the seed
  proposal and its gates), the-loop (design)
- **Refines:** [decision-094](decision-094.md) (channels beside the integrations; the
  work item stays the source of truth), [decision-102](decision-102.md) (a work-item
  collaborator is input, never authority)

## Context

Issue-245 gave the-loop a channel abstraction with one outbound caller (`ask`), one
graph hook that borrowed it (`notify`) and one inbound meaning (a reply is session
input). @jc1993 then drove work items from a phone and found five places the model
stopped: comments never left GitHub, an approval ping carried nothing, a reply could not
answer a gate, `work-item-complete` fired nowhere, and a DM could not start anything.
Their proposal fitted five gates to the config shapes of 12.1.0.

The owner answered with an architecture instead of five features: channels will
multiply (Jira, a control-plane UI); every event in the system is just an event; every
channel subscribes to any of them and publishes any the-loop recognises; one channel is
the ledger where everything accumulates — GitHub by default, the operator's choice;
each channel renders natively; and identity is declared once, with each person's
channel ids in one entry.

## Decision

| # | What was chosen | Why |
|---|-----------------|-----|
| D1 | **Through the ledger, never around it.** A channel advances the loop by getting the ledger to write a comment the ledger's own ingress already judges: `gate.feedback` and `control.command` are recorded *unmarked* under the operator's credential, with an envelope naming the source and the person. | Zero new authorization code on the action side — the self-marker check, `authorizedUsers`, the control seam's named-actor re-check and `classify-feedback`'s filter all run unchanged on the record. The cost is one ingress hop of latency, stated in the requirements. The alternative — the Slack pipeline calling `Runtime.advance` and the dispatcher's control apply itself — would have been a second executor for every guarded action. |
| D2 | **Grants are event types.** `channels.<name>.publish` lists catalog event types a message may become; `subscribe` lists the ones it receives. Defaults reproduce 12.1.0: `[work-item.reply]` and `[session.awaiting_input]`. | The owner's model says "publish any event the-loop recognises"; a boolean per feature (`advance.enabled`, `mirror.mode`, `kickoff.enabled`) is three vocabularies for one idea and a fourth for the next channel. A grant outside the publishable set is ignored with a warning — it cannot be a typo that widens. |
| D3 | **Identity entries are mappings keyed by channel name; a bare string is a GitHub login.** `routing.authorizedUsers` stays where it is; `channels.slack.authorizedUsers` is removed and migrated into it. | One list the operator already maintains, read per channel through `ids_for`. A separate `people` block would move a list operators know; `collaborators.yaml` is the plugin's file and the daemon never reads it (decision-032/035). |
| D4 | **The person is recorded, the poster is the proof.** A record's envelope names every id the config declares for the actor; the gate attributes the comment to the envelope's GitHub login **only** when the actual poster is authorized and the named login is too. | `approvedBy` should name a person, not the credential that relayed them; but an envelope is comment text, so it may only ever narrow from one authorized identity to another. A collaborator (decision-102) forging one rewrites nothing. |
| D5 | **Approve buttons render only where a press can arrive** — `read.mode: socket` and the `gate.feedback` grant, both. A press enters the pipeline as that member's reply carrying the button's text. | A button nobody receives is worse than none. The text is what `classify-feedback` already reads, so the button adds no vocabulary. |
| D6 | **Notifications are not recorded; `request-review` stays.** The catalog's `recorded` flag is false for the graph's notification events; the ask is recorded because its record *is* the question. | The gate's comment already exists; recording the event again would double every approval request. Folding `request-review` into `notify` is a graph change five shipped graphs and any custom one would have to follow. |
| D7 | **A kickoff issue is unmarked, enveloped, and labelled only from config.** | It must be armable (a marked issue is dropped at ingress, the self-diagnosis rule), the envelope keeps the provenance, and a label the message named could arm work nobody configured. |
| D8 | **`channels.ledger` ships with one value.** | The key states the extension point the owner named ("users can choose which channel is the ledger"); shipping a second value would be shipping a Jira channel, which is its own work item. |

## Consequences

**Good.** The five gaps close as one event type, one grant or one renderer each; a
second channel type is a provider behind `subscribes`/`may_publish`/`post`/`record`;
every step is observable (`bus.*`, `channel.*`); a config that says nothing new behaves
as before, with `work-item-complete` finally firing and pings finally carrying a link.

**Costs, accepted.** A breaking config change (0.7.0) behind the versioned migration; a
Slack id and a GitHub login are joined by hand after migration (the file cannot know
which member is which login); a gate answered from Slack moves on the next ingress rather
than instantly; a kickoff whose `gh issue create` fails is not retried (a retry could
duplicate an issue), so the member re-posts.

## Alternatives considered

| Alternative | Why not |
|-------------|---------|
| Five gates as proposed (`mirror.mode`, `advance.*`, `kickoff.enabled`) | Each is right on its own and wrong together: three switches for one idea, and the fourth channel type restarts the list. The proposal's fail-closed properties are all kept — as defaults of the grants. |
| The Slack pipeline advances the graph and applies control directly | A second executor for every guarded action, and a second place authorization can disagree with itself. |
| Re-attribute every enveloped comment | An unauthorized poster is already dropped; a *collaborator* is not, and could name the owner. Two conditions or none. |
| Mark the kickoff issue self-authored | It would never arm (the router drops marked `issues` events), which is the self-diagnosis rule and the opposite of what a kickoff is for. |
| A top-level `people:` block | Moves the one list operators already know and the docs already point at, for no gain in expressiveness. |
