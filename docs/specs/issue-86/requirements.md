---
type: requirements
phase: requirements-definition
workItem: "issue-86"
status: draft
approvedBy: []
collaborators: [product-manager, engineer]
overrides: {}
---

# Requirements: keep tmux sessions after the work completes, and announce how to attach

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (https://kiro.dev/docs/specs/). Tier 3 (`human-approves-pr`): spec + code are
> approved together at the PR.

## Introduction

A tmux-mode session is the-loop's window onto what an agent actually did. Today
that window slams shut exactly when a human most wants it
([issue #86](https://github.com/MadaraUchiha-314/the-loop/issues/86)):

- when the work item's PR is merged/closed the dispatcher **kills** the tmux
  session (same for `the-loop sessions close`), taking the whole transcript
  with it;
- even without an explicit kill, tmux destroys a window whose command exits, so
  a harness TUI that exits on its own erases its own scrollback;
- and nothing ever told the human the session existed in the first place — the
  `tmux attach -t loop-github--devbox-7` line lives only in the daemon's log,
  which the person reading the GitHub issue is not looking at.

This work item makes a finished session **inspectable after the fact** and puts
the attach command where the human already is: on the ticket.

## Requirements

### Requirement 1 — a completed work item's tmux session is retained

**User story:** As an operator, I want the tmux session to survive the work
item completing, so that I can read back what the agent did instead of losing
it the moment the PR merges.

#### Acceptance criteria (EARS)

1. WHEN a work item's PR is merged/closed and its registered session is
   tmux-mode THEN the system SHALL close the **registry** entry as it does
   today AND SHALL leave the tmux session running.
2. WHEN `webhooks.ghWebhook.routing.tmux.keepSessionOnClose` is `false` THEN
   the system SHALL kill the tmux session on close, i.e. the pre-issue-86
   behaviour SHALL remain available as an opt-out.
3. WHEN `the-loop sessions close` runs THEN it SHALL follow the same
   configured default, and SHALL accept explicit `--keep-tmux` / `--kill-tmux`
   overrides for a one-off decision.
4. WHEN a tmux session is retained on close THEN the system SHALL emit a
   `session.retained` event-log record (work item, tmux target) and log the
   attach command, so the trail says the session is still there.
5. WHEN a session is spawned for a work item whose deterministic tmux name is
   already taken by a retained session THEN the retained session SHALL be
   cleared first — the live work owns `loop-<slug>` (this is the existing
   stale-session clearing, now also reachable by a retained session, and is a
   documented consequence of the deterministic name).
6. Retention SHALL NOT change registry semantics: a closed session stays
   `closed`, is not matched for dispatch, and does not block a later spawn.

### Requirement 2 — the harness exiting does not destroy the transcript

**User story:** As an operator, I want the pane and its scrollback to stay
after the harness process exits, so "what happened" outlives the process.

#### Acceptance criteria (EARS)

1. WHEN a tmux session is spawned and
   `webhooks.ghWebhook.routing.tmux.remainOnExit` is `true` (the default) THEN
   the system SHALL configure the session's window with tmux's
   `remain-on-exit`, so the pane and its scrollback survive the harness
   process exiting.
2. IF setting that option fails (e.g. an older tmux) THEN the failure SHALL be
   a logged warning and the spawn SHALL still succeed — the option is a
   convenience, not a precondition.
3. WHEN a routed event targets a tmux session whose pane has **died** THEN the
   dispatcher SHALL treat that session as not live and take the existing
   respawn path (issue-80) — a retained-but-dead pane SHALL NEVER silently
   swallow a delivered event.
4. WHEN `the-loop sessions attach` targets a session with a dead pane THEN it
   SHALL attach (that is the point — reading the transcript back), not refuse.
5. WHEN the work item's session has been **closed** but its tmux session was
   retained THEN `the-loop sessions attach --work-item <ref>` SHALL still
   attach to it, noting that the session is closed.

### Requirement 3 — announce the session (and how to attach) on the ticket

**User story:** As a collaborator watching the issue, I want a comment telling
me the interactive session exists and how to attach, so I can watch the agent
work without reading the daemon's logs.

#### Acceptance criteria (EARS)

1. WHEN the dispatcher spawns a **tmux-mode** session for a work item THEN the
   system SHALL post a comment on that work item's GitHub issue/PR carrying
   the tmux session name and the `tmux attach -t <name>` command, plus the
   equivalent `the-loop sessions attach --work-item <ref>` invocation.
2. WHEN a dead tmux session is **respawned** (issue-80) THEN the system SHALL
   post the same announcement, worded as a respawn.
3. WHEN the spawned session is **process**-mode THEN no comment SHALL be
   posted — there is no terminal to attach.
4. Announcing SHALL be **best-effort**: a failure SHALL NOT fail, retry, delay
   or drop the dispatch, and SHALL NOT change retry/dedup semantics. IF the
   `gh` CLI is absent THEN announcing SHALL be a no-op with a **single**
   warning; IF the work item is not a GitHub one THEN it SHALL be a silent
   no-op.
5. The feature SHALL be configured at
   `webhooks.ghWebhook.routing.announce` (`enabled`, `ghBinary`), hot-reloading
   with the rest of the soft routing policy. `enabled` defaults to **true**,
   matching the `reactions` precedent (PR #85: out-of-box visibility is the
   point) — this is what the issue asks for.
6. The comment SHALL carry only coordinates that are already public or
   operator-visible: the tmux session name (derived from the work-item ref),
   the attach commands and the harness name. It SHALL NOT include filesystem
   paths, harness session ids, tokens, hostnames or any workspace content.

### Requirement 4 — observability

**User story:** As an operator debugging the trigger path, I want retention and
announcement outcomes in the event log, so `the-loop events` tells the whole
story.

#### Acceptance criteria (EARS)

1. WHEN a tmux session is retained on close THEN the system SHALL emit
   `session.retained` (work_item, tmux_target).
2. WHEN an announcement comment is posted THEN the system SHALL emit
   `session.announced` (work_item, tmux_target, respawned).
3. WHEN posting it fails THEN the system SHALL emit `session.announce_failed`
   (warning level) and carry on.

## Security considerations (threat-model-lite)

- **New write surface — the daemon's first *text* write to GitHub.** Reactions
  (issue-84) posted no text; an announcement comment does. The body is built
  from a fixed template plus values the-loop itself derived (the work-item ref
  and the tmux session name computed from it) — **never** from the event
  payload — so an attacker who can comment on a watched issue cannot inject
  text into what the-loop posts. AC3.6 bans paths/ids/hostnames from the body,
  so a public repo learns nothing about the operator's machine that the session
  name does not already imply.
- **Comment loop.** The daemon's own comment is an `issue_comment` event that
  can come back in as a trigger. The existing `authorizedUsers` guard already
  fails closed on any actor not on the operator's allowlist; an operator who
  lists their own login (the account `gh` posts as) must be aware the
  announcement is self-authored. Announcements are emitted only on
  spawn/respawn — never in response to a comment — so even if it did route,
  it cannot recurse.
- **Retained sessions hold state.** A kept tmux session keeps the harness's
  scrollback (and, if the pane is alive, a running agent with the operator's
  credentials) on the operator's own machine, for as long as tmux lives. This
  is the operator's box, it is opt-out (`keepSessionOnClose: false`), and
  `remain-on-exit` panes hold no live process. Documented in the capability
  doc so retention is a choice, not a surprise.
- **Unbounded accumulation.** Retention means finished sessions accumulate
  until the host reboots or the operator kills them. Bounded in practice by
  the deterministic name (a re-spawn on the same work item reclaims it,
  AC1.5), surfaced by `the-loop sessions list`, and reversible with the
  config flag / `sessions close --kill-tmux`.
- **Fail closed on doubt.** Any doubt inside the announcer (no `gh`, non-GitHub
  provider, malformed owner/repo) resolves to a no-op, never to a blocked or
  altered dispatch.
