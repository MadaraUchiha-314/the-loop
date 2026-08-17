# Decision 093: how many sessions a work item's pull requests get is the work item's choice — the operator states the default

- **Status:** proposed
- **Date:** 2026-08-17
- **Work item:** [issue-260](https://github.com/MadaraUchiha-314/the-loop/issues/260)
- **Deciders:** maintainer (via ticket); harness (proposal)
- **Refines:** [decision-092](decision-092.md) — specifically the premise its title states,
  that the choice is the **operator's**. Its D1 (three named modes), D2 (the booleans keep
  parsing), D3 (fail closed to `cross-repository`), D4 (`require_branch`) and D5 (`always` is
  served by `strategy: clone`) all stand unchanged; only *who decides* moves.
  Extends [decision-069](decision-069.md) — the same argument that put
  `outer-loop-on-pull-request` at `phase-selection`, applied to a second question.

## Context

Decision-092 shipped on 2026-08-17 and gave "how many tmux+claude sessions do a work item's
pull requests get?" to `routing.tmux.sessionPerPr` — one value, per machine, for every work
item that daemon serves. The ticket's author read the merged pull request and objected the
same day:

> Why the fuck did we give this option to the operator? This should be an option that's
> selectable at phase selection. […] The default should come from cli-config and phase
> selection should override it.

The objection is not new; it is [decision-069](decision-069.md)'s, one question over.
issue-183 had to decide where the outer loop's artifacts are iterated, refused to make it a
config key, and wrote down why:

> not in any config file, because one repository has both a one-repo bugfix and a three-repo
> migration

That sentence is true of *this* question too, and more sharply: a three-repo migration wants
a conversation per pull request precisely because its pull requests are in different
repositories doing different work, while the doc fix in the next ticket over wants one. A
machine-wide value must answer for both, so the operator picks the lesser wrong answer and
every work item that machine serves inherits it.

issue-258's own requirements list *"a per-work-item override of the choice"* under Out of
scope, with the reason: *"the ticket asks for an operator option; a spec-front-matter override
is a different question and nobody has asked it."* Nobody had. The person whose call it is
now has — and has also said where the override belongs, which rules out the front-matter
shape that sentence was declining.

## Decision

**`phase-selection` owns the choice; `routing.tmux.sessionPerPr` becomes its default.**

| Sub-decision | What was chosen | Why |
|---|---|---|
| **D1 — the gate asks, the config answers when nobody did** | three checklist rows, the configured value pre-ticked, frozen by the same authorized `the-loop execute` | One human act, one signature, one frozen record. The gate already carries a non-phase question of exactly this shape (`outer-loop-on-pull-request`), and adding a second costs no new authorization path, no new channel and no new permission model. |
| **D2 — three rows, not one box** | `pr-sessions-never` · `pr-sessions-cross-repository` · `pr-sessions-always` | A checkbox has two states and the question has three. Collapsing two of them is the complaint decision-092 was written to answer; reintroducing the collapse one level up would be the same bug in a new place. |
| **D3 — anything but exactly one ticked row is the default** | none ticked, several ticked, an unreadable checklist, a token outside the vocabulary → the configured value | Fail closed here means *the value already in force*, not the narrowest mode: it is what the operator stated, what every work item ran on before the question existed, and the only answer that is never a guess. Guessing which of two ticks a human meant is how a three-repo migration silently gets one conversation. |
| **D4 — the frozen answer travels in the portable record** | `graph.sessionPerPr`, beside the frozen graph and `surface` | "How this work item's pull requests are routed" is true on any machine, like the phases and the surface. It is also the only copy the **daemon** reads — `graph-state.json` needs a checkout, and the dispatcher has none. |
| **D5 — the frozen answer wins over a later config change** | the record is read first; the config answers only in its absence | A frozen selection is a recorded agreement (issue-177). A work item whose routing silently changed under it, because the operator edited a file a week later, would be the same complaint one level down. |
| **D6 — every loop that reaches the gate is asked** | the work-item, contribution and ad-hoc loops; `pdlc-pr-loop` reaches it at all | Unlike the surface (issue-199), this question has a true answer for a contribution: its pull request is usually in **another** repository, which is exactly the case the modes disagree about. |
| **D7 — the vocabulary moves below both readers** | `the_loop/prsessions.py` | The gate and the dispatcher both need the three names, and the gate cannot import the dispatcher (`dispatcher → graphlink → graph` is a cycle). Two copies of a three-name vocabulary is how a config file and a checklist come to disagree about what `always` means. |

Nothing else moves. The schema is unchanged — same type, same enum, same default. No new
event name, no new `reason` value, no change to `pullRequests[]`, no state migration, and a
work item that leaves the rows alone routes byte-for-byte as it did before.

## Consequences

**Good.**

- The one-repo bugfix and the three-repo migration in the same repository can differ, which
  is the whole reason the choice exists.
- Every answer is attributable: a named authorized human, in a comment, frozen with the
  phases they chose in the same act — the property issue-177 exists to preserve.
- The operator's value keeps a real job. It is the sensible default for a deployment (a
  machine with no `routing.workspace.root` genuinely cannot serve `always`), and it is what
  the checklist offers rather than a constant.

**Costs, accepted.**

- The checklist grows three rows. Mitigated by pre-ticking the default and by stating in
  prose that leaving them alone changes nothing.
- The daemon reads one more small JSON section per routed pull-request event. It already
  reads the session registry from disk on that path.
- A work item can now choose a mode its deployment cannot serve (`always` with no workspace
  root). It is declined at the spawn seam exactly as an operator's `always` would be, with
  `session.pr_session_declined` — decision-092 D4 is not relaxed by moving the switch.

## Alternatives considered

| Alternative | Why not |
|---|---|
| **Leave it in the CLI config** | The rejected status quo. One value cannot answer for two work items on one machine. |
| **A key in `harness-config.yaml`** | Per repository rather than per work item — the same failure one scope in, and issue-183 already refused it for the surface. |
| **Spec front matter (`execution-log.md`)** | The shape issue-258 declined. It is agent-writable with no signature, so the routing a work item runs under would stop being attributable to a human — the exact property `phase-selection` exists to hold. |
| **A single `pr-sessions-always` box, config for the rest** | Two of the three modes then remain unreachable per work item, and which two depends on the operator's value. A choice that changes shape depending on a config file is not a choice a reader can trust. |
| **Read the config on every event and ignore the freeze** | Makes the recorded agreement a lie: `the-loop check` and the portable record would name a mode the daemon was not using. |
| **A CLI verb to set the mode after freezing** | Re-answering a frozen selection is a general question (`the-loop graph skip` is its sibling for phases). Nobody has asked it, and inventing it here would ship an unaudited second channel. |
