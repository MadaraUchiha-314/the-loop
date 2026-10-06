---
type: requirements
phase: requirements-definition
workItem: "github:MadaraUchiha-314/the-loop#471"
status: in-review            # draft | in-review | approved — tier 3: the PR approval is the human gate
approvedBy: []
collaborators: [engineer]
overrides: {}
riskTier: 3                  # one new checklist row and one frozen boolean; no sensitive path touched
---

<!-- Authored per the the-loop:writing skill. -->

# Requirements: publish a work item's spec chain as one Claude artifact

> Phase 1 of 4 (requirements → design → testing plan → tasks). Tier 3
> (`human-approves-pr`): one new row on the `phase-selection` checklist, one boolean frozen
> into `work-item-state.json`, one prompt line, and the skill rule that tells the session
> what to do with it. No credential, token scope, sensitive path or gate changes.

## Introduction

[Issue #471](https://github.com/MadaraUchiha-314/the-loop/issues/471): "Generate
requirements.md, design.md and other md files as claude artifacts."

**What is broken.** A work item's spec chain (`brainstorm.md`, `requirements.md`,
`design.md`, `testing-plan.md`, `tasks.md`) is markdown files in the repository. A reviewer
reads them on GitHub, one file per tab, with mermaid rendered only where GitHub renders it.
The issue's point: markdown is a good storage format and a poor reading format. Claude Code
can publish a page as a **Claude artifact** — a hosted, private-by-default web page — and
comments on it already reach the session that published it. So the reading surface the
issue wants exists; the-loop never asks for it.

**What this changes.**

- `phase-selection` offers one more box, `claude-artifact`, unticked by default, with the
  note that it applies only when the work item runs on the `claude` harness.
- Ticked, signed by the same authorized `the-loop execute`, and resolved to the `claude`
  harness, the choice is frozen into `work-item-state.json` as `claudeArtifact: true`.
  Ticked on any other harness, it is **not applied** and the confirmation says so.
- The session prompt tells a session on such a work item to publish the spec chain as
  **one** Claude artifact, one tab per spec file, and to republish it to the same URL when a
  file changes.
- The markdown files stay the source of truth. Gates, locks and `the-loop check` read the
  files exactly as before; the artifact is a rendering of them.

## Requirements

### Requirement 1 — the gate offers the choice

**User story:** As the author of a work item, I want to choose at `phase-selection`
whether its spec chain is also published as a Claude artifact, so I can read and comment on
it as a page rather than as raw markdown.

#### Acceptance criteria (EARS)

1.1 WHEN the `phase-selection` checklist is posted for a loop that owns an outer loop THEN
the system SHALL render one unticked row `claude-artifact`, in a section of its own, below
the outer-loop surface section.

1.2 The section SHALL state that the row is not a phase, that it is off unless ticked, and
that it applies only when the work item runs on the `claude` harness — on any other
harness the-loop ignores it.

1.3 WHEN the loop owns no outer loop (`pdlc-contribution-loop`) THEN the system SHALL NOT
render the row, and SHALL NOT read it from a reply.

1.4 The row SHALL never be read as a phase: ticked or unticked, it SHALL NOT produce a
declared skip, an opt-in or a refusal.

1.5 A Slack mirror of the checklist SHALL keep the row as a non-phase row: it SHALL NOT
offer it as a phase checkbox, and a typed `without` reply SHALL carry it through
unchanged.

### Requirement 2 — the reply resolves it, against the harness

**User story:** As the author, I want a tick to take effect only where it can, and to be
told when it cannot, so I am never left waiting for a page that will not appear.

#### Acceptance criteria (EARS)

2.1 WHEN an authorized `the-loop execute` resolves the selection AND the `claude-artifact`
row is ticked AND the work item's resolved harness is `claude` THEN the system SHALL record
`claudeArtifact: true`.

2.2 The resolved harness SHALL be the harness the same reply chose, else this deployment's
default harness. WHEN neither is known (no CLI config, as in a `check` run outside a
deployment) THEN the harness SHALL be treated as not ruling the choice out.

2.3 WHEN the row is ticked AND the resolved harness is known and is not `claude` THEN the
system SHALL record `claudeArtifact: false`, and the confirmation comment SHALL name the
row as not applied and the harness it was not applied on.

