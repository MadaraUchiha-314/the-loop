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
- WHEN `webhooks.ghWebhook.events` is omitted or empty THEN the receiver SHALL
  accept the-loop's **default event set** — `issues`, `issue_comment`,
  `pull_request`, `pull_request_review`, `pull_request_review_comment`,
  `workflow_run`, `check_run`, `check_suite`, `status`, i.e. every event it can map
  to a work item. An explicit list narrows it, and WHEN that list omits `issues` or
  `pull_request` THEN the receiver SHALL **warn at startup and on hot reload**: a
  work item that ends would never be seen, so its session (and tmux session) would
  leak. A warning, not an error — narrowing is the operator's call.
- WHEN routing is enabled (`webhooks.ghWebhook.routing.enabled`) THEN a verified event
  SHALL be matched to a registered session (`.the-loop/sessions/*.json`, managed by
  `the-loop sessions`) and the harness SHALL be resumed via its official CLI
  (`claude -p --resume` / `cursor-agent -p --resume`), serialized per session and
  parallel across sessions (`maxConcurrentDispatches`).
- WHEN no session matches THEN the router SHALL spawn a new session per
  `spawnOnUnmatched` (`never | always | labeled`, default `labeled` — opt-in via the
  `the-loop: auto-execute` label) using the configured prompt templates.
