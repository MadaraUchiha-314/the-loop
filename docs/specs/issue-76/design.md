---
type: design
phase: design
workItem: "issue-76"
status: draft
approvedBy: []
collaborators: [architect, engineer]
overrides: {}
---

# Design: clone-and-worktree workspace for spawned sessions

> Phase 2 of 3 (requirements → design → tasks). Derives from
> `docs/specs/issue-76/requirements.md`. Decision: `docs/decisions/decision-034.md`.

## Overview

A new provider-neutral `the_loop.workspace` module owns the daemon's checkouts: one clone
per repo under `<root>/<host>/<owner>/<repo>`, and one git worktree per work item under
`<root>/.worktrees/<host>/<owner>/<repo>/<slug>`. The dispatcher calls it on the spawn
path (to resolve a session's `cwd`) and on the PR-close path (to clean up), gated by
`routing.workspace.root` being set. Everything else — the session registry, resume,
per-session FIFO dispatch, tmux runner, poller — is unchanged: a worktree is just a
directory, recorded as the session's `cwd`, so the existing "resume runs in `cwd`"
contract (decision-016) carries redelivered events back into the same worktree for free.

## Components

### `the_loop.workspace` (new)

- **`RepoTarget`** — `(host, owner, repo, clone_url)`; `rel_path` = `host/owner/repo`.
- **`repo_target_from_payload(payload, *, protocol, default_host)`** — resolves a
  `RepoTarget` from a webhook or synthesised payload. Uses `clone_url`/`ssh_url`/
  `html_url` when present (real webhook) and reconstructs them from `full_name` +
  `default_host` otherwise (poller). Returns `None` when no repository is named.
  Validates each path segment (`_safe_component`) — R5.1.
- **`Workspace(root, *, git_binary)`**:
  - `repo_dir(target)` / `worktree_dir(target, slug)` — the layout (R2.1, R3.1).
  - `is_available()` — `git` on PATH (verified before use, like the tmux runner).
  - `ensure_clone(target)` — clone if absent, else best-effort `git fetch --prune`
    (a network blip on refresh must not block dispatch) — R2.2.
  - `default_branch(repo_dir)` — from `origin/HEAD`, falling back to `main`.
  - `ensure_worktree(target, slug, *, branch)` — clone-then-worktree; PR head branch via
    `git worktree add -B <ref> origin/<ref>` (falling back to `--detach` at the default
    branch if the ref is unavailable or when no branch is given) — R3.2/R3.3. Idempotent:
    an existing worktree is returned as-is.
  - `remove_worktree(target, slug)` — `git worktree remove --force` + `prune`, then
    ensure the dir is gone; best-effort, primary clone untouched — R4.1/R4.2.
- **`WorkspaceError`** — raised on a git failure so the caller can fail+retry (R5.2).

### Dispatcher wiring (`the_loop.webhook.dispatcher`)

- **`WorkspaceConfig`** mirrors `routing.workspace` (`root`, `cloneProtocol`,
  `defaultHost`, `keepWorktreeOnClose`, `gitBinary`); `enabled` ⇔ `root` non-empty.
  Added to `RoutingConfig`.
- `Dispatcher` builds a `Workspace` when `workspace.enabled`, else `None` (legacy). It is
  rebuilt on hot-reload (a caller-supplied override is preserved for tests/embedding).
- **`_prepare_workspace(work_item, routed)`** — returns `spawnWorkdir` when disabled or
  the payload names no repo; otherwise `ensure_worktree(...)` and returns the worktree
  path. `_spawn_for`/`_spawn_tmux` use this for `cwd` and record it on the `Session`;
  a `WorkspaceError` becomes `session.spawn_failed` + delivery release (R5.2).
- **`_cleanup_workspace(session, routed)`** — called in the existing PR-close branch of
  `handle`, after `registry.close`; removes the worktree unless `keepWorktreeOnClose`
  (R4). Best-effort — never raises out of close.
- **`_pr_head_ref(routed)`** — the PR head branch to seed a PR-triggered worktree.

### Event log (`the_loop.eventlog`)

Two new `EVENT_TYPES`: `workspace.prepared` (work_item, repo_dir, worktree, branch) and
`workspace.cleaned` (work_item) — R5.3.

### Config schema / templates

`.the-loop/cli-config.schema.json` gains `routing.workspace`; the shipped
`cli-config.yaml` template and the `automation.md` reference document it.

## Data / layout

```
<root>/
  github.com/                     # or the enterprise domain
    <owner>/<repo>/               # primary clone — default branch, fetched, never worked in
  .worktrees/
    github.com/<owner>/<repo>/
      <work-item-slug>/           # one worktree per work item (session cwd)
```

## Testing strategy

- **`tests/test_workspace.py`** (skipped when `git` is absent): a bare local repo stands
  in for the origin. Covers `repo_target_from_payload` (full webhook, ssh, lean poller
  payload, traversal rejection), layout, `ensure_clone` (create + reuse + bad-URL raise),
  `ensure_worktree` (detached default, PR branch checkout, unknown-branch fallback,
  idempotency), and `remove_worktree`.
- **Dispatcher integration** (same file): a real `Workspace` over a local origin +
  recording adapter proves a spawn runs in the worktree cwd, PR-close removes the
  worktree (and keeps it under `keepWorktreeOnClose`), and the disabled path still uses
  `spawnWorkdir`.
- **Config parsing:** `WorkspaceConfig` defaults + overrides via `RoutingConfig`.

## Re-evaluation triggers

- **Auth beyond git credentials** (per-repo tokens, app installs) — revisit if operators
  need it; today `gh auth setup-git` / ssh keys cover it.
- **Worktree GC / disk pressure** — merged-PR cleanup handles the common case; a periodic
  prune of abandoned worktrees could follow if long-lived daemons accumulate them.
- **Non-GitHub providers** (the reserved `jira:` future) — `RepoTarget`/`Workspace` are
  already provider-neutral; only payload→target resolution would extend.
