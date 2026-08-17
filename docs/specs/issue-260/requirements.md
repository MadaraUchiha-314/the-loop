---
type: requirements
phase: requirements-definition
workItem: "github:MadaraUchiha-314/the-loop#260"
status: in-review             # draft | in-review | approved
approvedBy: []
collaborators: [engineer]
overrides: {}
---

# Requirements: how many sessions a work item's pull requests get is the work item's choice

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (https://kiro.dev/docs/specs/). This phase MUST be reviewed and approved by the
> required collaborators before moving to design.

## Introduction

**The wrong actor owns the choice.** Ticket:
[#260](https://github.com/MadaraUchiha-314/the-loop/issues/260) — *"Why the fuck did we give
this option to the operator? This should be an option that's selectable at phase selection.
Do the minimal changes to make this source of truth from phase selection instead of
cli-config. The default should come from cli-config and phase selection should override
it."*

[issue-258](https://github.com/MadaraUchiha-314/the-loop/issues/258) /
[decision-092](../../decisions/decision-092.md) turned `routing.tmux.sessionPerPr` into three
named modes and gave the choice to the **operator**, machine-wide. That is the same mistake
[issue-183](https://github.com/MadaraUchiha-314/the-loop/issues/183) already refused to make
for `outer-loop-on-pull-request`, and for the same stated reason:

> not in any config file, because one repository has both a one-repo bugfix and a
> three-repo migration

One daemon serves both. A three-repo migration wants a conversation per pull request; the
doc fix in the next ticket over does not. A machine-wide switch answers for neither, so the
operator picks the lesser wrong answer and every work item that machine serves lives with
it. issue-258's own requirements list *"a per-work-item override of the choice"* as out of
scope because *"nobody has asked it"*. The person whose call it is has now asked it.

**How many sessions a work item's pull requests get is a property of the work item.** It
therefore belongs where every other per-work-item process choice already is: the
`phase-selection` gate, ticked in place, signed by the same authorized `the-loop execute`,
and frozen into the same portable record. `routing.tmux.sessionPerPr` is not removed — it
becomes what it should have been from the start: the **default** the checklist offers, and
the answer for every work item that never answered.

## Requirements

### Requirement 1 — the work item is asked, at `phase-selection`

**User story:** As an authorized human starting a work item, I want to say how many harness
conversations its pull requests get, so that a three-repo migration and a doc fix on the same
machine can differ.

#### Acceptance criteria (EARS)

1. WHEN the-loop posts the `phase-selection` checklist THEN it SHALL render one row per
   `sessionPerPr` mode (`never`, `cross-repository`, `always`), with the row matching this
   deployment's configured default pre-ticked.
2. WHEN an authorized user says the execute keyword AND exactly one mode row is ticked THEN
   the system SHALL freeze that mode as this work item's choice.
3. WHEN the selection is frozen THEN the system SHALL record the chosen mode in
   `graph-state.json` (the `phase-selection` decision and the frozen graph) and SHALL publish
   it to the work item's **portable** record, beside the frozen graph it already publishes.
4. WHEN the selection is frozen THEN the confirmation comment SHALL state the mode that was
   recorded.
5. WHERE the loop being walked reaches `phase-selection` at all (the work-item, contribution
   and ad-hoc loops) the rows SHALL be offered; the inner `pdlc-pr-loop` never reaches the
   gate and is unaffected.

### Requirement 2 — the frozen choice overrides the operator's default, for that work item only

**User story:** As an operator, I want a work item's own answer to decide its routing, so
that my config value is a default rather than a ceiling.

#### Acceptance criteria (EARS)

1. WHEN an event carrying a pull request is routed for a work item whose portable record
   carries a frozen `sessionPerPr` THEN the system SHALL route by that mode rather than by
   `routing.tmux.sessionPerPr`.
2. WHEN the work item's portable record carries no frozen `sessionPerPr` THEN the system
   SHALL route by `routing.tmux.sessionPerPr` — which is every work item started before this
   change.
3. IF a frozen value is not one of the three modes (a hand-edited record) THEN the system
   SHALL ignore it and route by `routing.tmux.sessionPerPr`.
4. WHEN one work item's mode is resolved THEN it SHALL NOT affect any other work item's
   routing.
5. WHEN the retry path asks whether a delivery was handled (`delivery_status`) THEN it SHALL
   resolve the endpoint by the same per-work-item mode routing used, so a delivery that
   succeeded is never re-forwarded as unhandled.

### Requirement 3 — nothing changes for anyone who leaves the checklist alone

**User story:** As an operator upgrading the-loop, I want the default path to behave exactly
as it does today, so that a new question is not a silent behaviour change.

#### Acceptance criteria (EARS)

1. WHEN no mode row is ticked, OR more than one is ticked, OR the checklist could not be read
   THEN the system SHALL freeze this deployment's configured default.
2. WHEN `routing.tmux.sessionPerPr` is absent, a legacy boolean, or unrecognised THEN the
   default offered by the checklist SHALL be the value
   [decision-092](../../decisions/decision-092.md) D2/D3 already resolves it to.
3. WHEN a mode row appears in a reply THEN it SHALL NOT be read as a phase — neither as a
   declared skip nor as a refusal.
4. WHEN a work item's record was written by an older the-loop THEN it SHALL be read without
   migration.

### Requirement 4 — the safety rule is untouched

**User story:** As an operator, I want the per-work-item choice to be no more dangerous than
the operator-wide one, so that moving the switch does not reopen
[#253](https://github.com/MadaraUchiha-314/the-loop/issues/253).

#### Acceptance criteria (EARS)

1. WHEN a work item selects `always` AND no checkout can be prepared for a pull request alone
   THEN the system SHALL decline the endpoint spawn and deliver into the work item's session,
   exactly as [decision-092](../../decisions/decision-092.md) D4 requires.
2. WHEN a work item selects any mode THEN the `require_branch` rule for a same-repository
   endpoint SHALL be unchanged.
3. WHEN a work item selects a mode THEN no new event name, `reason` value, or session-record
   field SHALL be introduced.

## Non-functional requirements

- **Observability.** The choice is legible in three places a human already reads: the
  confirmation comment on the ticket, `graph-state.json`, and the portable record. No new
  event stream.
- **No state migration.** The portable record gains one optional key inside the existing
  `graph` section; a record without it reads as "never answered".
- **Cost.** The default is unchanged, so the token cost of the default path is unchanged. A
  work item that selects `always` multiplies its own conversations and nobody else's — which
  is the point.

## Security considerations

> Threat-model-lite, captured with the requirements (`security.threatModel.required`).

- **Actors & trust:** the new input is a **checklist reply**, and it arrives through the
  channel that already exists for phase selection: `_authorized_comments` drops the-loop's
  own self-marked comments, then filters by `routing.authorizedUsers`, and the execute
  keyword is what signs the selection. No new trust boundary, no second authorization path.
- **Trust boundaries & data:** the parsed value is matched against a **fixed vocabulary of
  three tokens** and discarded otherwise, so no payload-derived text reaches a path, an argv,
  a prompt or a ref. The frozen value is read back through the same membership test, so a
  hand-edited portable record (agent-writable, like every state file here) cannot introduce a
  fourth mode.
- **Abuse cases (EARS):**
  1. WHEN an unauthorized user ticks the boxes THEN the selection SHALL NOT be frozen until
     an authorized user says the execute keyword, exactly as for every phase row.
  2. WHEN a reply carries a token that is not one of the three THEN the system SHALL ignore
     it and resolve to the default, and SHALL NOT report it as a skipped or refused phase.
  3. WHEN a work item selects `always` THEN authorization is unchanged: each endpoint spawn
     is still subject to `authorizedUsers`, the arming rules and `maxConcurrentDispatches`,
     so the choice widens *concurrency* and never *authorization*.
- **Fail closed:** every unreadable, ambiguous or absent answer resolves to the operator's
  configured default — never to `always`, and never to a mode the operator did not state.

## Out of scope

- **Removing or renaming `routing.tmux.sessionPerPr`.** It stays as the deployment-wide
  default. A deployment with no `routing.workspace.root` genuinely cannot serve `always`, and
  that is the operator's fact to state.
- **The inner `pdlc-pr-loop`.** It carries no `phase-selection` node; a pull request's own
  loop is the work item's decision taken once at the outer level (issue-177).
- **Changing what the modes mean.** decision-092's D1/D2/D3 vocabulary, D4's `require_branch`
  rule and D5's `strategy: clone` obligation are all unchanged; only the *owner* of the
  choice moves.
- **A CLI verb for changing the mode after freezing.** Re-answering a frozen selection is a
  general question (`the-loop graph skip` is its sibling for phases) and nobody has asked it.

## Open questions

None outstanding. The ticket states the shape in one line — *"The default should come from
cli-config and phase selection should override it"* — and this document is that sentence
expanded.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with comments.
