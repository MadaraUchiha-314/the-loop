---
type: requirements
phase: requirements-definition
workItem: "issue-76"
status: draft
approvedBy: []
collaborators: [architect, engineer]
overrides: {}
---

# Requirements: clone each event's repo into a per-work-item workspace

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (https://kiro.dev/docs/specs/).

## Introduction

the-loop's CLI daemon (`gh-webhook`/`poll`) watches many repos and routes their activity
into harness sessions, independent of any one repo (decision-032). But a spawned session
must operate on a real checkout of the repo an event concerns, and today it is spawned in
a single static directory (`routing.spawnWorkdir`) — which only works when the operator
has pre-cloned exactly one repo there. Issue #76 asks the daemon to obtain the checkout
itself: clone the event's repo (if not already present) under a configurable workspace
root laid out `<root>/<host>/<owner>/<repo>`, and use a git worktree per work item when
the repo is already cloned, cleaning the worktree up once the work item's PR is
merged/closed.

## Requirements

### Requirement 1 — Configurable workspace root

**User story:** As an operator, I want to configure a workspace root path, so that the
daemon has one place to clone every repo it acts on.

- **R1.1** The CLI config SHALL expose `webhooks.ghWebhook.routing.workspace.root`.
- **R1.2** WHEN `root` is empty/unset, the daemon SHALL preserve today's behaviour
  (spawn in `spawnWorkdir`, clone nothing) — the feature is opt-in.
- **R1.3** WHEN `root` is set, spawned sessions SHALL run under it per R2–R3.

### Requirement 2 — Clone per repo in the documented layout

**User story:** As an operator, I want each repo cloned once at a predictable path, so I
can find and reuse checkouts across work items.

- **R2.1** The daemon SHALL clone a repo it has an event for to
  `<root>/<host>/<owner>/<repo>`, where `host` is `github.com` or the enterprise domain.
- **R2.2** WHEN the repo is already cloned there, the daemon SHALL reuse it (refreshing
  with `git fetch`) rather than re-cloning.
- **R2.3** The host SHALL be derived from the event payload when available, falling back
  to a configurable `defaultHost` for payloads that carry no URL (e.g. the poller's).
- **R2.4** Cloning SHALL use the operator's own git credentials; the daemon SHALL NOT
  store or handle secrets. `cloneProtocol` SHALL select https or ssh clone URLs.

### Requirement 3 — Per-work-item checkout, with a configurable strategy

**User story:** As an operator, I want each work item worked in its own checkout, so that
concurrent work items don't collide; and I want to choose the layout so multi-repo work
items stay easy to manage.

- **R3.1** For each spawned work item the daemon SHALL provide a checkout of the repo and
  run the session there, recording it as the session's `cwd`.
- **R3.2** A `workspace.strategy` option SHALL select the layout:
  - **`worktree`** (default) — a shared clone per repo plus a git worktree per work item,
    so concurrent work items on one repo share objects.
  - **`clone`** — a folder per work item (`<root>/.work-items/<slug>/`) holding a full
    clone of each repo the work item touches, self-contained for multi-repo work items.
- **R3.3** A work item with no known branch (a fresh issue) SHALL get its checkout on the
  default branch (detached, in `worktree`; checked out in place, in `clone`); a
  PR-triggered work item SHALL seed from the PR head branch, falling back to the default
  branch if that ref is unavailable.
- **R3.4** Checkout provisioning SHALL be idempotent across restarts/redeliveries (reuse
  an existing checkout rather than failing or duplicating).

### Requirement 4 — Cleanup on PR merge/close

**User story:** As an operator, I want a work item's checkout cleaned up when it's done,
so the workspace doesn't accumulate stale checkouts.

- **R4.1** WHEN a work item's PR is merged/closed (the event that already auto-closes its
  session), the daemon SHALL remove that work item's checkout — the worktree
  (`worktree`) or the whole per-work-item folder (`clone`).
- **R4.2** Cleanup SHALL be best-effort (never break session close); in `worktree`
  strategy it SHALL leave the shared per-repo clone intact.
- **R4.3** A `keepCheckoutOnClose` option SHALL let an operator retain checkouts for
  post-mortem.

### Requirement 5 — Robustness & observability

- **R5.1** Remote-influenced path segments (`host`/`owner`/`repo`/`slug`) SHALL be
  validated to prevent path traversal outside the root.
- **R5.2** A clone/worktree failure at spawn SHALL fail the spawn and release the
  delivery id so it is retried (redelivery / next poll cycle), rather than running in the
  wrong directory.
- **R5.3** Workspace preparation and cleanup SHALL emit event-log records
  (`workspace.prepared`, `workspace.cleaned`).

## Security considerations

- **Path traversal (R5.1):** `full_name`/host come from webhook payloads (untrusted). A
  hostile value (`../../etc`) must never escape the workspace root — each segment is
  allowlist-validated before being joined into a path.
- **Credentials:** the workspace shells out to `git` and relies on the operator's
  configured credential helper (e.g. `gh auth setup-git`); no tokens are read, logged, or
  written by the-loop. `cloneProtocol: ssh` supports key-based auth for private repos.
- **Untrusted content is unchanged:** the cloned repo's contents and the event payload
  remain untrusted data to the harness — this feature only provides the checkout, it does
  not widen what the session is told to trust (the existing prompt guards still apply).
