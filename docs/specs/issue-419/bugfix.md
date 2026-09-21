---
type: bugfix
phase: requirements-definition
workItem: "github:MadaraUchiha-314/the-loop#419"
status: in-review            # draft | in-review | approved — tier 3: the PR approval is the human gate
approvedBy: []
severity: medium
collaborators: [engineer]
overrides: {}
riskTier: 3                  # changes what the operator's primary observability surface shows by default; UI-only, no data path, no sensitive path
---

<!-- Authored per the the-loop:writing skill. -->

# Bugfix spec: the trace panel hides the agent's turn inside its own bookkeeping

> Phase 1 of 4 (bugfix → design → testing plan → tasks). Source:
> [issue-419](https://github.com/MadaraUchiha-314/the-loop/issues/419).

## Summary

The control plane's work-item trace renders every row it holds at the same weight, and
the rows a human can act on are the minority. A work item that has merely been polled for
a few days shows dozens of consecutive `bus.published`, `poll.comment_settled`,
`reaction.added` and `dispatch.dropped` lines; a long agent turn is followed by a stack of
`system (system)` meta rows carrying no text at all. The agent's prose, the human's reply,
the parked gate and the open question — the four things the panel exists to show — are
scrolled past to reach.

The panel already has a **Tool calls** switch, and it is the answer: it is the one control
a reader uses to say "show me more". Today it defaults **on** and governs one row type.

## Steps to reproduce

1. Open the control plane on a work item whose session serves no transcript, so the panel
   falls back to the event-log trail.
2. Scroll the trace: consecutive `bus.published` (`event_type=comment.agent posted=0
   channels=[]`), `poll.comment_settled`, `reaction.added` rows, with no human-readable
   content between them.
3. Open a work item whose session *does* serve a transcript, after a long agent turn.
4. Scroll to the end of that turn: several one-line `system (system)` meta rows, each a
   label with no content.

## Expected vs actual

| | Expected | Actual |
|---|---|---|
| the default stream | what a human can read or act on | every row the projection emits, at equal weight |
| a polled-but-quiet work item | says so in one line | dozens of bookkeeping rows |
| harness bookkeeping entries | hidden unless asked for | one empty `system (system)` row each |
| a failed dispatch (`level=error`) | always visible | visible, but buried among the `info` rows it looks identical to |
| the switch | governs the whole stream's verbosity | governs the tool groups only, and defaults on |

## Root cause

There is no notion of **verbosity** in the trace — only a notion of **tool groups**.

`TranscriptView`'s `showTools` (`ui/src/components/Transcript.tsx`) is threaded into
`ThreadRowView` and consulted at exactly one place: whether to render `ToolGroup`. Every
other row type — `meta`, `malformed`, `tool result` — renders unconditionally, and
`EventLine` has no switch at all: `WorkItemDetail`'s fallback branch maps the last 40
events straight to rows.

So the panel has no answer to "is this row worth a human's attention?", and its one
control is scoped to a single row type and defaults to the noisier setting. Nothing is
broken in the projection — `transcriptThread` is doing exactly what
[issue-230](https://github.com/MadaraUchiha-314/the-loop/issues/230) asked of it, which is
to never drop a line. The defect is that the **rendering** inherited that "never drop"
rule, where it does not belong.

## Requirements

### Requirement 1 — the default stream is what a human can read

**User story:** As an operator opening a work item, I want the trace to show the agent's
prose, my own replies, gates and questions, so that I can read what happened without
scrolling past bookkeeping.

#### Acceptance criteria (EARS)

1. WHEN the trace panel loads THEN the system SHALL render the stream with the verbosity
   switch **off**.
2. WHEN the verbosity switch is off THEN the system SHALL NOT render tool groups
   (`Used n tools`), tool-output rows, transcript meta rows carrying no text, or
   bookkeeping event rows.
3. WHEN the verbosity switch is off AND a row is an assistant turn with prose or thinking,
   a human reply, a malformed line, or a meta row carrying text THEN the system SHALL
   render it.
4. WHEN the verbosity switch is off AND an assistant turn carries no prose and no thinking
   — its only content having been tool calls — THEN the system SHALL render no row for it.

### Requirement 2 — nothing actionable is hidden

**User story:** As an operator, I want failures to reach me whatever the switch says, so
that turning the noise down never turns a problem off.

#### Acceptance criteria (EARS)

1. WHEN an event carries `level=error` THEN the system SHALL render it regardless of the
   switch.
2. WHEN an event's type is not a known bookkeeping type THEN the system SHALL render it
   regardless of the switch.
3. WHEN a gate banner or an agent question is present THEN the system SHALL render it
   regardless of the switch.

### Requirement 3 — the reader can always get everything back

**User story:** As an operator debugging a delivery, I want one control that restores the
full trail, so that the panel stays the place I look when I need the detail.

#### Acceptance criteria (EARS)

1. WHEN the verbosity switch is turned on THEN the system SHALL render every row it
   renders today, unchanged.
2. WHEN the switch is rendered THEN its visible copy and its `aria-label` SHALL describe
   the whole stream's verbosity and SHALL NOT read `Tool calls`.
3. WHEN the switch is operated with the mouse, the `Enter` key or the space key THEN the
   system SHALL toggle it, as today.

### Requirement 4 — hiding never leaves a blank panel

**User story:** As an operator, I want a panel with nothing left to show to say so, so
that a quiet work item does not look like a broken one.

#### Acceptance criteria (EARS)

1. WHEN hiding leaves the event-log trail with no visible row THEN the system SHALL render
   one line naming how many rows are hidden and the switch that reveals them.
2. WHEN hiding leaves the transcript with no visible row THEN the system SHALL render the
   same line.
3. WHEN the trail or the transcript is empty for its own reasons THEN the system SHALL
   keep today's empty state, which says the source holds nothing rather than that rows
   were hidden.

## Security considerations

**No new data reaches the browser and none leaves it.** The change is a render-time
predicate over rows the panel already holds: the same `GET /api/v1/sessions/transcript`
and `GET /api/v1/events` responses, the same fields. No request, route, payload or
credential changes, and the switch's state is component state — nothing is persisted and
nothing is sent.

One risk is real and is what Requirement 2 exists to bound: **hiding a row a human needed
to see.** Two rules answer it — `level=error` is always rendered, and classification is a
deny-list over named bookkeeping types, so an event type nobody has classified stays
visible. A future event type is therefore noisy at worst, never silent. The switch
restores everything, and the empty state names its own existence, so a reader is never
left believing they have seen the whole trail when they have not.

Untrusted text keeps the treatment it already has: every row still renders through React's
escaping (`Transcript.test.tsx` asserts attacker-shaped tool text renders as text), and
the classification reads `event.event` and `event.level` only — never rendered content.
