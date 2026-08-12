# Decision 078: Agent questions travel through a verb; the loop-prevention marker is stamped centrally

- **Status:** proposed
- **Date:** 2026-08-12
- **Deciders:** @MadaraUchiha-314 (owner), the-loop (engineer)
- **Work item:** [issue-208](https://github.com/MadaraUchiha-314/the-loop/issues/208)

## Context

The `work-item` interaction mode (issue-134, decision-051) tells a spawned agent to ask
its questions as comments on the ticket — and, until now, to post them itself with `gh`.
Two structural problems followed:

1. **The loop-prevention marker was a per-agent memory test.** Every agent, on every
   question, had to remember to append `<!-- the-loop:agent-comment -->` — the string
   both trigger paths use to drop the-loop's own comments before they re-enter the loop
   (issue-64/104). One lapse and the agent's own question resumes its own session.
2. **The wait was invisible.** A `gh` call leaves no trace in the-loop, so the control
   plane could only *infer* that a session was waiting, and the dashboard's reply card
   (shipped built-and-disabled by issue-207) had neither an event to key on nor a route
   to answer through.

## Decision

**`the-loop ask` is how an agent asks; `POST /api/v1/sessions/reply` is how an operator
answers into the session.** The verb stamps the marker centrally
(`authz.mark_self_authored`, idempotent) and emits `session.awaiting_input`; the route
bracketed-pastes into the pane, emits `session.reply_sent`, and records a **marked**
delivery report on the ticket. The ticket's own scope note holds: the central stamping
is the substantive behavioural change, not the transport.

Four subsidiary calls, each the narrow option:

1. **`ask` executes in-process** — the same exception class as `sessions attach`/`reset`,
   breaking the "core capabilities route through the service" default (PR #162)
   deliberately. It is the escalation path: the one verb that must work when no service
   is running, or in a cloud session with no daemon at all. It stays in
   `core/sessions.py`, so a route/MCP tool later is a binding, not a port. No
   `POST /sessions/ask` and no MCP tools ship now — the ticket scopes the reply route as
   the only new API surface, and no other consumer exists.
2. **The reply route is fail-closed and spawns nothing.** No session or no live pane is
   404 (the dispatcher's respawn machinery is not invoked — a reply answers an agent,
   never manufactures one); paused is 400 (pause means "deliver nothing", this route
   included). The claimed `actor` is recorded on the event and the ticket for audit,
   never trusted as auth — requiring a login here would be theatre while the service
   deliberately carries no in-app auth (decision-059); the boundary remains the
   exposure guard, the gateway, and the CORS exact-origin allowlist, and the plane
   already carries strictly higher privilege (`sessions/control` spawns and kills).
3. **The delivery report is marked, and the wait's event is emitted even when `gh`
   fails.** Marked, because an unmarked copy of the answer on the ticket would be
   poller-forwarded into the very session the route just pasted it into — delivered
   twice. Emitted-on-failure, because the agent is waiting whether or not GitHub was
   reachable, and the reply route is then the only way to answer it.
4. **An answer given on the ticket does not close the wait.** The poller forwards it as
   ever, but emits no `session.reply_sent`: it cannot know which forwarded comment
   answered the question, and guessing would silently clear real waits. The
   `awaiting-input` attention row staying lit after a ticket answer is the accepted,
   documented cost.

## Cost

- A stale `awaiting-input` row whenever the answer arrives via the ticket (point 4) —
  cleared by the next control-plane reply, or ignored.
- One more comment on the ticket per control-plane reply (the delivery report) — the
  price of the thread staying the full record, and skippable per call
  (`comment: false`).
- The `work-item` directive grew by a command the agent must have on PATH; the manual
  `gh` + marker path remains as the stated fallback.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Keep agents posting with `gh`, add only the reply route | Leaves the marker a per-agent memory test — the substantive problem — and leaves the wait unobservable |
| An `ask` API route + MCP tool now | Out of the ticket's scope ("the reply route is the only new API surface"); couples the escalation path to a running service; no consumer exists |
| Require an actor login on the reply route | Authentication theatre: the service has no auth layer for it to bind to (decision-059), and the same caller can already spawn/kill sessions unauthenticated on that plane |
| Poller emits `reply_sent` when it forwards a comment to a waiting session | Guessing — any forwarded comment would clear the wait, answered or not |
| A config switch to disable the reply route | Implies a privilege boundary `sessions/control` does not have; the origin/exposure posture already governs both |
