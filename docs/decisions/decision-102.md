# Decision 102: a work-item collaborator is input, never authority

- **Status:** proposed
- **Date:** 2026-08-31
- **Deciders:** @MadaraUchiha-314 (issue #307); shape proposed by the harness, pending PR review
- **Work item:** [issue-307](https://github.com/MadaraUchiha-314/the-loop/issues/307)
- **Spec:** `docs/specs/issue-307/`
- **Refines:** [decision-074](decision-074.md) (who the poll path judges, and by what
  evidence) and issue-63's one-allow-list model; sits beside
  [decision-035](decision-035.md), which named `.the-loop/collaborators.yaml` — a
  different thing that shares the word

## Context

Since issue-63 the-loop has had exactly one runtime identity allow-list for GitHub,
`routing.authorizedUsers`, and it is **global**: a login can direct every work item this
daemon watches, or none of them. Issue #307 asks for the missing middle — "sometimes a
work item needs specific collaborators whose actions can affect the running of the-loop
for a work item" — with three constraints stated in the ticket: only authorized users may
add them, they do **not** have the same permissions, and a grant is per work item and does
not travel.

The absence is not that such a person has less power. It is that they are **invisible**:
both ingress paths drop their comment before anything reads it, so an agent that asked a
question and is waiting for the one person who knows the answer never hears it. The
operator's two workarounds are both wrong — put them on `authorizedUsers`, which hands
them `the-loop cleanup` on every work item in the deployment, or relay their answers by
hand.

Two words collide here, and the collision is worth stating once: `.the-loop/collaborators.yaml`
names a *project's* stewards and their roles for the **plugin**, and the daemon never
reads it (decision-032, decision-035). This decision is about something else that the
ticket also calls a collaborator: a per-work-item runtime grant.

## Decision

1. **A work-item collaborator may be input, and may not be authority.** One sentence, and
   it is the whole permission model: *a work-item collaborator supplies input on one work
   item; an authorized user directs the loop.* Their comments on that item reach its
   session; the control keywords, spawning, arming and every human gate keep consulting
   `authorizedUsers` alone. Anything richer — a collaborator who may request changes at a
   gate but not approve, say — needs a second notion of provenance inside
   `classify-feedback` and an answer for what happens when a collaborator and an
   authorized user disagree in one round. That is a separate decision, and this one does
   not foreclose it.

2. **The grant is state on the work item, not policy in the config.** It goes in a fourth
   section of the portable record (`collaborators`, beside `control`, `poll` and `graph`)
   because it has a *lifecycle* — granted, revoked, cleared when the item closes — and
   because "an authorized user invited Dana onto this item" is true on any machine. The
   CLI config is hand-edited policy about the daemon; a roster is neither.

3. **The vocabulary carries an argument, and only a login.** `add-collaborator` and
   `remove-collaborator` are the first control commands to take one. The narrowness the
   control parser promises is kept by construction: the argument is matched against
   GitHub's login grammar and refused if it does not fit, so what reaches the store is a
   fixed-shape token, never body text. Scanning stops at the first thing after the keyword
   that is not an `@login`, so `add-collaborator @a @b — they know this area` grants two
   people and reads the prose as prose.

4. **Both seams that could turn a grant into authority are checked explicitly.** The
   control path's named-and-allowlisted-actor re-check already existed as belt-and-braces
   for actor-less poll comments; it is now load-bearing, and asserted directly. The spawn
   seam gains its own: an actor outside `authorizedUsers` who is granted on one of the
   event's refs cannot spawn a session (`collaborator-no-spawn`, settled rather than
   retried). Both halves of that test are written out rather than inferring the second
   from the first, because today's inference — that only a grant can put such an actor in
   front of the dispatcher — is exactly the kind that rots when a third admission path
   appears.

5. **Membership is asked only about the refs the event itself named.** That single rule is
   what confines a grant: it covers the work item and the pull requests whose events
   already route to its session, and reaches no other work item, without a second notion of
   scope to keep in sync with the router's linkage.

6. **The CLI verbs run in-process.** `add-collaborator`/`remove-collaborator` join
   `ask` and `sessions reset` in the documented exception to "core capabilities go through
   the control-plane service" (PR #162): a roster is a small write on a tracked record plus
   a comment, and requiring a running service for it would make the roster unfixable in
   the situation an operator most wants to fix it. The logic lives in
   `the_loop.core.collaborators`, so a route or MCP tool later is a binding, not a port.

## Consequences

**Good.** The narrowest useful thing is now expressible: one person, one work item, input
only — and it is revocable, scoped, and cleared when the work ends. The paper trail is the
existing one: the keyword on the thread, `control.command` in the event log, provenance on
every roster entry. Nothing an authorized user could do changes, and no deployment that
grants nobody behaves any differently than before — a router built without rosters takes
exactly the path it took yesterday.

**Costs, accepted.** A second allow-list is a second thing to reason about when asking
"why was this comment acted on?", answered by one new event (`routing.collaborator`). One
extra JSON read per event, on a path that already reads that record for the control
section. And the collision of the word "collaborator" survives: the ticket asked for that
spelling, so the code and the docs say *work-item collaborator* in full wherever the two
could be confused, rather than inventing a word nobody asked for.

**Out of scope, deliberately.** Collaborators at human gates (D1); org/team grants,
wildcards and expiry; a control-plane route or dashboard editor for a roster; and Slack —
`channels.slack.authorizedUsers` is a separate allow-list for a separate surface
(issue-304), and control keywords in a Slack reply stay defanged.

## Alternatives considered

| Alternative | Why not |
|-------------|---------|
| Put the rosters in the CLI config, keyed by work item | The config is the daemon's policy, hand-edited and reloaded; a roster is per-item state with a lifecycle. It would also put a work item's people on a machine rather than on the work item. |
| A `collaborator:<login>` label on the ticket | GitHub already stores it and it is visible — but labels are writable by anyone with triage rights, a *wider* set than `authorizedUsers`, so the grant's authorization would be GitHub's rather than the-loop's. The auto-execute label is safe because it is necessary-not-sufficient; a grant has no second gate behind it. |
| Let a collaborator satisfy gates with a reduced outcome set | D1: it needs provenance inside the classifier and a conflict rule. Deferred, not refused. |
| A `RoutedEvent.collaborator_only` flag set by the router | The poller builds `RoutedEvent`s by hand, so the flag would have to be set in two places and would fail open if a third appeared. The spawn seam re-reads the payload it already has. |
| Filter `routed.work_items` to the refs a collaborator holds | The refs on one event are the refs that already share one session, so the filter would change which item a comment is attributed to without changing who can reach it. |
| Widen `authorizedUsers` to per-repository or per-label scopes | Answers a different question (which *items* a login may direct) and leaves the ticket's one unanswered, at the cost of a policy language in the config. |
