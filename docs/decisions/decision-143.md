# Decision 143: a quiz gate is answered by an attributed tick

- **Status:** proposed (the owner decides at the PR)
- **Date:** 2026-10-15
- **Work item:** [issue-488](https://github.com/MadaraUchiha-314/the-loop/issues/488)
- **Deciders:** MadaraUchiha-314 (the ask, `requirements-approval`, `design-approval`),
  the-loop (design)
- **Refines:** the "ticking happens in place, and the reply is the signature" rule of
  `phase-selection` (`cli/the_loop/graph/hooks/selection.py`, PR #178). That rule stands
  for `phase-selection`.
- **Spec:** [`docs/specs/issue-488/design.md`](../specs/issue-488/design.md) §C4, §C5,
  §Trade-offs

## Context

**the-loop never trusted a ticked box on its own.** The reason is recorded in
`selection.py`: "GitHub cannot tell us who edited a comment". An authorized user's
`the-loop execute` reply is what signs the tick state. Issue-488 asked for the opposite
ergonomics for its two quiz gates: the author ticks one box and nothing else, with no
reply.

That premise is true of GitHub's REST API. It is not true of GraphQL:
`IssueComment.userContentEdits{editor{login} editedAt}` names every editor of a comment,
and the-loop's client already speaks GraphQL (decision-139).

## Decision

1. **The quiz gates (`spec-quiz`, `code-quiz`) pass on a tick.**
   - The box must be in the-loop's own marked comment for that node, round and spec
     digest.
   - The **latest** edit must have been made by a user in `routing.authorizedUsers`, as
     GitHub's GraphQL edit history reports it.
   - An unknown editor, an empty history, a failed query, a comment without the-loop's
     markers, or a tick from an earlier round keeps the gate waiting (fail closed). The
     unknown-editor check is made before `is_authorized` is consulted, because that
     function lets an actor-less event through.
2. **Edits are noticed without new infrastructure.**
   - The poller already re-reads every thread every cycle. It now rings the waiting gate
     when the-loop's own quiz comment reads ticked.
   - The webhook rewrites an `issue_comment.edited` of that comment into the same
     doorbell, before the self-reply guard drops it.
   - The doorbell is delivery-only: no prompt is rendered or delivered, and nothing
     spawns. It carries a comment id and no body or actor. The gate finds its own comment
     on the thread and asks GitHub who ticked it.
3. **An authorized typed reply carrying the ticked line is the fallback.** This is the
   same rule `phase-selection` uses, where the reply's own checklist wins. It covers Jira,
   which reports no editor, and a missed edit.
4. **`phase-selection` keeps its reply-is-the-signature rule.** Its checklist is a whole
   configuration that anyone may edit before execute. A quiz box is one attestation by
   whoever ticked it, so the person who ticked is the person who answered.

## Consequences

- **The author's ergonomics are one click**, attributed and recorded in
  `work-item-state.json` under `decisions["spec-quiz"|"code-quiz"]`, with `attestedBy`,
  `attestedAt`, `comment` and `via`.
- **One GraphQL query per detected tick**, not per cycle. A refused tick is logged once,
  because the doorbell is keyed by comment and body hash.
- **The residual risk: whoever holds the operator's token can tick as the operator.**
  the-loop posts under the operator's account, so any process holding that token could
  tick the box, and GitHub would name the operator. This is the same trust every human
  gate already rests on: an unmarked "approved" posted with that token passes
  `classify-feedback` too. Keeping the token out of spawned sessions (issue-482) is the
  control. Issue-488's implementation found a session that still held one; that is
  recorded in the work item's security review and raised on PR #489.
- **The quiz itself is self-attested.** the-loop records who said they took it, never a
  score.
