# Decision 034: clone each event's repo into a per-work-item git worktree under a configurable workspace root

- **Status:** accepted
- **Date:** 2026-07-23
- **Deciders:** @MadaraUchiha-314 (issue #76)
- **Work item:** issue-76
- **Spec:** `docs/specs/issue-76/`

## Context

The CLI daemon (`gh-webhook`/`poll`) is deliberately independent of any one repo
(decision-032): it watches many repos and routes their activity into harness sessions.
But a spawned session has to *do* work — read files, run tests, push a branch — and that
requires a checkout of the repo the event concerns. Until now the dispatcher spawned
every session in a single static directory (`routing.spawnWorkdir`, default `.`), which
only works if the operator has pre-cloned exactly one repo there and never watches a
second. Issue #76: "when an activity happens in any repo, the-loop's cli also needs to
clone that repo (if not already there) before acting on the action … take in a config
for the path of the root of the workspace where everything will be cloned," following
the layout `<root>/<host>/<owner>/<repo>`.

The issue also poses the design question explicitly: "If the repo is already cloned, then
it needs to use a worktree to manage the particular work item — decide if worktree is the
best way or is there any better way? Cloning a new repo for every work item seems like an
overkill. Also think about the cleanup of the worktree after a task is done aka PR is
merged."

## Decision

Add an opt-in **clone-and-worktree workspace**, owned by a new provider-neutral
`the_loop.workspace` module and wired into the dispatcher's spawn/close paths. Configured
under `webhooks.ghWebhook.routing.workspace` (reused by the poller, like the rest of
`routing`):

- **One clone per repo**, at `<root>/<host>/<owner>/<repo>` exactly as the issue
  specifies (`host` is `github.com` or the enterprise domain, parsed from the payload's
  `html_url`, falling back to `workspace.defaultHost`). The primary clone stays on the
  default branch and is `git fetch --prune`ed to stay fresh — it is a shared object
  store / reference, never worked in directly.
- **One git worktree per work item** — the answer to the issue's design question. A
  worktree shares the primary clone's object database, so N concurrent work items on one
  repo cost one clone plus N cheap checkouts, not N full clones. Worktrees live under
  `<root>/.worktrees/<host>/<owner>/<repo>/<work-item-slug>`, a sibling of the
  human-facing checkout tree, so `<host>/<owner>/<repo>` stays a clean mirror of the
  remote and all runtime state is quarantined in one directory.
- **Branch seeding.** A spawn triggered by a fresh issue has no branch yet, so its
  worktree is created **detached at the default branch's tip** and the harness creates
  its own feature branch inside — this also sidesteps git's "branch already checked out"
  rule (the primary clone holds the default branch). A spawn triggered by a PR event
  seeds the worktree from the PR's head ref (`git worktree add -B <ref>`), falling back
  to a detached default-branch worktree if origin doesn't have that ref yet (e.g. a fork
  PR) rather than failing the spawn.
- **Cleanup on PR merge/close.** The dispatcher already auto-closes a session when its
  PR closes (decision-016); it now also `git worktree remove --force`s that work item's
  worktree and prunes. The primary clone and any local branch are left intact — cleanup
  is cheap and non-destructive. `keepWorktreeOnClose: true` keeps the worktree for
  post-mortem.
- **Opt-in and backward compatible.** `workspace.root` empty (the default) preserves the
  legacy behaviour exactly: sessions run in `spawnWorkdir`, nothing is cloned. Set a root
  to turn cloning on.

The session registry records each worktree as the session's `cwd`, so resumes
(decision-016) land in the same worktree with no further work — the existing
resume-in-`cwd` contract already carries this.

Consequences:

- **Git-only, provider-neutral, secret-free.** The workspace shells out to `git` (the one
  native dep, verified by `is_available`, like tmux in decision-021) and derives the
  clone URL/host from the payload — using the rich `clone_url`/`ssh_url`/`html_url` a real
  webhook carries, and reconstructing them from `full_name` + `defaultHost` for the
  poller's leaner synthesised payloads. Auth is the operator's own git credentials (e.g.
  `gh auth setup-git`); the workspace never touches secrets. `cloneProtocol: ssh` selects
  SSH URLs for key-based auth / private repos.
- **Path-traversal guard.** `host`/`owner`/`repo`/`slug` are remote-influenced, so each
  path segment is validated against a strict allowlist before it becomes a directory — a
  hostile `full_name` like `../../etc` is rejected, never joined into the root.
- **A git failure fails the spawn (and retries).** If clone/worktree setup raises, the
  spawn emits `session.spawn_failed` and releases the delivery id, so GitHub redelivery /
  the next poll cycle retries — better than silently running in the wrong directory. Two
  new event types, `workspace.prepared` and `workspace.cleaned`, keep the audit trail
  (decision-025) complete.
- **Idempotent across restarts/redeliveries.** `ensure_clone`/`ensure_worktree` reuse an
  existing clone/worktree instead of recreating it, so a redelivered event or a restarted
  daemon re-attaches to the same checkout.

## Alternatives considered

- **A fresh full clone per work item** — the issue calls this out as "overkill," and it
  is: every concurrent issue/PR on a repo would re-download the entire history, multiplying
  disk and network for no isolation benefit a worktree doesn't already give. Worktrees
  share one object store; rejected.
- **Work directly in the primary clone (no worktrees), switching branches per event** —
  breaks the moment two work items on the same repo are active at once (one checkout,
  one HEAD): event B would clobber event A's working tree. Worktrees exist precisely to
  give each concurrent line of work its own HEAD over shared objects; rejected.
- **Worktrees *inside* the repo dir** (`<root>/<host>/<owner>/<repo>/.worktrees/<slug>`) —
  keeps everything co-located but pollutes the primary clone's working tree (the worktree
  path shows as untracked unless added to `.git/info/exclude`) and muddies the clean
  `<host>/<owner>/<repo>` mirror the issue's layout implies. Quarantining under
  `<root>/.worktrees/…` keeps the checkout tree pristine and makes "remove all of this
  repo's runtime state" a single directory; chosen.
- **Delete the work item's local branch on cleanup too** — rejected as needlessly
  destructive: merged branches are usually deleted on the remote anyway, and keeping the
  local branch aids post-mortems while costing almost nothing. Only the worktree
  directory is removed.
- **Cloning via `gh repo clone`** (leaning on the poller's `gh` auth) — rejected to keep
  the workspace provider-neutral: plain `git clone` works for any host and defers auth to
  the operator's git credential setup (`gh auth setup-git` configures exactly that for
  GitHub). A GitHub-specific clone path would not generalise to the reserved `jira:` /
  enterprise futures.
- **A top-level `workspace` config block** (peer of `webhooks`/`polling`) instead of
  nesting under `routing` — rejected: cloning is dispatch behaviour, shared by the webhook
  receiver and the poller exactly like `runner`, `spawnWorkdir`, and `spawnOnUnmatched`,
  which all already live under `routing`. Nesting keeps one home for "how a spawned
  session is set up."
