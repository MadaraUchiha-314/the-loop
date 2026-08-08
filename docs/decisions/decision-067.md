# Decision 067: Skips are declared — the graph fixes the vocabulary, a human selects, the runtime never forges

- **Status:** proposed
- **Date:** 2026-08-08
- **Deciders:** @MadaraUchiha-314 (pending PR review)
- **Work item:** issue-177
- **Spec:** `docs/specs/issue-177/`
- **Refines:** [decision-041](decision-041.md) (the PDLC is an executable graph — the
  fixed graph is precisely why the harness cannot invent skips) and the `force` posture
  of issue-109 R10 (an override moves the pointer and never forges a verdict; a declared
  skip is that posture made *plannable*).

## Context

[Issue #177](https://github.com/MadaraUchiha-314/the-loop/issues/177): the-loop walks
every work item through every phase, so a simple documentation update ships with a full
`requirements.md`/`design.md` chain ([PR #175](https://github.com/MadaraUchiha-314/the-loop/pull/175)
is the motivating example). The obvious fix — let the harness decide what to skip — is
the one the ticket forbids: *"If the LLM // coding harness decides which steps to skip,
it might accidentally skip requirements or design conveniently which is the whole point
of having a fixed graph."* The ask: a strategy where **the author of the work item or an
authorized user starting the-loop** specifies which phases can be skipped.

## Decision

**Three parties, one skip — each holding the part it can be trusted with.**

| Sub-decision | What was chosen | Why |
|---|---|---|
| **D1 — the graph fixes the vocabulary** | `skippable: true` per node in the shipped graph; compile-refused on a `required` node, without an `on: skipped` edge, or via a `skipSets` member outside the vocabulary. The outer loop marks exactly the spec chain: `brainstorming`, `requirements-definition`, `requirements-approval`, `design`, `design-approval`, `tasks-breakdown` | The graph already ships as package data a repository cannot override (issue-109 R1.4), so putting the vocabulary there is what makes it unwidenable by harness, repo or work item. Routing is authored (`on: skipped`), never inferred — every structural failure is a startup failure. |
| **D2 — the floor never moves** *(REVISED by [decision-068](decision-068.md): issue-179 made every phase but `phase-selection` selectable — the floor is now that single invariant, not a set of phases. Read 068 before relying on the row below.)* | `test-planning`, `implementation`, `verification`, the review chain (`security-review` still `required`), `human-approval` and `complete` carry no marker; the inner `pdlc-pr-loop` declares none | Every change keeps a proof: the testing plan's matrix scales down honestly (`n/a` with a reason per row — a doc fix's plan is a few lines naming markdownlint), and a `verification` gate whose subject can vanish is the issue-124/167 shape (a gate passing without running). Because the floor always runs, the worst any illegitimate declaration achieves is a lighter paper trail on the way to a human who can see the skip records. |
| **D3 — a human selects at the loop's own first phase** *(revised — see below)* | The outer loop starts at a **human** node `phase-selection`: its entry posts one checklist of the selectable phases on the ticket, its exit waits for an **authorized** user (`authorizedUsers`) to reply with the phases to keep plus `the-loop execute`. `the-loop graph skip <id> --node <token> --reason <why>` is the same declaration from an operator's shell — `force`'s sibling: reason required, actor recorded, marked audit comment, `graph.skips_declared` | The loop already knows who may direct it, and it is not GitHub's label permission: `authorizedUsers` is the boundary `the-loop start` and every human gate answer to. Selection on the ticket reuses it exactly, needs nothing created per repository, and puts the choice where the conversation already is. The harness has no channel: sessions are instructed never to answer the gate or run the verb, and only an authorized author's **reply** is read — never the checkboxes on the-loop's own comment, since GitHub reports that a comment was edited but never by whom. |
| **D4 — declarations never reach backwards** | A declaration applies only to nodes still ahead of the pointer: the selection gate's own result is filtered against entered nodes, and the verb refuses tokens naming a node already current, entered, or behind | A skip is a plan, not an amnesty. Without it, a work item blocked at a gate could be talked past it after the fact; with it, the worst a late declaration achieves is nothing. |
| **D5 — a skip routes and records; it never forges** | The pointer takes the node's `skipped` edge without running its hooks; the record says outcome `skipped` (`graph.node_skipped`); `check` — `--recompute` included — reports *skipped by declaration* with provenance (via, token, by, reason), never `pass`; a declaration on a non-skippable node is inert everywhere and surfaced on the node it touched | The `force` invariant, applied to the planned case. Recompute honours valid declarations because a declaration is a recorded human input with an off-repo audit trail (the authorized reply, the marked confirmation comment) — not the state file scoring itself — while the skippable-only filter is re-applied on every read, so tampering with the protected gates is structurally pointless. |
| **D6 — later gates treat a declared absence as planned** | `HookContext.skipped_artifacts`; `validate-artifacts` skips an absent slot all of whose accepted names are authored by declared-skipped nodes, and gates a present artifact unchanged | `implementation` re-gates `tasks.md`; with `tasks-breakdown` legitimately skipped that gate would otherwise block forever. Tolerating only *absence* keeps the rule tight: declaring a skip never weakens a gate over work that was actually produced. |

## What this deliberately does not do

- **No harness-inferred skips** ("docs-only diff → skip specs"): the decider would be the
  party being gated — the ticket's own veto.
- **No front-matter channel**: the spec files are agent-authored, so `skips:` in
  front-matter would hand the declaration to the untrusted party.
- **No skip labels** — see the reversal below.
- **No per-lane alternative graphs** (a `docs-loop` beside the work-item loop): N graphs
  to keep in parity for what is one loop with declared detours; `skipSets.spec-chain`
  buys the same one-token ergonomics.
- **No config toggle** (`workflow.allowSkips`): a knob without safety — an operator who
  wants no skips keeps every phase ticked.
- **No MCP exposure** of the verb, exactly as `force` is absent there: human-attributed
  verbs stay on human-attributed surfaces.
- **Honest about the residual**: within the repository the enforcement is *audit and
  floor*, not cryptography. An agent hand-writing a declaration on a *skippable* node
  into `graph-state.json` is detectable (its claimed channel's off-repo trail will not
  corroborate it) and bounded (D2's floor still gates the item) — the same trust model
  as `graph-state.json` itself: a cache, never an authority.

## Consequences

- A documentation fix is one reply away from the lean walk: untick the spec chain, say
  `the-loop execute`, and the item goes implementation → verification → reviews → human
  approval — with each skip visible, with provenance, in `the-loop check` and on the
  ticket.
- **Every work item now opens with a question**, which is a real cost: nothing walks a
  phase until an authorized human answers. That is the point (the selection is the
  authorization), and `the-loop execute` with no list is the one-line "run everything".
- The phase labels stay truthful: skipped phases never get a label; the ticket shows
  `loop:phase-selection` while the loop waits, then jumps to the first walked phase.
- CI (`check --recompute`) reports skipped nodes as skips, so a reviewer approving the PR
  is also approving the declared shape of the work item — which is where issue-177 wanted
  the judgement to live.

## Revisions from owner review (PR #178, second round)

Three corrections, all adopted:

1. **`execute` belongs in `routing.control`.** *"This also should be part of the
   cli-config."* The first build kept it as the gate's private vocabulary to avoid a
   disableable keyword; that was the wrong trade. It is a control word an authorized
   human types on a ticket — the definition of that vocabulary — and an operator who
   renames `the-loop start` expects to rename this too. It joins `COMMANDS` with the
   same named-actor authorization, and differs only in effect: it touches no session,
   and the comment carrying it is **still delivered**, because the gate is what reads
   the selection. An unset or empty keyword falls back to the built-in default, so the
   loop cannot be wedged by configuration.
2. **Ticking happens in place.** *"I want the nicer ergonomics of ticking in place."*
   The objection was that GitHub never reports *who* edited a comment. Reconciled rather
   than dropped: the tick state is a **proposal**, and an authorized user saying the
   execute keyword is the **signature** over it. A checklist inside the execute comment
   still wins, for anyone who wants it unambiguous.
3. **The selection freezes, and the frozen graph is portable.** *"When the authorized
   user then says `the-loop execute`, then the graph is frozen and then the execution
   starts. The graph that's executed also needs to be stored in the portable part of the
   tracking of work items."* Answering the gate now records the resolved graph — every
   node with `skipped` and `selectable` — in `graph-state.json` **and** in the `graph`
   section of the work item's portable record, beside `control`. That is what makes a
   later edit to the checklist comment inert, and it means the agreed shape of a work
   item is readable without a checkout.

## Reversal: the label channel, and why it is gone (owner review, PR #178)

The first implementation of D3 used **ticket labels** (`loop:skip:<node-or-set>`, read
once at graph entry). The owner rejected it on review, for two reasons that hold:

> *"A label is not the right way to go about it since it breaks the authorization
> principle of the loop. … A label needs to be created in all the repo etc and is
> tedious. Can we add a reply comment to the work item … with all the phases … and the
> user can choose which stages are required? This is the 'first phase' and then we can
> start with the actual phases."*

1. **It introduced a second authorization model.** the-loop's own boundary is
   `authorizedUsers` — who may `the-loop start`, whose review classifies a gate. A label
   channel silently substituted GitHub's triage permission for it, which is neither the
   same set of people nor a boundary the-loop can reason about. The rebuilt channel uses
   the loop's own boundary, so there is exactly one answer to "who may direct this loop".
2. **It was setup work in every consuming repository.** Seven labels to create before a
   feature could be used at all, for something that is naturally a conversation.

The mechanism the labels fed — the compile-checked `skippable` vocabulary, the
skip-sets, the routing, the never-forge reporting, the tamper filter — is unchanged: only
the declaration channel was replaced. What the rebuild *added* is the owner's second
point, that selection is itself the work item's first phase (`phase-selection`) and the
loop starts walking on `the-loop execute`.
