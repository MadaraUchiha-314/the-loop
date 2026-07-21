---
type: requirements
phase: requirements-definition
workItem: issue-32
status: approved
approvedBy: ["@MadaraUchiha-314 (PR #35: \"let's implement\", 2026-07-17)"]
collaborators: [product-manager, architect, engineer]
overrides: {}
---

# Requirements: tmux-backed observable/interactive harness sessions

> Phase 1 of 3 (requirements → design → tasks), derived from the locked
> [`brainstorm.md`](brainstorm.md). Ticket:
> [issue #32](https://github.com/MadaraUchiha-314/the-loop/issues/32). This phase MUST
> be reviewed and approved before moving to design.

## Introduction

When the webhook receiver auto-executes a work item, it spawns the harness as an
invisible headless subprocess — nobody can watch the agent work or steer it mid-run.
This work item adds a **tmux session runner**: opt-in via a receiver-global
`routing.runner: tmux`, the harness runs as an **interactive TUI inside a named tmux
session** that humans can attach to locally, over SSH, or through a shipped
web-terminal layer (ttyd), while webhook events keep flowing into the same session.

Decisions inherited from the locked brainstorm: Option A semantics behind an Option C
runner seam; receiver-global runner; access control is environmental (no auth built by
the-loop); the web layer ships, with the ttyd/tmux dependency story owned by the-loop.
The event-delivery mechanism (direct injection vs. hybrid idle-only headless resume —
brainstorm Q2) is a design-phase decision these requirements deliberately do not fix.

## Requirements

### Requirement 1 — tmux session runner

**User story:** As a developer running the-loop's webhook receiver, I want auto-executed
work items to run as interactive harness TUIs inside named tmux sessions, so that I can
watch the agent work and steer it live instead of it running invisibly.

#### Acceptance criteria (EARS)

1. WHEN the receiver spawns a session and `routing.runner` is `tmux` THEN the system
   SHALL start the configured harness's interactive TUI inside a detached tmux session
   with a predictable name derived from the work item (e.g. `loop/<work-item-slug>`).
2. WHEN `routing.runner` is `process` or unset THEN the system SHALL behave exactly as
   today (headless spawn/resume), with no configuration migration required.
3. WHEN a tmux-mode session is registered THEN the session registry entry SHALL record
   the runner kind and the tmux target so later events and CLI commands can find it.
4. IF `routing.runner` is `tmux` and the `tmux` binary is not available THEN the spawn
   SHALL fail with an actionable error naming the missing dependency; the system SHALL
   NOT silently fall back to the `process` runner.
5. WHILE a tmux-mode session is running, the receiver process SHALL be able to restart
   without terminating the tmux session (the tmux server owns the session lifetime).

### Requirement 2 — session identity in tmux mode

**User story:** As the webhook receiver, I want the harness session/chat id of a
tmux-hosted session captured at spawn time, so that follow-up webhook events route to
the same conversation.

#### Acceptance criteria (EARS)

1. WHEN a tmux-mode session starts THEN the system SHALL determine the harness
   session/chat id (e.g. a pre-assigned id passed to the harness, or hook-based capture
   — per-harness mechanism decided in design) and record it in the registry.
2. IF the session id cannot be determined THEN the system SHALL report the failure and
   SHALL NOT register a session entry that cannot receive follow-up events.
3. WHEN either supported harness (`claude`, `cursor`) is the spawn target THEN the same
   runner contract SHALL apply through the existing `HarnessAdapter` seam.

### Requirement 3 — event delivery into a live session

**User story:** As a work-item owner, I want webhook events (review comments, CI
results) to keep reaching the session while it runs interactively, so that automation
continues even when a human is watching or typing.

#### Acceptance criteria (EARS)

1. WHEN a routed event matches a tmux-mode session THEN the system SHALL deliver the
   rendered event prompt into that session's conversation (mechanism — direct TUI
   injection vs. hybrid idle-only headless resume — is the design-phase decision from
   brainstorm Q2).
2. WHILE earlier events for a session are still being delivered or processed, the
   system SHALL queue later events FIFO per session, preserving the existing
   one-at-a-time dispatcher invariant.
3. WHEN delivery into a tmux-mode session fails THEN the system SHALL log the failure
   and discard the delivery id so GitHub redelivery can retry it.
4. WHEN an event prompt is delivered THEN a human attached to the session SHALL be able
   to see the event arrive in the TUI (visibility is the point of tmux mode).

### Requirement 4 — discovery and attach UX

**User story:** As a user with shell access to the host (local terminal or SSH), I want
to discover running sessions and attach to them, so that observing/steering takes one
command.