- **An event on a PR resolves the PR's linked issue(s) first.** WHEN an event concerns a
  pull request — `pull_request*`, **or** an `issues`/`issue_comment` event whose `issue`
  carries a `pull_request` key (GitHub's shape for a **PR conversation comment**) — THEN
  the router SHALL emit the issue(s) the PR is linked to **before** the PR's own number.
  Linked issues come from three sources, most authoritative first: GitHub's own
  `closingIssuesReferences` (the Development panel), the `issue-<n>` head-branch
  convention, and closing keywords in the PR body in every form GitHub accepts
  (`Closes #N`, `Fixes: #N`, `Closes OWNER/REPO#N`, `GH-N`, a full issue URL); a
  qualified reference naming a **different** repository SHALL be ignored. Consequently a
  PR comment/review/CI result SHALL be delivered into the **existing session for the
  linked issue** (reusing its tmux session) rather than spawning a second one, and WHEN
  nothing matches and the spawn policy allows it THEN the session SHALL be spawned
  against the **issue's** ref, not the PR's (issue-93, decision-036).
- The auto-execute label SHALL work on **PRs directly**: a labelled PR linked to no
  GitHub issue is routed as its own work item (`github:OWNER/REPO#<pr-number>`), so PRs
  stay monitorable when the ticketing system is not GitHub (Jira, …) — `work-on` adds
  the label to the PR it opens and registers the session against the PR's ref.
- WHEN `routing.runner` is `tmux` THEN spawned sessions SHALL be hosted as attachable
  interactive tmux sessions and events pasted into them — see
  [interactive-sessions](interactive-sessions.md).
- WHEN a work item **ends** — an `issues` event with action `closed`, or a
  `pull_request` `closed` (merged or not) — THEN its matched session(s) SHALL be
  **auto-closed** rather than resumed: registry entry closed, tmux session handled per
  `routing.tmux` (see [interactive-sessions](interactive-sessions.md)), workspace
  cleaned, `session.autoclosed` recording the reason (`issue-closed` | `pr-merged` |
  `pr-closed`). A close event SHALL never spawn a session, whatever `spawnOnUnmatched`
  says, and SHALL never be rendered into a harness prompt. Because it is a lifecycle
  signal that carries no free-form text and can only end the-loop's *own* session, it
  bypasses the authorized-actor guard (as PR-close always has) — narrowly: only the
  `closed` action.
- **One work item may be delivered by several PRs, and only the object that closed is
  ended.** WHEN a `pull_request` `closed` event is dispatched THEN the system SHALL
  auto-close only the session registered against **that PR's own ref**, and SHALL leave
  a session registered against an issue the PR is merely *linked* to **active**
  (logged as `session.kept_open`) — a spec PR, a stacked series or a follow-up fix all
  deliver one work item, so one of them merging is not the item ending. Consequently
  the work item's **checkout is not removed** while it is open, and the item's session
  ends on its **own** close: the `issues` `closed` event, or the poll path's closure
  reconciliation. The decision is made from the event payload alone (no API call, no
  credentials); a payload that names no closing number closes nothing. The operational
  consequence: a PR merged **without** closing its ticket leaves the session active
  until the ticket closes (`the-loop sessions close` is the manual escape hatch)
  — issue-101, decision-039.
- On the **poll** path the same closure is discovered by reconciliation, since a poll
  listing only ever carries *open* items: after each **successful** listing the poller
  checks every active session that source owns whose item is no longer listed, asks the
  provider whether it really ended (`poll.closure_detected`), and closes it through the
  dispatcher's identical close path. It never closes on doubt — a failed listing skips
  reconciliation, and an unanswerable state query leaves the session running for a later
  cycle — and forgetting the item's poll state means a **reopened** work item is
  first-sight again and spawns afresh. The closure query lives behind the provider
  contract (`owns`/`closure`/`closure_event`), so a provider that does not implement it
  is simply never reconciled (issue-94).
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
- On the poll path the linked issues of a labelled PR SHALL be read from GitHub inside the
  PR listing the poller already performs (`gh pr list --json …,closingIssuesReferences` —
  no extra API round-trip per cycle), and WHEN the installed `gh` predates that field THEN
  the poller SHALL warn once and fall back to the head-branch / closing-keyword
  conventions rather than failing the cycle.
- WHEN `routing.reactions.enabled` is on (default **on** — owner decision at PR #85
  review; `enabled: false` opts out of the daemon's one write surface to GitHub) THEN
  the dispatcher SHALL acknowledge each event it
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
- WHEN the dispatcher spawns (or respawns) a session THEN it SHALL first pre-seed the
  harness's own user config for that session's working directory
  (`routing.harnessTrust`, default **on**), so an unattended session cannot stall on
  Claude Code's workspace-trust dialog or its bypass-permissions disclaimer — neither
  of which is a permission rule, hence neither is silenced by
  `--dangerously-skip-permissions`. Scoped by `harnessTrust.scope` — the workspace
  root by default (one entry covering every checkout under it) or the exact spawn
  directory — non-destructive (named keys only, merged, atomic, skipped when already
  correct, refused on an unparseable file), and permission-neutral: the bypass
  disclaimer is accepted only when this harness's `harnessArgs` already ask for bypass
  mode. Best-effort — a failure warns, emits `workspace.trust_failed` and still spawns.
  Audited as `workspace.trusted`; `harnessTrust.enabled: false` opts out. See
  [interactive-sessions](interactive-sessions.md).
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
| issue-101 | A work item may be delivered by **several** PRs: a `pull_request` `closed` event now ends only the session registered against that PR itself, leaving a linked issue's session (and its checkout) running until the issue's own close | [spec](../specs/issue-101/), [decision-039](../decisions/decision-039.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/101) |
| issue-94 | A finished work item now ends its session on **both** ingress paths: the poller reconciles active sessions against each successful listing and closes the ones whose item is closed/merged upstream; the receiver treats `issues`/`closed` like `pull_request`/`closed` instead of delivering it into the conversation | [spec](../specs/issue-94/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/94) |
| issue-93 | An event on a PR resolves the PR's **linked issues first** (`closingIssuesReferences` + branch/keyword conventions, incl. PR conversation comments delivered as `issue_comment`), so PR activity reuses the linked issue's session instead of spawning a second one | [spec](../specs/issue-93/), [decision-036](../decisions/decision-036.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/93) |
| issue-90 | Pre-seed the harness config before spawning (`routing.harnessTrust`) so spawned sessions stop stalling on the workspace-trust dialog / bypass-permissions disclaimer | [spec](../specs/issue-90/), [decision-037](../decisions/decision-037.md) |
| issue-84 | Dispatch-lifecycle emoji reactions (`routing.reactions`, opt-in): 👀 started / 🎉 completed / 😕 error on the triggering comment or issue/PR, best-effort via `gh`, no-op where unsupported | [spec](../specs/issue-84/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/84) |
| issue-63 | `webhooks.*` moved out of the per-repo plugin config into an independent, repo-agnostic CLI config | [spec](../specs/issue-63/), [decision-032](../decisions/decision-032.md) |
| issue-64 | Added the self-reply marker guard (drops the-loop's own comments/reviews before dispatch, on both trigger paths, so it never resumes a session on its own reply) | [decision-031](../decisions/decision-031.md) |
| issue-80 | Bounded per-event retry policy on the poll path (`polling.maxRetries`, default 3): stop baselining failed spawns/comments as processed, retry each cycle, then log `poll.spawn_failed`/`poll.comment_failed` and ignore; a new comment retriggers | [spec](../specs/issue-80/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/80) |
| issue-32 | Added the tmux runner option for spawned sessions (dispatch via paste-injection; PR-close kills the tmux session) | [spec](../specs/issue-32/), [decision-021](../decisions/decision-021.md) |
| issue-15 | Added session registry, event→session routing and harness resume (receiver shipped in v0 gained `--route`) | [spec](../specs/issue-15/), [decision-016](../decisions/decision-016.md) |
| issue-1 | Shipped the HMAC-verified `gh-webhook` receiver (v0) | [spec](../specs/issue-1/), [decision-005](../decisions/decision-005.md) |
