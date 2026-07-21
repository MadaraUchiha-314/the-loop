# Decision 022: poll as a provider-agnostic pull ingress reusing the webhook dispatch stack

- **Status:** accepted
- **Date:** 2026-07-21
- **Deciders:** @MadaraUchiha-314 (issue #34, PR #45 review)
- **Work item:** issue-34
- **Spec:** `docs/specs/issue-34/`

## Context

The webhook receiver (issue-15, decision-016) is push-based: GitHub must be able to
reach the host. When it can't — the harness runs behind NAT/a firewall, on a laptop, or
on infrastructure GitHub cannot call — events never arrive. Issue #34 asks for a
polling ingress that watches label-gated issues/PRs and spawns/routes tmux sessions
(issue-32), without spawning duplicate sessions for the same work item.

PR #45 review sharpened the shape: *"we are indexing too much in GitHub being the only
source of work-item dispatch — make the config and other systems agnostic of GitHub;
the only way the system interfaces with GitHub is through config."*

## Decision

Add `the-loop poll start|stop`, a **provider-agnostic pull ingress that reuses the entire
webhook routing/dispatch stack** rather than reimplementing any of it. A `PollProvider`
seam abstracts discovery + event construction; a `polling.sources` config entry selects a
provider by name (GitHub ships as `GitHubPollProvider`), and the poller core, CLI, session
registry, dedup state and run loop carry **no** provider-specific vocabulary. Each cycle a
provider lists its labelled work items, synthesises the same `RoutedEvent` shape the
receiver produces, and the poller hands it to the existing `Dispatcher`. Consequences:

- **One session per work item is inherited, not re-solved.** The session registry is the
  dedup authority; the poller emits a spawn ("presence") event only while a work item has
  no active session, so a live session is never doubled and a failed spawn simply retries
  next cycle.
- **Spawn vs. comment are separate synthetic events.** Presence events carry
  `labeled=True` (drive `spawnOnUnmatched`); comment events carry `labeled=False` (route
  to an existing session, never spawn). This keeps spawning registry-idempotent and
  comment forwarding exactly-once independently.
- **Provider seam keeps the core agnostic.** A `PollProvider` (in `poller/base.py`) owns
  discovery + event construction; the poller core speaks only `WorkItem`/`Comment` and
  the shared `RoutedEvent`. `GitHubPollProvider` (`poller/github.py`) is the *only*
  GitHub-aware code. A `polling.sources` entry's `provider` name selects the class via a
  registry; a new provider (e.g. Jira) drops in with zero core changes.
- **Config is provider-agnostic.** `polling` holds `intervalSeconds`, `stateFile` and a
  `sources` list; each source names a `provider` plus that provider's own keys (a GitHub
  source: `repos`, `monitor`, `label`, `ghBinary`). The CLI (`the-loop poll`) exposes
  only run-loop flags — no provider knobs. GitHub is interfaced with *only* through a
  configured source.
- **Dispatch config is reused from `webhooks.ghWebhook.routing`** (harness, runner
  `process`/`tmux`, spawn policy, templates, registry). A source's `label` defaults to the
  routing `autoExecuteLabel`; a GitHub source's `repos` falls back to `ticketing.github`.
- **`gh` is the GitHub provider's client**, inheriting the user's existing auth — no token
  of our own, consistent with how the-loop shells out to `gh` elsewhere. `gh` is verified
  at start (per-provider `check_dependencies`) like tmux/ttyd.
- **A durable `PollState` owns cross-poll/restart dedup.** With no webhook redelivery to
  lean on, the poller is the reliability layer: it baselines an item's comments on first
  sight (no replay) and forwards each new comment once, surviving restarts via
  `.the-loop/poll-state.json`.
- **The `polling` config hot-reloads** (PR #45 review) at one-poll-cycle granularity: a
  `Reloader` content-hashes `.the-loop/config.yaml` and rebuilds the provider/interval
  plan on change — no restart to add/remove sources or retune the interval. A bad edit is
  logged and the previous plan is kept. Only `polling` reloads; the dispatcher/routing
  (worker threads, in-memory dedup) stays established at start.

Only the GitHub provider is implemented now; `jira:` stays reserved in `WorkItemRef` and
the seam. PR review (inline) comment threads are a follow-up — conversation comments are
covered.

## Consequences

- New package `cli/the_loop/poller/`: `base.py` (the `PollProvider` seam —
  `WorkItem`/`Comment` plus the registry), `github.py`
  (`GhClient`/`GitHubPollProvider`), and `poller.py` (the agnostic
  `Poller`/`PollState`/`PollConfig`). Plus command `poll`; new provider-agnostic config
  `polling.sources`; new git-ignored runtime state `poll-state.json` / `poll.pid`. No
  changes to the webhook, dispatcher, registry, runner or adapters — polling is additive.
- Two ingresses (push webhook + pull poll) can even run together against one registry;
  the shared deduper/registry keep them from stepping on each other.
- Polling latency is bounded by `intervalSeconds` (vs. near-instant webhooks) and costs
  provider API calls per cycle — the accepted trade for reaching unreachable hosts.
- **Re-evaluation triggers:** adding Jira/other providers (implement `PollProvider`,
  register it); needing PR review-thread events (extend the GitHub provider); a provider
  API gaining a first-class "since" cursor for comments (drop the state-file baseline for
  that provider).

## Alternatives considered

- **Hard-wire GitHub into the poller/config** — rejected on the PR #45 review: it indexes
  the whole dispatch story on one provider; the seam keeps GitHub reachable only through
  config and admits Jira/others later.
- **Reimplement spawning/dedup in the poller** — rejected: duplicates the tested
  registry/dispatcher invariants and risks a second, diverging "one session per item"
  code path.
- **Generalise the webhook router/dispatcher too (full-stack agnostic)** — deferred:
  reopens merged issue-15 code and balloons this PR; the shared `RoutedEvent`/registry
  are already provider-keyed, so the provider builds them and the downstream stays as-is.
- **Query GitHub via the MCP server / REST with our own token** — rejected: `gh` already
  carries the user's auth and enterprise config and is how the-loop talks to GitHub
  elsewhere; a wheel needs no extra credential story.
- **A shared cursor (max `updatedAt`) instead of per-comment ids** — rejected: second
  granularity and edits make it lossy; storing seen comment ids is exact and simple.
- **Long-poll / GitHub Actions push from CI** — rejected for this iteration: still needs
  an inbound path to the harness host, which is the very thing that is missing.
