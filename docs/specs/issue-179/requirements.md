---
type: requirements
phase: requirements-definition
workItem: issue-179
status: approved              # draft | in-review | approved
approvedBy: []                # recorded on the PR review (paper trail)
riskTier: 5
collaborators: [product-manager, architect, engineer, approver]
overrides:
  autonomy: >-
    Tier 5 by change (the skip vocabulary is a security boundary), worked
    autonomously to a PR at the owner's explicit direction on this ticket; the
    human gate is the PR review.
---

# Requirements: every phase is selectable — the human is the floor

> Phase 1 of 4 (requirements → design → testing plan → tasks). Ticket:
> [issue #179](https://github.com/MadaraUchiha-314/the-loop/issues/179).

## Introduction

[Issue #177](https://github.com/MadaraUchiha-314/the-loop/issues/177) made *part* of the
loop selectable: at the `phase-selection` gate an authorized human unticks phases, and the
work item routes around them. The vocabulary it shipped was deliberately narrow — the spec
chain only — because [decision-067](../../decisions/decision-067.md) D2 held that a fixed
floor (`test-planning`, `implementation`, `verification`, the review chain,
`security-review`, `human-approval`) was what bounded the damage of any illegitimate
declaration.

The ticket opens on the first crack in that floor: *"For documentation related changes,
there's no testing plan that's required. Make that phase also optional and hence
selectable from the phase selection step."* A doc fix that unticks its whole spec chain
still has to author a locked `testing-plan.md` whose every matrix row says `n/a`.

The owner's direction on this ticket goes further and settles the general case:
**every phase is selectable and skippable.** Not the spec chain plus one; everything the
loop walks. That is a deliberate reversal of decision-067 D2 *and* of the `required: true`
markers decision-063 put on `security-review` and `human-approval` — and it relocates the
floor rather than removing it:

- **The structural floor becomes a declared one.** Nothing is protected by the graph
  refusing to skip it. What protects the process is that a *named, authorized human* must
  choose each omission, before any work starts, on the ticket, and that every omission is
  recorded with provenance and travels with the work item.
- **What does not move:** `phase-selection` itself. The gate that asks the question is
  the one node no declaration can reach — it is `required: true` and unskippable, so a
  work item can never walk past the act of choosing. That single invariant is what keeps
  "everything is selectable" from meaning "the harness decided".
- **What is still refused:** the harness declaring anything, an unauthorized commenter
  declaring anything, a declaration reaching a node the pointer has already passed, and a
  declaration inventing a node the graph does not have.

A second requirement travels with the first, and it is what keeps a *kept* phase
meaningful. `verification` gates `testing-plan.md`. Once the plan is selectable, a work
item can keep verification and skip its plan — and under issue-177's planned-absence rule
the gate would then assert nothing at all: a node reporting success without running, the
issue-124/167 failure this repository has now fixed twice. So a gate whose subject was
declared away must **move its subject**, not lose it.

## Requirements

### Requirement 1 — the vocabulary is every phase but the gate itself

**User story:** As the authorized user starting a work item, I want to select any phase of
the loop, so that the process fits the change instead of the change fitting the process.

#### Acceptance criteria

1. WHEN the shipped outer loop (`pdlc-work-item-loop`) is compiled THEN every node SHALL
   be `skippable: true` **except** `phase-selection` and the terminal nodes (`complete`,
   `escalated`) — specifically including `test-planning`, `implementation`,
   `verification`, `self-review`, `critic-review`, `security-review`, `evidence`,
   `capability-docs`, `reviewer-briefing` and `human-approval`.
2. WHEN `phase-selection` is compiled THEN it SHALL remain `required: true` and SHALL NOT
   be skippable — no declaration, from any channel, may route around the act of
   selecting.
3. WHEN `security-review` and `human-approval` are compiled in the **outer** loop THEN
   they SHALL no longer carry `required: true` (a node cannot be both required and
   skippable), and the graph SHALL say in place why the marker was traded.
4. WHEN any newly skippable node is compiled THEN it SHALL declare its own `on: skipped`
   edge to its ordinary forward successor — routing is authored, never inferred, so a
   missing edge is a compile failure before any traversal.
5. WHEN the shipped skip sets are expanded THEN `spec-chain` SHALL name
   `brainstorming`, `requirements-definition`, `requirements-approval`, `design`,
   `test-planning`, `design-approval`, `tasks-breakdown` (the chain the project's own
   vocabulary describes: *requirements → design → testing-plan → tasks*), and a new
   `review-chain` set SHALL name `self-review`, `critic-review`, `security-review`,
   `evidence`, `capability-docs`, `reviewer-briefing` — the six nodes that were one
   `needs-review` label.
6. WHEN the **inner** `pdlc-pr-loop` is compiled THEN it SHALL be unchanged: no skippable
   node, no `phase-selection`, and `security-review` still `required: true`. Declared
   skips remain outer-loop only (issue-177 R4.1).
7. WHEN the `phase-selection` checklist is posted THEN it SHALL list every selectable
   phase pre-ticked, and WHEN no phase of the loop is protected THEN the checklist SHALL
   say so plainly — naming that every phase is the user's to decide and that each
   omission is recorded against their name — rather than printing an empty "always runs"
   block.
8. WHEN a phase is declared skipped — from the selection gate or the audited
   `the-loop graph skip` verb — THEN it SHALL route along its `on: skipped` edge without
   running any hook, SHALL record outcome `skipped`, and SHALL be reported by
   `the-loop check` as *skipped by declaration* with provenance — never as a pass. This
   is issue-177's behaviour, unchanged, now reaching every node.

### Requirement 2 — a kept gate keeps a subject

**User story:** As a reviewer, I want a work item that skipped its testing plan but kept
verification to still show me what was verified, so that a kept phase is never a phase
that silently asserts nothing.

#### Acceptance criteria

1. WHEN `verification` is reached and `test-planning` was **not** declared skipped THEN
   its gate SHALL be exactly what it is today — `testing-plan.md` present, checkmarks
   complete, `Verification results` non-empty — and SHALL require no new section
   anywhere.
2. WHEN `verification` is reached, `test-planning` was declared skipped, and no
   `testing-plan.md` exists THEN `verification` SHALL instead gate the shared
   `execution-log.md` for a non-empty `Verification results` section, and SHALL block
   until it is written.
3. WHEN `test-planning` was declared skipped but a `testing-plan.md` exists anyway THEN
   that artifact SHALL be gated normally and the execution-log fallback SHALL NOT apply —
   a declaration tolerates only an *absence*, and the proof is never demanded twice.
4. WHEN `verification` itself is declared skipped THEN neither gate SHALL run — the node
   is not walked at all, and the omission is on the record like every other.
5. WHEN the bundled `templates/execution-log.md` is authored THEN it SHALL offer a
   `Verification results` section, so a work item created from the template never blocks
   on a heading it was never given (the issue-167 shape, pinned by the P5c parity test).

### Requirement 3 — a conditional gate is declared, and can only narrow

**User story:** As the maintainer of the process graph, I want the fallback expressed in
the graph and bounded by the same vocabulary as everything else, so that no hook decides
for itself when a gate applies.

#### Acceptance criteria

1. WHEN a `validate-artifacts` entry declares `onlyWhenSkipped: <artifact>` THEN the
   entry SHALL apply only while **every** named artifact is a planned absence — its
   authoring node declared-skipped **and** no accepted name present on disk — and SHALL
   report `skipped` with a reason otherwise.
2. WHEN a hook entry omits `onlyWhenSkipped` THEN its behaviour SHALL be exactly what it
   is today: the parameter is additive, and every existing node, graph and consuming
   repository is unaffected.
3. WHEN `onlyWhenSkipped` names an artifact that no declared-skipped node authors THEN
   the entry SHALL never apply — the parameter reads only the runtime's filtered
   `skipped_artifacts`, so it can narrow a gate's applicability and never widen what may
   be skipped.

### Requirement 4 — the reversal is on the record, and the residual is stated

**User story:** As someone reading why the floor moved, I want the decisions that built it
and the decision that dismantled it to point at each other, so the change reads as a
revision rather than a contradiction.

#### Acceptance criteria

1. WHEN this work item ships THEN a new decision SHALL record the revision of
   decision-067 D2 and of the `required: true` markers from decision-063, SHALL name the
   one invariant that remains (`phase-selection`), and SHALL state plainly what a work
   item can now legitimately omit — up to and including the security review and the human
   approval gate.
2. WHEN decision-063 and decision-067 are read THEN each SHALL carry a pointer to the
   revising decision at the affected point, so nobody follows a superseded rule from an
   older document.
3. WHEN the operating-model surfaces are read (`SKILL.md`, `reference/workflow.md`,
   `reference/security.md`, `docs/capabilities/process-graph.md`,
   `docs/cli/commands/graph.md`) THEN each SHALL describe the widened vocabulary, the
   `phase-selection` invariant and the execution-log fallback — none SHALL still claim a
   structural floor of never-skippable phases.
4. WHEN the agent-facing rules are read THEN they SHALL still forbid the harness from
   declaring or proposing a skip by answering the gate — the widened vocabulary makes
   that rule more load-bearing, not less.

## Security considerations

> Threat-model-lite (`security.threatModel.required`). This work item **dismantles a
> security boundary and rebuilds it in one place.** It is the highest-risk change the
> declared-skips mechanism has taken, and the honest framing is that the *graph* no longer
> guarantees any phase runs; a *human* does.

- **Untrusted actors.** Unchanged from issue-177: (a) the agent/harness working the item —
  it writes `graph-state.json`, spec files and (with the operator's credentials) ticket
  comments, and the whole design assumes it will try to skip conveniently; (b) anyone who
  can comment on the ticket but is not in `routing.authorizedUsers`; (c) a hand-edited or
  corrupted state file.
- **Trust boundaries — two of three unchanged, one deliberately widened.**
  1. *Who may declare* — `routing.authorizedUsers`, checked by the shared
     `_authorized_comments` reader, which drops the-loop's own self-marked comments so the
     gate can never answer itself. **Unchanged, and now carrying the whole weight.**
  2. *What may be declared* — still the compiled graph's `skippable` set, still shipped as
     CLI package data a repository cannot override, still re-filtered on every read. What
     changes is its contents: every phase but `phase-selection`. A repository, a session
     or a hook still cannot widen it, and `phase-selection` still cannot be declared away.
  3. *When* — only nodes still ahead of the pointer. **Unchanged.**
- **What the widening costs, stated plainly.** An authorized human may now declare a work
  item that skips its security review and its human approval and walks straight to
  `complete`. Nothing in the graph prevents it. What remains is: the selection is a human
  act by a named actor; it happens **before** any phase runs; it is recorded with
  provenance in `graph-state.json` and frozen into the portable work-item record; it is
  posted as a confirmation comment on the ticket; and `the-loop check` reports every
  omission as *skipped by declaration — by whom* forever after. The mechanism's guarantee
  moves from *"these phases always ran"* to *"every phase that did not run is attributable
  to a person"*.
- **Abuse cases.**
  - *The agent posts `the-loop execute` to skip its own review.* Refused: its comments
    carry the self-authored marker and are dropped before authorization is considered, and
    it is not in `authorizedUsers`. The skill states the prohibition explicitly, and R4.4
    keeps it stated as the vocabulary widens.
  - *An unauthorized commenter selects phases away.* Ignored; the gate keeps waiting.
  - *The harness routes past the selection gate itself.* Structurally refused (R1.2):
    `phase-selection` is required and unskippable, so the loop cannot begin without a
    human's answer. This is the invariant everything else now rests on.
  - *A late declaration excuses a node already walked.* Not recorded (issue-177 R2.12),
    unchanged — a skip is a plan, not an amnesty.
  - *The agent hand-writes skips into `graph-state.json`.* Previously bounded by the
    protected floor; now bounded only by detectability. A forged declaration claims a
    channel (`selection` / `cli`) whose off-repo trail — the authorized reply, the marked
    confirmation comment, the `graph.skips_declared` event — does not corroborate it, and
    the frozen graph recorded at selection time is the contemporaneous record to compare
    against. Stated honestly: within the repository the enforcement is now *audit alone*,
    not audit-plus-floor. This is the residual the owner accepted in widening the
    vocabulary, and it is why R4.1 requires the decision record to say so.
  - *A kept gate is hollowed out by skipping what it reads.* Answered by R2.2 for the one
    case that exists in the shipped graph (`verification` over `testing-plan.md`), and by
    R3.1/R3.3 structurally: the conditional parameter can only ever narrow.
  - *Integration outage at the gate.* Fail-closed, unchanged: the gate waits, nothing is
    skipped, no phase runs.
- **Fail-closed expectations.** Every failure still degrades to *more* process: no
  authorized reply → nothing runs at all; an unparseable or empty selection → the full
  process; an invalid token → no skip; a missing `on: skipped` edge → compile failure; a
  kept `verification` whose plan was declared away → blocked until the results are
  written down.
