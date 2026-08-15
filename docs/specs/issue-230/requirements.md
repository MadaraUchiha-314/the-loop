---
type: requirements
phase: requirements-definition
workItem: issue-230
status: draft                # draft | in-review | approved
approvedBy: []
collaborators: [maintainer]
overrides: {}
---

# Requirements: a readable session stream, a session tree, and a chat bar

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (<https://kiro.dev/docs/specs/>). This phase MUST be reviewed and approved by the
> required collaborators before moving to design.

## Introduction

The Control Plane's trace panel (issue-209) renders a session's own JSONL —
`~/.claude/projects/<munged cwd>/<session-id>.jsonl` — one row per line, from the
harness's perspective. [#230](https://github.com/MadaraUchiha-314/the-loop/issues/230)
reports three things wrong with that surface, and asks for two additions:

1. **The stream is unreadable.** claude.ai/code renders the same file as a
   conversation: tool calls collapsed to one line each, expandable on demand, with each
   call's result attached to it. The trace panel instead prints every line flat, with
   tool inputs as raw JSON.
2. **Many lines render blank.** The projection (`transcriptTurns` in
   `ui/src/api/model.ts`) reads only `text` and `tool_use` blocks, so a `tool_result`
   entry — the majority of lines in a working session — projects to an empty row, as do
   `thinking` blocks and harness bookkeeping entries.
3. **Sessions are reached through the wrong door.** A work item's sessions (the outer
   loop's, plus one per PR inner loop) are only visible as tabs inside one work item's
   detail page. The issue asks for a sidebar of **all** work items, each expanding to a
   two-level tree of its sessions — outer loop, then inner loops — with no tree for
   ad-hoc work items (contribute / do), which own no inner loops.
4. **There is no way to talk to a session from the stream.** A chat bar at the bottom
   must send a message into the viewed session's tmux pane — the outer loop's bar to the
   outer session, an inner loop's bar to that PR's session. The delivery mechanism
   already exists (`POST /api/v1/sessions/reply`, issue-208) but only resolves a work
   item's own record, never a PR endpoint.

## Requirements

### R1 — Every transcript line renders as something legible

**User story:** As an operator reading a session's stream, I want every line the service
serves to render as readable content, so that the trace tells me what happened rather
than showing blank rows.

- R1.1 WHEN an entry's `message.content` carries `tool_result` blocks THEN the UI SHALL
  extract the result's text (string content, or the text of nested content blocks) and
  SHALL attach it to the `tool_use` it answers, matched by `tool_use_id`.
- R1.2 WHEN a `tool_result` matches no rendered `tool_use` (the tail cut the call off)
  THEN the UI SHALL render it as its own row with the extracted text, never blank.
- R1.3 WHEN an assistant entry carries `thinking` blocks THEN the UI SHALL render the
  thinking collapsed, not as a blank row.
- R1.4 WHEN an entry is harness bookkeeping (`summary`, `system`, or any shape with no
  derivable message text) THEN the UI SHALL render a labelled, visually quiet row naming
  what it is, never a blank row.
- R1.5 WHEN a line is server-flagged `malformed` THEN the UI SHALL keep the current
  behaviour: the raw line, visibly flagged.

### R2 — Tool calls are collapsed by default, expandable on demand

**User story:** As an operator scanning a session, I want tool calls collapsed to one
summary line each — the way claude.ai/code shows them — so the conversation reads as
prose with the machinery folded away.

- R2.1 WHEN an assistant turn invokes tools THEN each call SHALL render collapsed to one
  line: the tool name plus a human-readable summary of its input (`Bash` → the command,
  `Read`/`Write`/`Edit` → the file path, `Grep`/`Glob` → the pattern, otherwise a
  compact rendering of the input).
- R2.2 WHEN the operator expands a collapsed call THEN the UI SHALL show the full input
  and the paired result text.
- R2.3 WHEN a paired result is an error (`is_error`) THEN the collapsed line SHALL say
  so visibly.
- R2.4 The default state SHALL be collapsed for tool calls, thinking and bookkeeping
  rows, and expanded for user and assistant text.

### R3 — A sessions surface: all work items in a sidebar, sessions as a tree

**User story:** As an operator, I want one screen listing every work item in a sidebar,
each opening into its sessions, so I can move between streams without going through the
dashboard.

- R3.1 The UI SHALL provide a Sessions screen with a sidebar listing every work item on
  the board.
- R3.2 WHEN a work item is selected THEN the sidebar SHALL show its sessions as a
  two-level tree: the outer-loop session, then one child per PR inner-loop session.
- R3.3 WHEN a work item runs an ad-hoc loop (`pdlc-adhoc-loop` or
  `pdlc-contribution-loop`) THEN no tree SHALL be shown — selecting the item selects its
  single session.
- R3.4 WHEN a session is selected THEN the main pane SHALL show that session's stream
  (per R1/R2), with the same fallback behaviour the trace panel has today when no
  transcript is served.
- R3.5 The selected session SHALL be addressable by URL (hash route), so a stream can be
  linked to.

### R4 — A chat bar delivers into the viewed session's tmux pane

**User story:** As an operator viewing a session's stream, I want to type a message and
have it land in that session's tmux pane, so I can steer the agent without leaving the
page.

- R4.1 The Sessions screen SHALL show a chat bar beneath the stream; sending SHALL
  deliver the text into the **viewed** session's pane — the outer session for the outer
  loop, the PR endpoint's session for an inner loop.
- R4.2 WHEN `POST /api/v1/sessions/reply` is called with a pull request's ref THEN the
  service SHALL resolve the PR endpoint the way dispatch does (own record first, then
  the record holding it as a PR endpoint; a closed PR endpoint falls back to the
  record's own session) and SHALL deliver into that endpoint's pane.
- R4.3 The reply route SHALL stay fail-closed exactly as issue-208 specified: it never
  spawns, respawns or resumes a session; no live session or pane is a refusal; a paused
  record or endpoint is a refusal.
- R4.4 WHEN the viewed session cannot receive (paused, closed, none) THEN the chat bar
  SHALL be disabled with the reason, rather than failing on send.

## Non-functional requirements

- NFR1 The projection stays a **projection, not a parser**: the harness's line format is
  not ours; any unknown shape degrades to a labelled row and never throws (the rule
  `transcriptTurns` already follows).
- NFR2 No new endpoint and no new service state: the screen is a join of what
  `/work-items`, `/sessions`, `/sessions/transcript` and `/sessions/reply` already
  serve. The one service-side change is the reply route's endpoint resolution (R4.2).
- NFR3 The demo fixture exercises every new shape (paired results, thinking,
  bookkeeping, an ad-hoc item), so the hosted page demonstrates the screen without a
  workstation.
- NFR4 Collapse/expand is plain disclosure (`<details>`), not new state machinery.

## Security considerations

Threat-model-lite, per `reference/security.md`:

- **Untrusted actors:** anyone who can reach the service's socket (loopback by default,
  CORS-gated origins otherwise — decision-059/077); transcript files written by the
  harness; registry records writable via `POST /sessions/register`.
- **Trust boundaries:** the browser ↔ service boundary is unchanged — no new routes, no
  new auth claims. The reply route's authorization posture is unchanged from issue-208:
  `actor` stays an audit-trail claim, never authentication.
- **Abuse cases:**
  - A crafted transcript line (attacker-controlled text in tool inputs/results) must
    render as text, never as markup — React's default escaping is the control; no
    `dangerouslySetInnerHTML` is introduced.
  - A crafted registry record must not widen where a reply can land: resolution reuses
    the registry's own `record_owning`/`endpoint_for` (the dispatch path), and delivery
    still refuses when the endpoint has no live pane (fail-closed, R4.3).
  - The chat bar delivers text into an agent session — prompt injection by whoever can
    reach the page. That capability is exactly issue-208's reply box (same route, same
    exposure guard); widening it to PR endpoints adds reachability to sessions the same
    operator already owned, not a new class of actor.
- **Fail-closed:** every refusal path in `reply_session` is kept; the new resolution
  only changes *which* live endpoint is addressed, never whether a dead one is revived.

## Risk tier

**3** (`autonomy.defaultTier`, human-approves-pr): a UI feature plus one narrow,
well-tested resolution change on an existing route. No schema, workflow or sensitive
path is touched; the reply route's security posture is unchanged.
