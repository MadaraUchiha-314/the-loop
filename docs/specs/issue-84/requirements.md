---
type: requirements
phase: requirements-definition
workItem: "issue-84"
status: draft
approvedBy: []
collaborators: [product-manager, engineer]
overrides: {}
---

# Requirements: emoji reactions acknowledging that the-loop is processing an entity

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (https://kiro.dev/docs/specs/). Tier 3 (`human-approves-pr`): spec + code are
> approved together at the PR.

## Introduction

Today there is no visible signal that the-loop has picked up a comment, issue or
PR — the first feedback a human gets is the harness's reply comment after the
work is done ([issue #84](https://github.com/MadaraUchiha-314/the-loop/issues/84)).
The owner asked for lightweight emoji acknowledgements on the triggering GitHub
entity: one when the-loop **starts** working an event (👀), one when it has
**completed** it (✅), and one on **errors** (⁉️) — configurable in the CLI
config yaml, and a no-op on work-item platforms that have no emoji reactions.

One platform constraint shapes the acceptance criteria: GitHub's reaction
palette is fixed (`+1 -1 laugh confused heart hooray rocket eyes`). ✅ and ⁉️
do not exist as GitHub reactions, so the defaults map each state to the closest
supported emoji (👀 `eyes`, 🎉 `hooray`, 😕 `confused`) and the mapping is
operator-configurable.

## Requirements

### Requirement 1 — lifecycle reactions on the triggering entity

**User story:** As an operator (or any collaborator watching the repo), I want
the-loop to react on the comment/issue/PR that triggered it, so that I can see
at a glance that it has started working, finished, or hit an error — before any
reply comment exists.

#### Acceptance criteria (EARS)

1. WHEN the dispatcher begins processing a routed event (the event is dequeued
   for delivery to, or spawn of, a harness session) THEN the system SHALL add
   the configured **started** reaction (default `eyes` 👀) to the triggering
   entity.
2. WHEN the dispatch of that event succeeds (delivered/resumed/spawned) THEN
   the system SHALL add the configured **completed** reaction (default
   `hooray` 🎉) to the same entity.
3. WHEN the dispatch fails terminally for that attempt (delivery/spawn failure,
   missing adapter, vanished session, or a dispatch-worker crash) THEN the
   system SHALL add the configured **error** reaction (default `confused` 😕).
4. WHEN the event carries a comment (`issue_comment`,
   `pull_request_review_comment` — webhook or poll path) THEN the reaction
   SHALL land on that **comment**; WHEN it carries no comment but an issue/PR
   (presence/labeled/review events) THEN the reaction SHALL land on the
   **issue/PR** itself; CI events with neither SHALL get no reaction.
5. Reactions SHALL be **best-effort**: a reaction failure SHALL NOT fail,
   retry, delay or drop the dispatch itself, and SHALL NOT change the existing
   retry/dedup semantics. (Corollary: a retried event may legitimately end up
   with both the error and, later, the completed reaction — reactions are an
   append-only trail, and GitHub ignores a duplicate reaction by the same
   user.)
6. Events the-loop does **not** process (unauthorized actor, self-authored
   reply, disabled event type, duplicate delivery, unmatched with
   `spawnOnUnmatched: never`, PR-close lifecycle handling) SHALL get **no**
   reaction.

### Requirement 2 — configurable in the CLI config yaml

**User story:** As an operator, I want to choose the emoji per state (or turn
the feature off) in `cli-config.yaml`, so the acknowledgement style is mine.

#### Acceptance criteria (EARS)

1. The feature SHALL be configured under
   `webhooks.ghWebhook.routing.reactions` in the CLI config (shared by the
   webhook receiver AND the poller, like all other dispatch behaviour):
   `enabled`, `started`, `completed`, `error`, `ghBinary`.
2. Each state SHALL accept one of GitHub's supported reaction names
   (`+1 -1 laugh confused heart hooray rocket eyes`) or `""` (skip that state),
   enforced by `cli-config.schema.json`.
3. `enabled` SHALL default to **false** (opt-in): reacting posts to GitHub with
   the operator's own `gh` credentials, and the daemon previously never wrote
   to GitHub — turning that on silently on upgrade would violate the CLI's
   fail-closed philosophy. (the-loop's own checked-in `cli-config.yaml`
   enables it — dogfooding.)
4. WHEN the CLI config file is edited while the receiver/poller runs THEN the
   reactions config SHALL hot-reload with the rest of the soft routing policy.

### Requirement 3 — no-op where reactions are not available

**User story:** As an operator on a platform without emoji reactions, I want
the feature to disappear silently rather than error.

#### Acceptance criteria (EARS)

1. IF the routed event's work item is not a GitHub one (a future Jira/other
   poll provider) THEN reacting SHALL be a silent no-op.
2. IF the event payload carries no reactable target (no repository, no
   comment, no issue/PR number — e.g. `workflow_run`) THEN reacting SHALL be a
   no-op.
3. IF the `gh` CLI is not on PATH THEN reacting SHALL be a no-op with a
   **single** warning (not one per event), and the receiver/poller SHALL still
   start and dispatch normally — the CLI's zero-required-dependency guarantee
   is preserved (reactions never join `check_dependencies`).

### Requirement 4 — observability

**User story:** As an operator debugging the trigger path, I want reaction
outcomes in the event log, so `the-loop events` shows the full story.

#### Acceptance criteria (EARS)

1. WHEN a reaction is added THEN the system SHALL emit a `reaction.added`
   event-log record (work_item, state, content, target).
2. WHEN adding a reaction fails (gh error/timeout) THEN the system SHALL emit
   `reaction.failed` (warning level) and carry on.

## Security considerations (threat-model-lite)

- **New write surface:** this is the CLI daemon's **first write to GitHub**
  (everything before was read-only `gh` listing or inbound webhooks). The write
  is confined to the reactions API — it posts **no text**, so it adds no
  prompt-injection surface and cannot leak workspace content. It runs with the
  operator's own `gh` auth, exactly like the poller reads (decision: no token
  of its own).
- **Untrusted payload → API coordinates:** the reaction target (owner/repo,
  comment id / node id, issue number) is derived from event payloads. Those
  payloads are already HMAC-verified (webhook) or synthesized from `gh`'s own
  output (poll), and only authorized-actor events reach dispatch — but the
  values are still validated defensively (numeric ids parsed as integers,
  node ids / owner / repo matched against strict character classes) before
  being placed into a `gh api` argv (list-form exec, no shell).
- **Config injection:** the reaction content is operator-controlled config,
  validated against the fixed palette (schema + runtime check); an unknown
  value is skipped with a warning, never passed through.
- **Fail closed:** disabled by default; any doubt (no target, non-GitHub
  provider, missing gh, invalid content) resolves to a no-op, never to a
  blocked or altered dispatch.
- **Abuse case — reaction spam:** a retried event re-adds the same reaction;
  GitHub treats a duplicate reaction by the same user as idempotent, so
  retries cannot accumulate spam.
