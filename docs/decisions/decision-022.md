# Decision 022: poll GitHub as a pull ingress reusing the webhook dispatch stack

- **Status:** accepted
- **Date:** 2026-07-21
- **Deciders:** @MadaraUchiha-314 (issue #34)
- **Work item:** issue-34
- **Spec:** `docs/specs/issue-34/`

## Context

The webhook receiver (issue-15, decision-016) is push-based: GitHub must be able to
reach the host. When it can't — the harness runs behind NAT/a firewall, on a laptop, or
on infrastructure GitHub cannot call — events never arrive. Issue #34 asks for a
polling ingress that watches label-gated issues/PRs and spawns/routes tmux sessions
(issue-32), without spawning duplicate sessions for the same work item.

## Decision

Add `the-loop gh-poll start|stop`, a **pull ingress that reuses the entire webhook
routing/dispatch stack** rather than reimplementing any of it. Each cycle the poller
lists labelled issues/PRs via the user's `gh` CLI, synthesises the same `RoutedEvent`
shape the receiver produces, and hands it to the existing `Dispatcher`. Consequences of
that reuse:

- **One session per work item is inherited, not re-solved.** The session registry is the
  dedup authority; the poller emits a spawn ("presence") event only while a work item has
  no active session, so a live session is never doubled and a failed spawn simply retries
  next cycle.
- **Spawn vs. comment are separate synthetic events.** Presence events carry
  `labeled=True` (drive `spawnOnUnmatched`); comment events carry `labeled=False` (route
  to an existing session, never spawn). This keeps spawning registry-idempotent and
  comment forwarding exactly-once independently.
- **Dispatch config is reused from `webhooks.ghWebhook.routing`** (harness, runner
  `process`/`tmux`, spawn policy, templates, registry). `polling.ghPoll` adds only
  ingress knobs (interval, repos, monitor toggles, label, state/pid files); its `label`
  defaults to the routing `autoExecuteLabel` and `repos` falls back to `ticketing.github`.
- **`gh` is the GitHub client**, inheriting the user's existing auth — no token of our
  own, consistent with how the-loop shells out to `gh` elsewhere. `gh` is verified at
  start like tmux/ttyd.
- **A durable `PollState` owns cross-poll/restart dedup.** With no GitHub redelivery to
  lean on, the poller is the reliability layer: it baselines an item's comments on first
  sight (no replay) and forwards each new comment once, surviving restarts via
  `.the-loop/poll-state.json`.

Only GitHub is implemented now; `jira:` stays reserved in `WorkItemRef`. PR review
(inline) comment threads are a follow-up — conversation comments are covered.

## Consequences

- New package `cli/the_loop/poller/` (`GhClient`, `Poller`, `PollState`, `PollConfig`)
  and command `gh-poll`; new config `polling.ghPoll`; new git-ignored runtime state
  `poll-state.json` / `gh-poll.pid`. No changes to the webhook, dispatcher, registry,
  runner or adapters — polling is purely additive.
- Two ingresses (push webhook + pull poll) can even run together against one registry;
  the shared deduper/registry keep them from stepping on each other.
- Polling latency is bounded by `intervalSeconds` (vs. near-instant webhooks) and costs
  `gh` API calls per cycle — the accepted trade for reaching unreachable hosts.
- **Re-evaluation triggers:** adding Jira/other providers (generalise the ingress behind
  a provider seam); needing PR review-thread events (extend `GhClient`); `gh` gaining a
  first-class "since" cursor for comments (drop the state-file baseline for it).

## Alternatives considered

- **Reimplement spawning/dedup in the poller** — rejected: duplicates the tested
  registry/dispatcher invariants and risks a second, diverging "one session per item"
  code path.
- **Query GitHub via the MCP server / REST with our own token** — rejected: `gh` already
  carries the user's auth and enterprise config and is how the-loop talks to GitHub
  elsewhere; a wheel needs no extra credential story.
- **A shared cursor (max `updatedAt`) instead of per-comment ids** — rejected: second
  granularity and edits make it lossy; storing seen comment ids is exact and simple.
- **Long-poll / GitHub Actions push from CI** — rejected for this iteration: still needs
  an inbound path to the harness host, which is the very thing that is missing.