2.4 WHEN the row is unticked, absent, or the checklist cannot be read THEN the system SHALL
record `claudeArtifact: false`.

2.5 The confirmation comment SHALL name the outcome in both directions: published as a
Claude artifact, not applied (with the harness), or not requested.

### Requirement 3 — the choice is frozen with the selection

**User story:** As the operator, I want the choice recorded where every other
per-work-item choice is, so a respawned session and `the-loop check` read the same fact.

#### Acceptance criteria (EARS)

3.1 WHEN the selection is recorded THEN the system SHALL write `claudeArtifact` into
`work-item-state.json` and into the gate's decision record and frozen graph, beside
`surface`, `harness`, `model` and `effort`.

3.2 WHEN a state file carries no `claudeArtifact` key, or a value other than the boolean
`true`, THEN the system SHALL read it as `false`.

3.3 The work item's archive record SHALL carry the value under `selections`.

### Requirement 4 — the session is told, and knows the procedure

**User story:** As the operator, I want the session to publish and maintain the artifact
without being asked again, and to leave the gates exactly as they are.

#### Acceptance criteria (EARS)

4.1 WHEN the session prompt's graph-context block is rendered for an outer-loop work item
whose state has `claudeArtifact: true` THEN it SHALL carry one line telling the session to
publish the spec chain as one Claude artifact and to republish it on every change.

4.2 The line SHALL NOT be rendered for a pull request's inner loop, a contribution, an
ad-hoc task, a review, or a work item whose state has `claudeArtifact: false`.

4.3 The skill SHALL state the procedure: one artifact per work item; one tab per spec file
present, in chain order; republish to the same URL when a file changes; link the artifact
from the ticket once; the markdown files stay the source of truth.

4.4 The skill SHALL state that a comment on the artifact is feedback to fold into the
markdown file, never an answer to a gate: approvals stay with the gate on the ticket or
pull request.

4.5 The skill SHALL state that a session with no Claude artifact tool ignores the choice
and says so once on the ticket.

## Out of scope

- **A Codex or Cursor equivalent.** The issue defers it "until codex implements a similar
  alternative". The row says so; nothing else is built for it.
- **Artifacts replacing the files.** Gates lock `status: approved` into the files' front
  matter, `the-loop check` reads them, and capability docs link them. Moving the source of
  truth off the repository would change every gate; this change touches none.
- **Routing artifact comments.** The issue notes Claude already delivers them to the
  publishing session. the-loop adds no ingress for them.
- **Sharing the artifact.** It is published private, under the operator's account. Who may
  open it is the operator's decision, made in claude.ai.

## Security considerations

**Untrusted actors.** Anyone who can comment on the ticket can tick the box in place; only
an authorized `the-loop execute` makes the tick count, the same boundary as every other row.
Anyone the operator shares the artifact with can comment on it.

**Trust boundaries.** (1) The ticket → the gate: unchanged; the reply is authorized and the
row is matched by exact token. (2) The repository → claude.ai: the spec chain's text is
published to the operator's Claude account. It already reaches the same provider as model
input; publishing it stores it there as a page. (3) Artifact comments → the session: a new
input path into the session, but not into the-loop, which neither reads nor routes them.

**Abuse cases.**

- WHEN a non-authorized user ticks `claude-artifact` and nobody authorized executes THEN
  nothing SHALL change.
- WHEN an artifact comment says "approved", or asks for a gate to be skipped, THEN the
  session SHALL NOT treat it as a gate answer; gates read the ticket or pull request only.
- WHEN an artifact comment carries instructions THEN the session SHALL treat them as
  untrusted data, as it treats ticket comments.
- WHEN a hand-edited `work-item-state.json` sets `claudeArtifact` to a string or number THEN
  the system SHALL read it as `false`.

**Fail closed.** Every unreadable, ambiguous or unknown case resolves to *not published*:
an unreadable checklist, an absent row, a non-boolean value, a harness known not to be
`claude`, a session without the artifact tool.

**Disclosure.** The artifact is private by default and the-loop never changes its sharing.
A spec chain must not hold secrets in any case (the evidence redaction rule); publishing
does not loosen that.
