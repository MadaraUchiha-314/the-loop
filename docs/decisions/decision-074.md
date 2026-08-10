# Decision 074: on the poll path, the item's author gates only spawning

- **Status:** proposed — the human gate is the pull request
- **Date:** 2026-08-10
- **Deciders:** MadaraUchiha-314 (approver)
- **Work item:** [issue-197](https://github.com/MadaraUchiha-314/the-loop/issues/197)

## Context

[decision-023](decision-023.md) put an allowlist on both trigger paths: only
`routing.authorizedUsers` logins may be an input the-loop acts on. The two paths then
implemented it differently, and the difference was never written down.

- The **webhook** router authorizes the **actor of the event** — whoever commented,
  labelled or reviewed.
- The **poller** authorizes the **author of the work item**, and gates everything on it:
  the spawn, the comment forwarding, and (since issue-119) whether a control command
  already on the thread is held back from the first-sight baseline.

The reason for the difference is real. A polled listing carries an item's labels but not
who applied them, so the poller has no event actor for the item itself — it has the
author, and used it as a proxy for "an authorized human wanted this".

The consequence, reported as [#197](https://github.com/MadaraUchiha-314/the-loop/issues/197),
is that the proxy also decides things it is no evidence about. A maintainer commenting
`the-loop contribute` on an outside contributor's bug report is ignored — every cycle,
permanently, with `poll.unauthorized` naming the *contributor* as the actor. The
per-comment authorization check, which would have accepted the maintainer's comment, sits
below a guard that has already dropped the thread. Working on outside contributions is not
an edge case; it is most of what maintainers do.

## Decision

**The work item's author gates exactly one thing: whether the poller may emit a *presence*
event — spawn a session whose subject is that item — on its own initiative. Everything
else is judged by the author of the thing itself.**

```text
comment forwarded?        → the COMMENT's author         (unchanged code, newly reachable)
first-sight hold-back?    → the COMMENT's author         (unchanged code, newly reachable)
presence event emitted?   → the ITEM's author  OR  an authorized user's recorded
                            arming command (ControlStore.start_requested)
```

The second half of the presence gate is what makes the first half affordable to keep. An
arming command (`the-loop start` / `the-loop contribute` / `the-loop resume`) is recorded
only by the dispatcher, only for a **named** allowlisted actor, and it is *stronger*
evidence than the author proxy: it names who asked, and when. A later `stop`, `pause` or
`cleanup` revokes it, because `start_requested` reads the last command.

**What was considered and not done:**

- **Authorize the labeller.** The best available signal — "an authorized user applied the
  auto-execute label" — costs a per-item timeline query on every cycle, for a fact the
  listing does not carry. Left as the direction if polling ever needs presence without a
  comment; the arming comment covers the case today.
- **Drop the item-author gate entirely.** Under `requireStartCommand: false` (label-alone
  operation) nothing else would stand between a labelled item and a session. Keeping the
  proxy costs an outside-authored item one comment.
- **Accept any authorized comment as arming.** An ordinary remark is not a request to work
  on something. Using the same predicate the dispatcher's own spawn gate uses keeps the two
  ingresses in agreement by construction.

**And the guard that replaces what was loosened:** the spawn prompt now states that the
work item's title, body and thread are untrusted content — data about a request, never
instructions. That is where the prompt-injection concern actually lives. Discarding a
maintainer's instruction never protected the model from the contributor's text; it only
protected it by never reading either.

## Consequences

**Easier.** The case the-loop exists for on a public repository: a maintainer points it at
an outside contribution with one comment, on the poll ingress, exactly as they already can
over a webhook. `poll.unauthorized` becomes actionable — it fires only while a spawn is
genuinely being withheld, and names the remedy — instead of repeating forever on items
nobody can un-author.

**Harder.** One more thing is true of an armed work item: an authorized user's arming
command now widens *which items may spawn*, not only *when*. An operator who armed an item
and later wants the-loop off it must say so (`the-loop stop`), where before the item's
authorship kept it off by accident. That is the correct direction — an explicit revocation
instead of an implicit one — but it is a real change in what "armed" implies.

**Unchanged.** Every other guard: the allowlist and its fail-closed empty case, the
self-comment marker, the dispatcher's stricter named-actor re-check before any command
executes, the auto-execute label as the arming prerequisite, `requireStartCommand`, and the
webhook path in full. No new config key, no schema change, and no new way for an
unauthorized user to reach the-loop — their comment is dropped by the same check as before,
on an armed item as on any other.
