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

A new provider-neutral `the_loop.workspace` module owns the daemon's checkouts, in one of
two strategies. The dispatcher calls it on the spawn path (to resolve a session's `cwd`)
and on the PR-close path (to clean up), gated by `routing.workspace.root` being set.
Everything else — the session registry, resume, per-session FIFO dispatch, tmux runner,
poller — is unchanged: a checkout is just a directory, recorded as the session's `cwd`, so
the existing "resume runs in `cwd`" contract (decision-016) carries redelivered events
back into the same checkout for free.

## Components

### `the_loop.workspace` (new)

- **`RepoTarget`** — `(host, owner, repo, clone_url)`; `rel_path` = `host/owner/repo`.
- **`repo_target_from_payload(payload, *, protocol, default_host)`** — resolves a
  `RepoTarget` from a webhook or synthesised payload. Uses `clone_url`/`ssh_url`/
  `html_url` when present (real webhook) and reconstructs them from `full_name` +
  `default_host` otherwise (poller). Returns `None` when no repository is named.
  Validates each path segment (`_safe_component`) — R5.1.
- **`Workspace(root, *, strategy, git_binary)`** — `strategy` is `worktree` (default) or
  `clone` (unknown values fall back to `worktree`):
  - `prepare(target, slug, *, branch)` / `cleanup(target, slug)` — the strategy-dispatch
    entry points the dispatcher calls; return the session `cwd` / remove the checkout.
  - `repo_dir` / `worktree_dir` (worktree) and `workitem_dir(slug)` /
    `clone_dir(target, slug)` (clone) — the layouts (R2.1, R3.1/R3.2).
  - `is_available()` — `git` on PATH (verified before use, like the tmux runner).
  - `ensure_clone` + `default_branch` + `ensure_worktree(target, slug, *, branch)` /
    `remove_worktree` — the **worktree** impl: shared clone (fetch if present), PR head
    via `git worktree add -B <ref> origin/<ref>` else `--detach` at the default branch;
    removal via `git worktree remove --force` + `prune`, shared clone kept (R2.2, R3.3,
    R4.1/R4.2). Idempotent.
  - `ensure_workitem_clone(target, slug, *, branch)` / `remove_workitem_clone(slug)` —
    the **clone** impl: full clone into `<root>/.work-items/<slug>/…` (default branch in
    place, or PR head via `checkout -B`), removal via a single `rmtree` of the folder
    (every repo the work item cloned) (R3.2/R3.3, R4.1). Idempotent.
- **`WorkspaceError`** — raised on a git failure so the caller can fail+retry (R5.2).

### Dispatcher wiring (`the_loop.webhook.dispatcher`)

- **`WorkspaceConfig`** mirrors `routing.workspace` (`root`, `strategy`, `cloneProtocol`,
  `defaultHost`, `keepCheckoutOnClose`, `gitBinary`); `enabled` ⇔ `root` non-empty.
  Added to `RoutingConfig`.
- `Dispatcher` builds a `Workspace` when `workspace.enabled`, else `None` (legacy). It is
  rebuilt on hot-reload (a caller-supplied override is preserved for tests/embedding).
- **`_prepare_workspace(work_item, routed)`** — returns `spawnWorkdir` when disabled or
  the payload names no repo; otherwise `workspace.prepare(...)` and returns the checkout
  path. `_spawn_for`/`_spawn_tmux` use this for `cwd` and record it on the `Session`;
  a `WorkspaceError` becomes `session.spawn_failed` + delivery release (R5.2).
- **`_cleanup_workspace(session, routed)`** — called in the existing PR-close branch of
  `handle`, after `registry.close`; `workspace.cleanup(...)` unless `keepCheckoutOnClose`
  (R4). Best-effort — never raises out of close.
- **`_pr_head_ref(routed)`** — the PR head branch to seed a PR-triggered checkout.

### Event log (`the_loop.eventlog`)

Two new `EVENT_TYPES`: `workspace.prepared` (work_item, strategy, checkout, branch) and
`workspace.cleaned` (work_item, strategy) — R5.3.

### Config schema / templates

`.the-loop/cli-config.schema.json` gains `routing.workspace`; the shipped
`cli-config.yaml` template and the `automation.md` reference document it.

## Data / layout

```
<root>/                             # strategy: worktree
  github.com/                       # or the enterprise domain
    <owner>/<repo>/                 # shared clone — default branch, fetched, never worked in
  .worktrees/
    github.com/<owner>/<repo>/
      <work-item-slug>/             # one worktree per work item (session cwd)

<root>/                             # strategy: clone
  .work-items/
    <work-item-slug>/               # one folder per work item (removed whole on close)
      github.com/<owner>/<repo>/    # full clone of each repo it touches (session cwd)
```

## Testing strategy

- **`tests/test_workspace.py`** (skipped when `git` is absent): a bare local repo stands
  in for the origin. Covers `repo_target_from_payload` (full webhook, ssh, lean poller
  payload, traversal rejection), layout, `ensure_clone` (create + reuse + bad-URL raise),
  `ensure_worktree` (detached default, PR branch checkout, unknown-branch fallback,
  idempotency), `remove_worktree`, and the **clone strategy** (work-item-centric layout,
  full clone on default/PR branch, idempotency, and cleanup removing the whole
  multi-repo work-item folder; unknown strategy falls back to `worktree`).
- **Dispatcher integration** (same file): a real `Workspace` over a local origin +
  recording adapter proves a spawn runs in the checkout cwd, PR-close removes it (and
  keeps it under `keepCheckoutOnClose`) — for **both** strategies — and the disabled path
  still uses `spawnWorkdir`.
- **Config parsing:** `WorkspaceConfig` defaults + overrides (incl. `strategy`) via
  `RoutingConfig`.

## Re-evaluation triggers

- **Auth beyond git credentials** (per-repo tokens, app installs) — revisit if operators
  need it; today `gh auth setup-git` / ssh keys cover it.
- **Checkout GC / disk pressure** — merged-PR cleanup handles the common case; a periodic
  prune of abandoned worktrees/work-item folders could follow if long-lived daemons
  accumulate them (the `clone` strategy is heavier on disk, one full clone per work item).
- **Non-GitHub providers** (the reserved `jira:` future) — `RepoTarget`/`Workspace` are
  already provider-neutral; only payload→target resolution would extend.
