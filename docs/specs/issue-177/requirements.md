---
type: requirements
phase: requirements-definition
workItem: issue-177
status: approved              # draft | in-review | approved
approvedBy: []                # recorded on the PR review (paper trail)
riskTier: 4
collaborators: [product-manager, architect, engineer, approver]
overrides: {}
---

# Requirements: declared skips — the author decides which phases a work item walks

> Phase 1 of 4 (requirements → design → testing plan → tasks). Ticket:
> [issue #177](https://github.com/MadaraUchiha-314/the-loop/issues/177).

## Introduction

**the-loop walks every work item through every phase, and for a simple documentation
update that is process without payoff** — [PR #175](https://github.com/MadaraUchiha-314/the-loop/pull/175)
carried a full `requirements.md`/`design.md` chain for a doc fix. The obvious repair —
let the harness decide what to skip — is the one the ticket explicitly forbids: an LLM
that may skip phases will eventually skip `requirements` or `design` *conveniently*,
which defeats the point of a fixed process graph.

The strategy this work item delivers is **declared skips**, split across three parties so
no single one can cheat:

- **The shipped graph** declares which nodes *may* be skipped (`skippable: true`) — a
  fixed vocabulary the harness cannot extend, shipped as package data a repository cannot
  override. The floor (`verification`, `security-review`, `human-approval`) is never in
  that vocabulary.
- **A human** — an authorized user of the loop — declares which of those nodes *are*
  skipped for one work item, at the loop's own **first phase**: the-loop posts a phase
  checklist on the ticket and waits for their reply plus `the-loop execute`. An operator
  may make the same declaration from a shell with an audited CLI verb. The harness never
  declares a skip.
- **The runtime** records each skip as a *declaration with provenance* and routes around
  the node along a declared edge. A skip is never a forged `pass`: `the-loop check`
  reports it as skipped-by-whom, and a declaration on a non-skippable node is refused
  loudly.

This is the same posture `the-loop graph force` established (decision-041): the escape
hatch moves the pointer and leaves the truth intact. Declared skips are the *planned*
version of that hatch — declared up front, bounded by the graph, and visible everywhere.

## Requirements

### Requirement 1 — the graph owns the skip vocabulary

**User story:** As the maintainer of the process, I want the set of skippable phases fixed
in the shipped graph, so that no harness, repository or work item can widen it.

#### Acceptance criteria

1. WHEN the graph compiler reads a node carrying `skippable: true` THEN the system SHALL
   expose that marker on the compiled node and in `graph show`.
2. WHEN a node declares both `required: true` and `skippable: true` THEN compilation
   SHALL fail naming the node — a mandatory gate cannot also be skippable.
3. WHEN a node is declared skippable and no `on: skipped` edge leaves it THEN compilation
   SHALL fail naming the node — routing around a node is declared, never inferred.
4. WHEN the graph declares a `skipSets` bundle THEN compilation SHALL fail if any member
   names an undeclared or non-skippable node, naming the set and the member.
5. WHEN the shipped outer loop (`pdlc-work-item-loop`) is compiled THEN exactly
   `brainstorming`, `requirements-definition`, `requirements-approval`, `design`,
   `design-approval` and `tasks-breakdown` SHALL be skippable, and a shipped
   `spec-chain` skip set SHALL name exactly those six nodes.
6. WHEN any set of skips is declared THEN `test-planning`, `implementation`,
   `verification`, the review chain (`self-review`, `critic-review`, `security-review`,
   `evidence`, `capability-docs`, `reviewer-briefing`), `human-approval` and `complete`
   SHALL still be walked and gated — none of them carries the skippable marker.

### Requirement 2 — only a human declares a skip, and the loop asks first

**User story:** As an authorized user of the loop, I want to be asked up front which
phases this work item needs, so that a doc fix does not produce a spec chain — and so
that the agent can never make that call.

#### Acceptance criteria

1. WHEN a work item enters the graph THEN the system SHALL enter a `phase-selection`
   node first, and SHALL post to the ticket one checklist naming every skippable phase
   of the loop being walked (pre-ticked) and every phase that always runs.
2. WHEN the checklist has already been posted for a work item THEN a later entry SHALL
   NOT post a second one.
3. WHEN no authorized reply carrying `the-loop execute` has arrived THEN the node SHALL
   `wait`, and no phase of the loop SHALL run.
4. WHEN an **unauthorized** author replies with a selection and `the-loop execute` THEN
   the system SHALL ignore it entirely and keep waiting.
5. WHEN an authorized user says the execute keyword THEN the selection SHALL be taken
   from the **current tick state of the-loop's own checklist comment** — unless the
   execute comment itself carries a checklist, which wins. Every **unticked skippable**
   phase SHALL be recorded as a declared skip with provenance (`via: selection`, the
   author, the phase, a timestamp), every **unticked protected** phase SHALL be refused
   and named back in a confirmation comment, and the loop SHALL proceed to the first
   phase that survived.
6. WHEN the execute comment carries no checklist and the checklist comment cannot be read
   THEN no skip SHALL be recorded — the full process runs (fail-closed).
7. WHEN a selection omits a phase entirely THEN that phase SHALL be kept: a selection
   removes only what it explicitly unticks.
8. WHEN posting the checklist fails THEN the node SHALL remain `wait`ing, no skip SHALL
   be recorded, and a later entry SHALL post it again.
9. WHEN a selection has been read but posting the **confirmation** fails THEN the
   recorded declaration SHALL still stand and the loop SHALL proceed — the confirmation
   is an audit convenience, exactly as the forced-transition announcement is, and the
   declaration itself is durable in graph state.
10. WHEN an operator runs `the-loop graph skip <id> --node <token> --reason <why>` THEN
    the system SHALL record each declaration with the actor and reason, post a
    self-marked audit comment, and emit `graph.skips_declared`.
11. WHEN that verb is invoked without a non-empty `--reason` THEN it SHALL be refused,
    exactly as `force` is.
12. WHEN a skip token — from either channel — names an unknown node, a non-skippable
    node, or a node the pointer has already entered or passed THEN it SHALL NOT take
    effect: the verb refuses it by name, and a selection simply does not record it.
13. WHEN the gate is answered THEN the resolved graph — every node with whether it is
    walked and whether it was selectable — SHALL be recorded in the work item's graph
    state **and** written to the `graph` section of its **portable** record, so the
    agreed shape travels with the work item and is readable without a checkout. A
    failure to write the portable copy SHALL NOT gate the selection.
14. WHEN the operator configures `routing.control.keywords.execute` THEN that keyword
    SHALL be what the gate looks for and what the checklist tells the user to say.

### Requirement 3 — a skip routes and records; it never forges

**User story:** As a reviewer, I want every skipped phase visible with who declared it,
so that reviewing a lightweight work item includes reviewing the decision to make it
lightweight.

#### Acceptance criteria

1. WHEN the pointer would enter a declared-skipped node THEN the runtime SHALL record
   outcome `skipped` for that node, SHALL run none of its entry or exit hooks, and SHALL
   follow its declared `on: skipped` edge to the next node.
2. WHEN `the-loop check` (with or without `--recompute`) reports a declared-skipped node
   THEN it SHALL report status `skip` carrying the declaration's provenance — never
   `pass`.
3. WHEN graph state declares a skip on a non-skippable node (a tampered or hand-edited
   state file) THEN the declaration SHALL have no effect anywhere: the node is evaluated
   on its artifacts alone and the report SHALL surface the refused declaration.
4. WHEN a later gate validates an artifact whose authoring node was declared-skipped and
   the artifact is absent THEN that artifact SHALL be treated as skipped rather than
   blocking (e.g. `implementation`'s `tasks.md` checkmark gate after `tasks-breakdown`
   was skipped). An artifact that exists is gated normally regardless of declarations.
5. WHEN a node is skipped THEN its phase label SHALL NOT be applied — the ticket's label
   moves to the first non-skipped node entered.

### Requirement 4 — the boundary is stated

**User story:** As an operator, I want to know exactly where declared skips apply, so
the mechanism cannot be stretched past its design.

#### Acceptance criteria

1. WHEN a pull request's inner `pdlc-pr-loop` runs THEN declared skips SHALL have no
   effect on it — the inner loop's nodes are precisely the never-skippable floor, and
   v1 scopes the mechanism to the outer loop.
2. WHEN `the-loop graph skip` would be exposed over MCP THEN it SHALL NOT be — like
   `force`, it is a human-attributed verb, absent from the MCP surface by design.

## Security considerations

> Threat-model-lite (`security.threatModel.required`). The new attack surface is the
> selection channel itself: a mechanism for legitimately *not doing* process steps is, by
> construction, a target for illegitimately not doing them.

- **Untrusted actors.** (a) The agent/harness working the item — it can write
  `graph-state.json`, spec files and (because it posts with the operator's credentials)
  ticket comments; the entire design assumes it will try to skip conveniently. (b) Anyone
  who can comment on the ticket but is not in `authorizedUsers`. (c) A hand-edited or
  corrupted state file.
- **Trust boundaries.** (1) *Who may declare:* `routing.authorizedUsers` — the loop's own
  boundary, the same one `the-loop start` and every human gate use — checked by the
  shared `_authorized_comments` reader, which also drops the-loop's own self-marked
  comments so the gate can never answer itself. (2) *What may be declared:* the skippable
  vocabulary ships inside the CLI package (existing R1.4 of issue-109 — a repo-supplied
  graph is ignored), and the runtime re-filters every declaration through it on **each**
  read, so neither a repository, a session, nor a hook can mark `security-review`
  skippable. (3) *When:* a declaration only ever applies to a node still ahead of the
  pointer.
- **Abuse cases.**
  - *The agent posts `the-loop execute` on the work item's behalf.* Refused unless it
    posts as an authorized user; and its own comments carry the self-authored marker,
    which the reader drops before authorization is even considered. The skill states the
    rule explicitly so the behaviour is not merely mechanical.
  - *An unauthorized commenter selects phases away.* Ignored; the gate keeps waiting.
  - *Someone unticks boxes on the-loop's own checklist comment.* Ticking is the intended
    ergonomics (owner's call), and GitHub cannot tell us who edited a comment — so the
    tick state alone is a **proposal**, never an instruction. What authorizes it is an
    allowlisted human saying the execute keyword over it, and the selection is **frozen**
    at that moment: later edits to the comment change nothing, because the resolved graph
    is already recorded in graph state and in the portable record. Anyone wanting the
    unambiguous form puts the checklist in the execute comment itself, where it wins.
  - *A reply unticks a protected phase.* Refused, named back in the confirmation, and the
    phase runs.
  - *The agent writes skips into `graph-state.json` directly.* A declaration on a
    non-skippable node is inert and surfaced (R3.3), so the protected gates cannot be
    touched. A forged declaration on a *skippable* node is detectable — its provenance
    claims a channel whose off-repo audit trail (the reply on the ticket, the marked
    confirmation) does not corroborate it — and bounded, because the never-skippable
    floor still gates the item. Stated honestly: within the repository the enforcement is
    *audit and floor*, not cryptography — the same trust model as the rest of the
    checked-in state.
  - *A late reply tries to excuse a node already walked.* Not recorded (R2.12).
  - *Integration outage.* Fail-closed: the gate waits, nothing is skipped.
- **Fail-closed expectations.** Every failure in this mechanism degrades to *more*
  process, never less: no reply → no phases run at all; an unparseable or empty selection
  → the full process; an invalid token → no skip; a missing `skipped` edge → compile
  failure before any traversal.
