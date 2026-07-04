---
type: requirements
phase: requirements-definition
workItem: issue-15
status: approved
approvedBy: ["@MadaraUchiha-314 (PR #16: let's implement it now)"]
collaborators: [architect, engineer]
overrides: {}
---

# Requirements: GitHub events trigger a harness session programmatically

> **Source of truth:** GitHub [issue #15](https://github.com/MadaraUchiha-314/the-loop/issues/15)
> is the canonical requirements input for this work item. This file distills it into
> reviewable, testable requirements. Design and the task DAG live in `design.md` and
> `tasks.md`.

## Introduction

Claude.ai/code can already watch a PR and wake an existing session when comments, CI
results or reviews arrive. Users who cannot use that hosted service need the same
capability locally: a GitHub webhook event should reach the *right* running (or new)
Claude Code / Cursor agent session on the user's own machine, programmatically. the-loop
already ships the receiver half (`the-loop gh-webhook`, HMAC-verified); this work item
specifies the routing half — session tracking, event→session matching, and harness
triggering — for multiple concurrent sessions on the same executor.

## Requirements

### R1 — Delivery-approach decision (MCP vs webhook receiver)

**User story:** As the architect, I want the "does the GitHub MCP support subscribing to
events?" question answered and recorded, so that the implementation builds on the right
transport.

#### Acceptance criteria (EARS)

1. The design SHALL evaluate the preferred approach (GitHub MCP event subscription) and
   document whether it is viable for locally-run harnesses.
2. IF the MCP approach is not viable THEN the design SHALL adopt the webhook-receiver +
   programmatic-trigger approach and record the choice (and its re-evaluation trigger)
   as a decision record under `docs/decisions/`.

### R2 — Session registry (event ↔ session linkage metadata)

**User story:** As the-loop, I want every harness session launched for a work item to be
tracked with metadata linking it to that work item, so that an incoming event for a PR /
GitHub issue (later: Jira issue) can be routed to the right session.

#### Acceptance criteria (EARS)

1. The system SHALL persist, per session: a work-item reference
   (`github:<owner>/<repo>#<number>`, extensible to other providers), the harness kind
   (`claude` | `cursor`), the harness's own session/chat id, the working directory the
   session runs in, a status (`active` | `closed`), and created/last-event timestamps.
2. The `the-loop` CLI SHALL provide `sessions register|list|close` to manage the
   registry, so both humans and harnesses (via a workflow step or hook) can register.
3. WHEN a session is registered for a work item that already has an `active` session
   THEN the system SHALL refuse (one work item ↔ one session) unless `--force` replaces
   the stale entry.
4. Registry writes SHALL be atomic and safe under concurrent access from multiple
   sessions on the same machine.

### R3 — Event → session routing

**User story:** As a user, I want a webhook event about a PR or issue to reach the
session working that item, so that the harness reacts (fix CI, answer a review comment)
without me re-prompting it.

#### Acceptance criteria (EARS)

1. WHEN a verified webhook event arrives THEN the system SHALL extract the work-item
   reference(s) it concerns (issue number, PR number, or the PR behind a
   `workflow_run`/`check_run`/branch) and look them up in the registry.
2. IF an `active` session matches THEN the system SHALL deliver the event to that
   session by resuming it with a structured prompt describing the event.
3. IF no session matches THEN the system SHALL apply the configured policy
   (`spawnOnUnmatched`: `never` (default) → log and drop; `always` → spawn a new session
   for the work item and register it).
4. WHEN the same delivery id (`X-GitHub-Delivery`) is seen twice THEN the system SHALL
   process it at most once (GitHub redeliveries are the retry path, not a duplication
   path).
5. The system SHALL only route event types enabled in configuration
   (`webhooks.ghWebhook.events`).

### R4 — Programmatic harness triggering (Claude Code and Cursor)

**User story:** As the-loop, I want a uniform programmatic interface to "wake this
session with this prompt" for both Claude Code and Cursor, so that routing is
harness-agnostic.

#### Acceptance criteria (EARS)

1. The system SHALL define a harness-adapter contract (`resume(session, prompt)`,
   `spawn(work_item, prompt, cwd)`) with implementations for Claude Code and Cursor.
2. The Claude Code adapter SHALL trigger via the official CLI in non-interactive mode
   (`claude -p … --resume <session-id> --output-format json`), invoked in the session's
   recorded working directory (resume lookup is scoped to the project directory).
3. The Cursor adapter SHALL answer the issue's TODO: Cursor's official programmatic
   surfaces are the `cursor-agent` CLI (headless `-p`, `--resume <chat-id>`,
   `--output-format json`) and a TypeScript SDK (`@cursor/sdk`); there is **no official
   Python SDK**, so the adapter SHALL shell out to `cursor-agent`.
4. Spawning a new session SHALL capture the harness-assigned session/chat id from the
   CLI's JSON output and register it (R2).
5. Adapters SHALL be invoked as subprocesses so the CLI keeps its zero-runtime-dependency
   guarantee; SDK-based adapters MAY be added later as optional extras.

### R5 — Multiple concurrent sessions per executor

**User story:** As a user, I want several the-loop sessions for different work items
running on one machine, so that events for each item reach only its own session.

#### Acceptance criteria (EARS)

1. The system SHALL support many `active` sessions concurrently on the same machine,
   each linked to a different work item.
2. WHILE events for one session are being processed the system SHALL queue further
   events for that session and deliver them strictly in arrival order (a harness session
   handles one resume at a time).
3. Events for *different* sessions SHALL be dispatched in parallel, bounded by a
   configurable concurrency limit.

### R6 — Label-gated auto-execution (GitHub workflow)

**User story:** As a maintainer, I want a configurable issue/PR label to opt a work item
into autonomous execution, so that the-loop starts (and continues) work only on items I
have explicitly marked.

#### Acceptance criteria (EARS)

1. The label SHALL be configurable per project (`webhooks.ghWebhook.routing.autoExecuteLabel`,
   default `the-loop: auto-execute`), and gating SHALL be enabled by
   `spawnOnUnmatched: labeled`.
2. WHEN an issue is created without the label THEN the system SHALL receive the event and
   take no action (no session).
3. WHEN the configured label is added to an issue (or PR) THEN the system SHALL spawn and
   register a new session and start the-loop's work-on flow on that item.
4. WHEN activity (comment, review, CI) occurs on a labelled item THEN the system SHALL
   route it to the existing session, or spawn one if the item is labelled but has none.
5. WHEN a PR linked to an issue (branch convention / closing keyword) has activity THEN
   the system SHALL resume the linked item's session; a PR that carries the label but is
   not linked to an issue SHALL be treated on its own ref the same way.
6. Label presence SHALL be read from the webhook payload (no extra GitHub API call),
   preserving the zero-dependency guarantee.

## Non-functional requirements

- **Zero runtime dependencies** — routing, registry and adapters use the stdlib only
  (PyYAML stays optional for config defaults).
- **Security** — existing HMAC verification stays mandatory in front of routing; the
  event payload is treated as untrusted input when rendered into the prompt; secrets
  come from env vars, never argv.
- **Observability** — every routing decision (matched / unmatched / deduped / dispatch
  result) is logged at the same levels dev-time and runtime.
- **Config contract** — new keys validate against `.the-loop/config.schema.json`;
  quality gates stay green (ruff, pyright, pytest, markdownlint, validate_config).

## Out of scope (this work item)

- Jira webhooks (the work-item reference format reserves the `jira:` prefix; a Jira
  router is a follow-up).
- Remote auto-provisioning of workspaces (the roadmap's "dream"); this work item routes
  to sessions on an executor the user already runs.
- Exposing the receiver publicly (tunnels such as `smee.io`/`cloudflared` are
  documented, not automated).

## Open questions

- Should `spawnOnUnmatched: always` gate on issue labels (e.g. only `loop:*`-labelled
  issues spawn sessions)? Raised on the ticket; default stays `never` until answered.
