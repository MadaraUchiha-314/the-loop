# Capability: webhook-triggers

> GitHub events (comments, reviews, CI results) reach the *right* running harness
> session on the user's own machine, programmatically.

## What it is

The local trigger path: an HMAC-verified webhook receiver plus event → session routing,
so a PR comment or workflow result resumes the Claude Code / Cursor session working
that item — the self-hosted equivalent of claude.ai/code PR watching.

## Current behaviour

- `the-loop gh-webhook start` SHALL run an HTTP receiver (default `127.0.0.1:8787`,
  path `/gh-webhook`) that verifies `X-Hub-Signature-256` HMAC using
  `THE_LOOP_GH_WEBHOOK_SECRET`, exposes `GET /health`, and logs events.
- Supported events SHALL include `issues`, `issue_comment`, `pull_request`,
  `pull_request_review`, `pull_request_review_comment`, `workflow_run`
  (`webhooks.ghWebhook.events`).
- WHEN routing is enabled (`webhooks.ghWebhook.routing.enabled`) THEN a verified event
  SHALL be matched to a registered session (`.the-loop/sessions/*.json`, managed by
  `the-loop sessions`) and the harness SHALL be resumed via its official CLI
  (`claude -p --resume` / `cursor-agent -p --resume`), serialized per session and
  parallel across sessions (`maxConcurrentDispatches`).
- WHEN no session matches THEN the router SHALL spawn a new session per
  `spawnOnUnmatched` (`never | always | labeled`, default `labeled` — opt-in via the
  `the-loop: auto-execute` label) using the configured prompt templates.
- The auto-execute label SHALL work on **PRs directly**: a labelled PR linked to no
  GitHub issue is routed as its own work item (`github:OWNER/REPO#<pr-number>`), so PRs
  stay monitorable when the ticketing system is not GitHub (Jira, …) — `work-on` adds
  the label to the PR it opens and registers the session against the PR's ref.
- WHEN `routing.runner` is `tmux` THEN spawned sessions SHALL be hosted as attachable
  interactive tmux sessions and events pasted into them — see
  [interactive-sessions](interactive-sessions.md).
- Duplicate deliveries SHALL be dropped via a dedup cache (`dedupCacheSize`).
- On the **poll** (pull) path the-loop drives its own retries, bounded by
  `polling.maxRetries` (default 3): WHEN a spawn or a comment forward does not succeed
  THEN it SHALL be retried on later cycles up to the budget (a failed event is no longer
  baselined as "processed" after one attempt), and WHEN the budget is exhausted THEN the
  poller SHALL log a terminal failure (`poll.spawn_failed` / `poll.comment_failed`,
  `will_retry=false`) and ignore that event on later polls until new activity re-arms it.
  A still-processing (in-flight) dispatch SHALL NOT be counted a failed attempt, and a
  **new** comment on a work item SHALL retrigger it with a fresh budget. The poller reads
  the async dispatch outcome via the dispatcher's durable delivery record
  (`Dispatcher.delivery_status`: done/inflight/unhandled) rather than assuming success at
  enqueue time. (The webhook path relies on GitHub redelivery, repaired for dead tmux
  sessions by the respawn above — see [interactive-sessions](interactive-sessions.md).)
- WHEN `routing.reactions.enabled` is on (default **off** — opt-in, it is the daemon's
  first write surface to GitHub) THEN the dispatcher SHALL acknowledge each event it
  processes with emoji reactions on the triggering entity: the `started` reaction
  (default 👀 `eyes`) when the event is dequeued for delivery/spawn, then `completed`
  (default 🎉 `hooray`) or `error` (default 😕 `confused`) from the dispatch outcome —
  on the triggering **comment** when the event carries one, else on the **issue/PR**
  itself. Shared by the webhook receiver and the poller; best-effort via the operator's
  own `gh` CLI (a reaction failure never affects the dispatch; a missing `gh`, a
  non-GitHub provider, or an event with no reactable target is a silent no-op — so
  work-item platforms without reactions degrade cleanly). GitHub's palette is fixed
  (`+1 -1 laugh confused heart hooray rocket eyes`; ✅/⁉️ don't exist), and each
  state's emoji is configurable (`""` skips a state). Outcomes are logged as
  `reaction.added` / `reaction.failed`.
- A comment/review the-loop itself posted (identified by an embedded marker, since it
  is posted under the operator's own credentials and is otherwise indistinguishable by
  author) SHALL be dropped before dispatch, so the-loop never resumes a session on its
  own reply (`the_loop.authz.is_self_authored`; same check in `the-loop poll`).
- All `webhooks.*` keys above live in the **CLI config** (`cli-config.yaml`, resolved
  via `--config`/env/cwd/home — see `cli/README.md`), independent of any repo's
  `.the-loop/harness-config.yaml` (the plugin config) — the daemon is not tied to a single repo
  and never reads a repo's plugin config for anything (decision-032).
  `routing.authorizedUsers` has no fallback: it must be set explicitly in the CLI
  config or the receiver fails closed (acts on no human-authored events).

## Design

[`docs/specs/issue-15/design.md`](../specs/issue-15/design.md) ·
[architecture § triggers](../architecture/architecture.md)

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-84 | Dispatch-lifecycle emoji reactions (`routing.reactions`, opt-in): 👀 started / 🎉 completed / 😕 error on the triggering comment or issue/PR, best-effort via `gh`, no-op where unsupported | [spec](../specs/issue-84/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/84) |
| issue-63 | `webhooks.*` moved out of the per-repo plugin config into an independent, repo-agnostic CLI config | [spec](../specs/issue-63/), [decision-032](../decisions/decision-032.md) |
| issue-64 | Added the self-reply marker guard (drops the-loop's own comments/reviews before dispatch, on both trigger paths, so it never resumes a session on its own reply) | [decision-031](../decisions/decision-031.md) |
| issue-80 | Bounded per-event retry policy on the poll path (`polling.maxRetries`, default 3): stop baselining failed spawns/comments as processed, retry each cycle, then log `poll.spawn_failed`/`poll.comment_failed` and ignore; a new comment retriggers | [spec](../specs/issue-80/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/80) |
| issue-32 | Added the tmux runner option for spawned sessions (dispatch via paste-injection; PR-close kills the tmux session) | [spec](../specs/issue-32/), [decision-021](../decisions/decision-021.md) |
| issue-15 | Added session registry, event→session routing and harness resume (receiver shipped in v0 gained `--route`) | [spec](../specs/issue-15/), [decision-016](../decisions/decision-016.md) |
| issue-1 | Shipped the HMAC-verified `gh-webhook` receiver (v0) | [spec](../specs/issue-1/), [decision-005](../decisions/decision-005.md) |
