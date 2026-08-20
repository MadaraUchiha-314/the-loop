# Decision 099: a session that owns no work item lives in its own namespace, and is called standing

- **Status:** proposed
- **Date:** 2026-08-20
- **Work item:** [issue-277](https://github.com/MadaraUchiha-314/the-loop/issues/277)
- **Deciders:** the-loop (proposal), MadaraUchiha-314 (owner — pending)
- **Relates to:** [decision-021](decision-021.md) (tmux is how a session is hosted),
  [decision-046](decision-046.md) (generated state classified by portability),
  [decision-056](decision-056.md) (tmux is the only runner),
  [decision-059](decision-059.md) (the deployment owns authentication)

## Context

Issue-277 asks for sessions the-loop keeps for **itself**: watching the work items in
flight, and letting an operator talk one through recovering a work item that is stuck.
Nothing about that is a work item, and the ticket says so plainly — *"gh issues etc is not
the right surface to interact with this session"*.

Two questions had to be answered before any of it could be built.

**Where does such a session live?** Every session the-loop has today is keyed on a
`WorkItemRef` — `provider:[host/]owner/repo#number`. The tmux name is minted from it, the
registry file is named after it, the router resolves events into it, the poll ledger keys
on it. A session with no ticket has no value to put there.

**What is it called?** The ticket calls it an *ad-hoc session*. "Ad-hoc" already means
something in this codebase, and it means something close enough to be confusing:
`pdlc-adhoc-loop` / `the-loop do` (issue-225) is a **tactical work item that runs no PDLC
process** — it still has a ticket, still gets a `loop-<slug>` session, and still finishes.

## Decision

**A second namespace, and the name "standing session".**

1. **Namespace.** Standing sessions get their own declaration
   (`standingSessions` in the CLI config), their own record store
   (`<state.root>/local/standing/<name>.json`, `StandingRegistry`), their own tmux names
   (`loop-standing-<name>`) and their own verbs. `WorkItemRef` is **not** widened, and
   nothing in the router, the dispatcher or `SessionRegistry` learns that standing
   sessions exist.

   What is shared is exactly what is genuinely the same job: the tmux runner and the
   harness adapters, both refactored to be addressed by *target* rather than by work item
   (`spawn_in`, `deliver_to`, `kill_target`, `terminate_harness_in`), with the work-item
   entry points delegating and keeping their exact refusals.

2. **Name.** They are *standing* sessions — they stand outside the work items, and they
   keep standing until an operator stops them. The ticket's vocabulary is recorded here so
   a reader who arrives from issue-277 can follow it; nothing in the code says "ad-hoc"
   about them.

3. **`standing:<name>`** is the ref grammar, and its **only** reader is
   `standing.parse_standing_ref`, called from two places in the inbound channels
   pipeline. It has no `/` and no `#`, so `WorkItemRef.parse` cannot accept it, and
   `parse_standing_ref` cannot accept a work-item ref.

## Consequences

**Easier.**

- The security property is structural rather than asserted: no GitHub event can reach a
  standing session, because the only thing that resolves events is a ref resolver that
  never sees the directory these records live in. And `the-loop sessions list` cannot show
  one for the same reason.
- A new non-work-item use case is a config entry, not a code change — the ticket's *"more
  and more use-cases for sessions outside of the work-item"*.
- The Slack surface came almost free: `ChannelState` binds a thread to an opaque string,
  so binding one to `standing:<name>` reuses the whole existing read pipeline, and only
  the mirror step (which needs a ticket) had to learn the difference.

**Harder.**

- Two registries, two sets of verbs, two rows in the state classification. An operator
  now has to know which kind of session they are looking at — mitigated by the two never
  being addressable the same way, so the question always has an answer.
- A refactor of `TmuxRunner`'s four entry points, on the path every work-item session
  already takes. Bounded by keeping the work-item methods' behaviour byte-identical, which
  the existing runner tests hold up untouched.

**Deferred.** Nothing here reads a Slack channel at large, and nothing spawns a standing
session on any lifecycle but `start`. The config shape leaves room for the second —
`autoStart` is per entry, not a global — and the first is a deliberate refusal: the bot
reads threads it was bound to, and widening that is a Slack-permissions decision, not a
standing-sessions one.

## Alternatives considered

- **Widen `WorkItemRef` with a non-work-item form** (e.g. `standing:local/supervisor#0`) —
  rejected. It would put a value with no owner, no repository and no number through code
  whose entire job is deciding which *ticket* an event belongs to, and every guard that
  today reads "this is a work item" would silently become "this is a work item, or one of
  these other things". The saving — one registry instead of two — is not worth making the
  router's central type ambiguous.
- **Model a standing session as a work item on a synthetic ticket** — rejected for the
  reason the ticket gives: GitHub is not the surface. It would also mean a real issue
  somewhere, armed, labelled, and advancing through phases it can never complete.
- **Keep the ticket's word "ad-hoc"** — rejected. `the-loop do` and `pdlc-adhoc-loop` are
  shipped vocabulary for a *different* thing, and two meanings of one word in one codebase
  is how a reader ends up looking for a spec chain that was never going to exist.
- **A `promptTemplate` key so the boot directive is configurable** — rejected. The
  directive is what tells the session it owns no work item and must not answer a phase gate
  or post a control keyword; a template key would exist only to let an operator delete it.
  The operator's own brief is appended, which is the same rule `$interaction_directive`
  already follows for work-item prompts.