#### Acceptance criteria (EARS)

1. WHEN I run `the-loop sessions list` THEN tmux-mode sessions SHALL display their tmux
   target alongside the existing columns.
2. WHEN I run `the-loop sessions attach <work-item>` for a tmux-mode session THEN the
   system SHALL attach my terminal to that session's tmux session (read-only attach
   available via tmux's native `-r`).
3. IF I request attach for a session that is not tmux-mode or no longer exists THEN the
   system SHALL fail with a message stating why and how to find live sessions.
4. WHEN I detach (standard tmux detach) THEN the session SHALL continue running and
   receiving events unaffected.

### Requirement 5 — web terminal layer (ships)

**User story:** As a user with a URL to the host (access controlled by my network — VPN,
provider controls, or localhost on my laptop), I want a browser terminal onto a
session, so that I can observe/steer without a local terminal or SSH client.

#### Acceptance criteria (EARS)

1. WHEN the web terminal is enabled in configuration THEN the system SHALL serve
   tmux-mode session(s) over HTTP via ttyd.
2. WHEN no bind address is configured THEN the web terminal SHALL bind to `127.0.0.1`
   (sensible-default binding; exposing it wider is an explicit configuration act).
3. The system SHALL NOT implement authentication of its own: access control is
   environmental per the locked brainstorm assumption.
4. WHEN the web terminal serves a session THEN typing in the browser SHALL reach the
   same tmux session other attach modes use (one session, many clients).

### Requirement 6 — dependency verification (installability)

**User story:** As someone installing the-loop, I want the tmux/ttyd dependencies
verified with clear guidance, so that the feature works out of the box or tells me
exactly what to install.

#### Acceptance criteria (EARS)

1. WHEN `the-loop init` runs, or the receiver starts with `routing.runner: tmux` (or
   the web terminal enabled) THEN the system SHALL verify the required native
   dependencies (`tmux`; `ttyd` when web is enabled) and fail with per-platform
   installation guidance if any is missing.
2. IF all required dependencies are present THEN verification SHALL be silent (no
   noise on the happy path).
3. The design MAY additionally propose auto-downloading ttyd's static release binary
   into a the-loop-managed directory (brainstorm enhancement candidate); auto-install
   via system package managers is rejected (recorded in the brainstorm).

### Requirement 7 — session lifecycle end-to-end

**User story:** As a developer, I want tmux-mode sessions cleaned up when their work
item finishes, so that finished agents don't accumulate as zombie tmux sessions.

#### Acceptance criteria (EARS)

1. WHEN a work item's PR is merged or closed THEN the system SHALL close the registry
   session (existing behaviour) and SHALL terminate the corresponding tmux session.
2. WHEN `the-loop sessions close <work-item>` targets a tmux-mode session THEN it SHALL
   terminate the tmux session in addition to marking the registry entry closed.
3. IF the tmux session was already gone THEN close SHALL still succeed on the registry
   side and note the missing tmux session.

## Non-functional requirements

- **Zero runtime dependencies (decision-005/016):** the implementation uses the Python
  stdlib only; tmux and ttyd are host binaries invoked as subprocesses.
- **Harness uniformity:** both `claude` and `cursor-agent` are supported through the
  existing `HarnessAdapter` contract; nothing is claude-only by construction.
- **Backwards compatibility:** with `routing.runner` unset, observable behaviour is
  identical to today; existing registry files remain readable.
- **Observability:** runner operations (spawn, delivery, attach, close) log at the same
  levels dev and runtime, consistent with the existing receiver logging.
- **Config schema:** new keys (`routing.runner`, web-terminal settings) are added to
  `.the-loop/config.schema.json` and validated like the rest of the routing config.

## Out of scope

- Authentication/TLS for the web terminal (environmental access control — locked
  brainstorm assumption).
- Per-work-item runner selection (receiver-global only; recorded as a zero-migration
  later extension).
- Alternative multiplexer backends (screen, Zellij) and asciinema-style broadcast.
- Vendor-hosted session sharing (claude.ai/code, Cursor's hosted surface).
- Changing the `process` runner's dispatch semantics.

## Open questions

- **Brainstorm Q2 (design phase):** event-delivery mechanism into the live TUI —
  best-effort `send-keys` injection vs. hybrid idle-only headless resume. Decided in
  `design.md`, informed by a spike against both harness TUIs.
- **Brainstorm Q3 (design phase):** exact per-harness session-id capture and
  turn-completion signals (claude `--session-id`/hooks; cursor-agent equivalents).
