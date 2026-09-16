<!-- Authored per the the-loop:writing skill. -->

# Decision 129: routing may guess which work item an event is about; tracking may not

- **Status:** proposed
- **Date:** 2026-09-16
- **Deciders:** the-loop (architect, engineer), asked for by @MadaraUchiha-314
- **Work item:** [issue-370](https://github.com/MadaraUchiha-314/the-loop/issues/370)
- **Builds on:** [decision-128](decision-128.md), which said *where* a work item's pull
  requests are recorded. This one says *who may put one there*.

## Context

[Issue #370](https://github.com/MadaraUchiha-314/the-loop/issues/370): *"the-loop
currently does some 'magic' to determine which PRs are linked to which work item … we
should remove the feature in poller which 'actively' goes and links random PRs to work
item using 'linked PR' meta-data on gh issues etc."*

the-loop has three ways to guess which work item a pull request belongs to: GitHub's
`closingIssuesReferences`, the `issue-<n>` head-branch convention, and a closing keyword
in the body ([issue-93](https://github.com/MadaraUchiha-314/the-loop/issues/93),
[issue-183](https://github.com/MadaraUchiha-314/the-loop/issues/183)). All three were
built to answer one question — *whose conversation should hear this event?* — and were
then quietly reused to answer a second: *which pull requests deliver this work item?*

The second question now has a real answer.
[Issue-274](https://github.com/MadaraUchiha-314/the-loop/issues/274) gave the session that
opens a pull request a command to say so, and
[issue-368](https://github.com/MadaraUchiha-314/the-loop/issues/368) gave the work item a
checked-in file to hold it. The guess is no longer a fallback; it is a second, conflicting
writer.

## Decision

**The two questions are separate, and only the first may be answered by inference.**

| | delivery — "whose conversation hears this?" | tracking — "which PRs deliver this work item?" |
|---|---|---|
| answered from | closing references, `issue-<n>` branch, closing keywords, recorded bindings | the recorded binding alone |
| written where | nowhere durable — re-decided per event | `work-item-state.json`, `portable/<slug>.json` |
| a wrong answer costs | one misrouted comment, corrected by the next event | a row in a committed file that nobody can explain and nothing removes |

Concretely, three removals and one addition:

1. The poller resolves a labelled pull request's ledger owner from the session-registry
   binding and the existing portable ledgers, and from nothing else. A pull request that
   answers neither is a work item in its own right.
2. `work-item-state.json`'s `pullRequests[]` is written only by `the-loop sessions
   link-pr`. `linkedBy` is `session` for every row the-loop writes; an `event` row from
   before this change is read and kept, never rewritten.
3. the-loop asks GitHub nothing about which pull requests relate to a work item: the
   `linked-pulls` integration op is retired, and a work-item review's scope is pre-filled
   from what the-loop recorded.
4. Because the record is now load-bearing, it stops depending on a model remembering a
   rule: a `PostToolUse` hook runs `link-pr` when a session creates a pull request, and
   the tmux runner exports `THE_LOOP_WORK_ITEM` so the plugin's hooks know which work item
   they are in.

**Delivery is explicitly untouched.** The router still resolves a pull request's work
items from all three sources, so a review comment on a contributor's pull request still
reaches the work item's session.

**And the rule is uniform across what a work item *is*.** the-loop is armed four ways —
`start` and `do` on a work item, `review` and `contribute` on a pull request — and the
entity it manages is one work item whatever represents it: a GitHub issue, a Jira story, a
pull request, whatever comes next. So a pull request armed as its own work item is recorded
in `pullRequests[]` the same way one the-loop opened for an issue is, marked `self: true`
and carrying no `stateDir` (the work item's own directory is the loop; an inner-loop path
would nest a copy of it inside itself). One list, one answer to "which pull requests does
this work item involve?", and a marker rather than a ref comparison to say which of the two
relations a row has. Owner ruling on
[PR #372](https://github.com/MadaraUchiha-314/the-loop/pull/372).

## Consequences

- A pull request the-loop did not open is not part of a work item's tracking unless
  somebody says it is — which is the point, and is also a behaviour change an operator may
  notice as *more* portable records than before. Each of those is a real work item with a
  real ledger; none is new state.
- A pull request already ledgered under a work item keeps that owner. Nothing migrates:
  after the fact, nothing distinguishes a correct filing from an inferred one, so a sweep
  would be a guess about guesses.
- A work-item review's `Pull requests:` scope gets *better*, not smaller: the recorded
  list can see a spec pull request, which closes nothing and which GitHub's linkage
  therefore never held.
- In a harness that runs no `PostToolUse` hook — Cursor, a bare session — recording the
  pull request is still the agent's prose rule, and skipping it now costs the tracking as
  well as the routing.

## Alternatives rejected

- **Infer "this work item is a pull request" from the selected loop.** `review` and
  `contribute` are the two guest loops, so loop membership looks like the signal.
  Rejected: `the-loop contribute` can join an issue as readily as a pull request, so the
  loop answers a different question. The arming event is the one place that knows, and it
  is already parsed.

- **Remove the router's delivery linkage too**, the literal reading of "remove the magic".
  It would silently stop delivering review comments on every pull request the-loop did not
  open — the contribution loop's whole subject. Recorded as out of scope in
  `docs/specs/issue-370/requirements.md` rather than done quietly.
- **Keep `linked-pulls` as a suggestion**, since a human edits the pre-fill anyway. The
  ticket names the active search as the thing to stop, and the local answer is now
  strictly better than the remote one.
- **Sweep `portable/` on upgrade.** See above: unfilable after the fact.
- **Keep the prose rule and change nothing else.** It is what the inference was covering
  for. Removing the cover without fixing the cause would trade a wrong record for a
  missing one.
