---
type: requirements
phase: requirements-definition
workItem: issue-208
status: draft
approvedBy: []
collaborators: [engineer, approver]
riskTier: 3
overrides: {}
---

# Requirements: `the-loop ask` + `POST /api/v1/sessions/reply`

> Phase 1 of the chain. Ticket:
> [#208](https://github.com/MadaraUchiha-314/the-loop/issues/208).

## Introduction

**A waiting agent is invisible, and there is no way to answer it except on GitHub.**
When a spawned session needs a human — a clarification, a decision — the interaction
directive (`cli/the_loop/interaction.py`, issue-134) tells it to post the question as a
comment on the work item and wait. The agent does the posting itself, with the
operator's own `gh`, and is *trusted to remember* the loop-prevention marker every
single time; a forgotten marker turns its own question into an event that resumes its
own session (issue-104's bug, reintroducible by any one agent on any one question). And
because the post is just a `gh` call, nothing in the-loop knows the session is now
waiting: the control plane can infer it at best, and the dashboard's reply card —
shipped built-and-disabled by [issue-207](https://github.com/MadaraUchiha-314/the-loop/issues/207)
— has neither an event to key on nor a route to answer through.

```mermaid
sequenceDiagram
    participant A as agent (tmux session)
    participant GH as GitHub
    participant EL as event log
    participant UI as dashboard
    participant O as operator
    Note over A,UI: today
    A->>GH: gh api …/comments (marker: remembered? each time?)
    Note over EL: nothing — the wait is invisible
    UI--xO: no card; the wait is inferred or missed
    O->>GH: answer on the ticket
    GH->>A: poller forwards the comment (next cycle)
```

This work item routes the question through a verb and the answer through a route:

1. **`the-loop ask`** — the agent calls the verb instead of `gh`. The loop-prevention
   marker is stamped **centrally** (the substantive behavioural change, per the ticket's
   scope note — not the transport), and the wait becomes a first-class
   `session.awaiting_input` event.
2. **`POST /api/v1/sessions/reply`** — delivers an operator's answer straight into the
   waiting session's tmux pane, emitting `session.reply_sent`.

The wait is then *observable* (`attention` reports it; the dashboard's card lights up
from the event) and *answerable* (the card's reply box gains the route it was shipped
disabled for).

## Requirements

### Requirement 1 — the agent asks through a verb, and the marker is stamped centrally

**User story:** As a spawned agent needing a human answer, I want one verb that posts my
question correctly, so that I cannot resume my own session by forgetting the marker and
so the system knows I am waiting.

**Acceptance criteria (EARS):**

- **1.1** WHEN `the-loop ask` is invoked with a valid work-item ref and a non-empty
  question THEN the system SHALL post the question as a comment on that work item
  (issues endpoint — PR conversations included) through the operator's `gh` CLI, with
  the visible attribution line and the loop-prevention marker
  (`authz.mark_self_authored`) appended centrally by the verb.
- **1.2** WHEN the comment is posted THEN the system SHALL emit a
  `session.awaiting_input` event carrying the work item ref, the question text, the
  invoking actor and the posted comment's URL.
- **1.3** WHEN posting the comment fails THEN the system SHALL still emit
  `session.awaiting_input` (with `comment_posted: false`), report the failure on stderr
  and exit non-zero — the wait is real even when GitHub was unreachable, and the control
  plane is then the only surface that can carry the answer.
- **1.4** WHEN the question is empty/whitespace or the work-item ref is malformed THEN
  the system SHALL exit 2 with an error, posting nothing and emitting nothing.
- **1.5** The verb SHALL execute in-process, not through the control-plane service: the
  escalation path is the one path that must keep working when nothing else of the-loop
  is running (same exception class as `sessions attach`/`reset`).

### Requirement 2 — the operator replies through the control plane

**User story:** As an operator looking at the dashboard's "agent is waiting" card, I
want to type an answer and have it reach the session directly, so that answering does
not require a round-trip through GitHub and a poll cycle.

**Acceptance criteria (EARS):**

- **2.1** WHEN `POST /api/v1/sessions/reply` names a work item with an active session
  whose tmux pane is live THEN the system SHALL paste the reply text — prefixed with a
  short provenance header naming the control plane and the given actor — into the pane
  as one bracketed-paste message and submit it.
- **2.2** WHEN the reply is delivered THEN the system SHALL emit a `session.reply_sent`
  event carrying the work item ref and the actor.
- **2.3** WHEN the named work item has no registered session, or its session's tmux pane
  is gone or was never created, THEN the system SHALL respond 404 with guidance and
  SHALL NOT spawn or respawn anything — a reply must never *start* an agent.
- **2.4** WHEN the named session is paused THEN the system SHALL respond 400 telling the
  caller to resume it first — pause means "nothing is delivered", and the reply route is
  not an exception to it.
- **2.5** WHEN the reply text is empty/whitespace or the ref malformed THEN the system
  SHALL respond 400.
- **2.6** WHEN the reply is delivered THEN the system SHALL post (best-effort, on by
  default, `comment: false` to skip) a marked comment on the work item reporting the
  delivery and quoting the reply — the ticket stays the paper trail, and the marker
  keeps the poller from delivering the same answer a second time.
- **2.7** The route SHALL be added to the authored OpenAPI contract
  (`docs/api-specs/openapi/the-loop.v1.yaml`), and the contract-parity test SHALL hold.

### Requirement 3 — the wait is observable

**User story:** As an operator (or the dashboard), I want waiting sessions surfaced
without inference, so that a question does not sit unanswered because nobody scrolled
the right ticket.

**Acceptance criteria (EARS):**

- **3.1** WHEN a work item's most recent `session.awaiting_input` event is newer than
  its most recent `session.reply_sent` event THEN `GET /api/v1/attention` SHALL list the
  work item with kind `awaiting-input` and the question as detail — the same
  open/answered rule the dashboard's `awaitingInput` model already implements, so the
  two surfaces cannot disagree.
- **3.2** Both event types SHALL be registered in `eventlog.EVENT_TYPES` (and the
  observability reference that mirrors it), so `the-loop events --types` documents them.

### Requirement 4 — the loop directs agents through the verb

**User story:** As the operator of the loop, I want spawned agents *told* to use the
verb, so the central stamping actually happens in practice.

**Acceptance criteria (EARS):**

- **4.1** The `work-item` interaction directive (`interaction.py`) SHALL name
  `the-loop ask` as the way to ask, retaining manual `gh` + marker only as the explicit
  fallback for when the CLI is unavailable.
- **4.2** The skill's collaboration reference (§ where questions go / loop prevention)
  SHALL be updated in the same PR.

### Requirement 5 — the reply card stops being disabled (scope call, see execution log)

The ticket says "no UI work is required by this issue": the question card does light up
from the event alone. But the reply box beneath it is hard-disabled with copy stating
*"the service has no reply route yet"* — copy this work item makes false. Leaving a
control that lies about the product contradicts the very reason it was shipped disabled
("a control that claims the product can do something it cannot would be a lie",
issue-207). The minimal honest change:

- **5.1** WHEN the reply box is submitted THEN the dashboard SHALL `POST
  /api/v1/sessions/reply` for the work item, report the outcome, and refresh; the demo
  transport simulates the delivery (emitting `session.reply_sent` in-memory), the same
  convention its control verbs already follow.
- **5.2** The "route does not exist" copy SHALL be removed from the card, the module
  docstrings and `ui/README.md`.

## Non-functional requirements

- **NFR1 — no new dependency.** `gh`, tmux bracketed paste and the event log are all
  existing machinery.
- **NFR2 — no new configuration.** No schema key is added or changed; the verb and the
  route ride the existing `routing.control` gh binary and the existing service posture.
- **NFR3 — the security posture is unchanged in kind.** No in-app auth is added
  (decision-059); the reply route is loopback-by-default behind the same exposure guard
  and CORS allowlist as `POST /sessions/control`, which already carries strictly higher
  privilege (it spawns and kills sessions).

## Security considerations

Threat-model-lite. The untrusted actors: anyone who can reach the service's socket
(loopback processes by default; whatever the operator exposes otherwise), any page on a
CORS-allowed origin, and anyone who can comment on the work item.

| # | Abuse case | Mechanism |
|---|-----------|-----------|
| 1 | **Reply as prompt injection**: whoever reaches the API can type into the agent's terminal. | Accepted and bounded, not new: the same plane already serves `sessions/control` (spawn/kill — strictly higher privilege, `core/sessions.py`), the network boundary stays the exposure guard + gateway (decision-059), and CORS stays the exact-origin allowlist. The pasted reply carries a provenance header, and every reply lands in the event log (`session.reply_sent`, plus `api.request`) with the claimed actor — an audit trail, never authentication. |
| 2 | **Reply revives or spawns a session**: a crafted reply to a dead/missing session starts an agent. | Fail closed (R2.3): no session → 404; dead or absent pane → 404; the dispatcher's respawn path is deliberately not invoked. |
| 3 | **Reply bypasses pause**: pause is the operator's "deliver nothing" switch. | R2.4: paused sessions are refused with 400. |
| 4 | **The reply's ticket comment re-enters the loop**, delivering the answer twice (once by paste, once by poller-forward). | The report comment is composed by the-loop (a delivery *report* quoting the reply) and stamped `mark_self_authored` — both trigger paths drop marked bodies before the authorized-actor check (issue-64/104 machinery, unchanged). |
| 5 | **A forgotten marker on the agent's question resumes its own session** — today's standing risk. | Removed by construction (R1.1): the verb stamps centrally; no agent memory involved. The stamp is idempotent, so a question that already carries a marker is not double-stamped. |
| 6 | **`ask` as a comment-posting oracle**: any local user can post to the ticket under the operator's gh credentials. | Not new surface: local shell access already *is* `gh` access (and `sessions start/stop`); the verb adds attribution + marker to what the same user could post anyway, and records the actor in the event. |
| 7 | **Question/reply text in committed logs**: the event log holds question and reply text. | The event log is already git-ignored local state (`.the-loop/logs/`, decision-025); nothing new is committed. |

**Risk tier: 3** (`human-approves-pr`). Unlike issue-211 (tier 4) this touches no
schema/sensitive path and widens no *network or read* boundary: the new write
capability (paste into a pane) is granted to a plane that can already spawn, kill and
clean up the same sessions. A named human security sign-off is therefore not mandated
(`security.review.humanSignOffMinTier: 4`), but the PR approval gate stands.
