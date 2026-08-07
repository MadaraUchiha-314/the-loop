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
- WHEN routing is enabled (`routing.enabled`) THEN a verified event
  SHALL be matched to a registered session (`.the-loop/sessions/*.json`, managed by
  `the-loop sessions`) and delivered into that session's tmux-hosted conversation
  (respawned first when it has died — see
  [interactive-sessions](interactive-sessions.md)), serialized per session and
  parallel across sessions (`maxConcurrentDispatches`).
- WHEN no session matches THEN the router SHALL spawn a new session per
  `spawnOnUnmatched` (`never | always | labeled`, default `labeled` — opt-in via the
  `the-loop: auto-execute` label) using the configured prompt templates — **and, since
  issue-106, only once an authorized user has explicitly started the work item** (see
  *Execution control* below).
- **Every rendered prompt states where the work item stands in the process graph**
  (issue-148). WHEN a prompt is rendered THEN the item's graph context — current node,
  phase, status, gate messages, the node's resume command and the
  `the-loop graph complete` instruction — SHALL be substituted into the
  `$graph_context` placeholder, resolved read-only **before** delivery or spawn. WHEN
  no context exists (fresh item, graph disabled, no spec directory, foreign checkout,
  or a resolution fault) THEN the placeholder SHALL render empty and the prompt SHALL
  otherwise be unchanged — resolution failure never costs a delivery. See
  [process-graph](process-graph.md) for the consult-first ordering at human gates.
- **Every rendered prompt states where the session takes its answers from** (issue-134,
  `routing.interaction.mode`, [decision-051](../decisions/decision-051.md)).
  - WHEN a prompt is rendered — an event prompt or a spawn prompt, either
    ingress — THEN the resolved mode's directive SHALL be substituted into the
    `$interaction_directive` placeholder, **above** the untrusted payload excerpt.
  - WHEN the mode is `work-item` (**the default**) THEN the directive SHALL tell the agent
    not to assume a human is watching its terminal: every question is a **comment on the work item or
    its PR**, marked as the-loop's own, after which the session waits for the reply to
    arrive as the next event — never blocking on an interactive prompt, never reading
    silence as consent. WHEN it is `cli` THEN the agent SHALL ask interactively **and**
    still record each decision's outcome on the work item.
  - IF the configured `promptTemplate`/`spawnPromptTemplate` does not declare the
    placeholder THEN the directive SHALL be **appended** to the rendered prompt: a custom
    template — every template written before issue-134 included — must not be able to
    strip the rule silently.
  - IF `interaction.mode` carries an undeclared value THEN it SHALL resolve to
    `work-item` with a warning, never to `cli`: a wrong `work-item` leaves a visible
    comment awaiting a reply, a wrong `cli` leaves a question in a void. The directive is
    a **constant per mode** — it interpolates nothing, so no payload text can reach it.
    Both modes are valid: `cli` means a human attaches to the session's tmux pane and
    answers there.
  - WHEN a session is spawned THEN `session.spawned` SHALL carry the resolved mode.
  - **Independently of the mode**, iteration on a generated artifact (`brainstorm.md`,
    `requirements.md`/`bugfix.md`, `design.md`, `tasks.md`) happens **only** in
    pull-request review on the PR carrying it — an invariant of the loop stated in the
    skill (`reference/collaboration.md`), restated in every rendered prompt.
- **Execution control: the label is necessary, not sufficient** (issue-106,
  `routing.control`). The label says *which* items may run and `authorizedUsers` says
  *who* may be an input; four declared keywords say *when*:
  `the-loop start`, `the-loop stop`, `the-loop pause`, `the-loop resume`
  (all configurable; issue-135 — the pre-issue-135 defaults were
  `the-loop:start-execution` and its three siblings).
  - WHEN an **authorized** user's comment on the work item or its PR carries one of
    them THEN the-loop SHALL execute that command and SHALL NOT forward the comment to
    the harness; keywords match as whole tokens, case-insensitively, and a comment
    carrying **two different** ones SHALL execute nothing and forward nothing
    (`control.ambiguous`). The control surface is **comments only** — a keyword in the
    work item's own body or a PR description is not a command.
  - **Creating** a work item that already carries the label arms it, exactly like
    labelling an existing one: it still waits for an explicit start.
  - WHEN `routing.control.requireStartCommand` is true (**the default**) THEN a labelled
    work item SHALL NOT spawn until the **start** command has been issued for it — on
    either ingress path, and under `spawnOnUnmatched: always` too ("always" widens which
    items may spawn, never who may start them). An **accepted** start is **durable**
    (it survives a restart, so a failed spawn retries without a new comment) and a
    later `stop`/`pause` disarms the item again. A start on a work item that is
    **not** armed is refused and leaves *nothing standing*: labelling it afterwards
    does not start it, because otherwise the label would still be the trigger, one
    event later — only a start issued while the item is armed starts it. The same
    asymmetry applies throughout: arming commands (`start`, `resume`) are remembered
    only when they act, disarming ones (`pause`, `stop`) always.
    `requireStartCommand: false` restores the pre-issue-106 label-alone behaviour.
  - **pause** SHALL suspend delivery for a work item's session while keeping its
    conversation (`session.paused`; suppressed events are recorded as
    `dispatch.dropped`/`session-paused` and are **not** replayed on **resume**);
    **stop** SHALL end the session through the same close path a merge takes (registry
    entry, harness process, workspace). A paused session still owns its work item, so
    nothing spawns a second one; a work item closing closes a paused session as readily
    as an active one.
  - Control parsing runs **after** the self-comment marker check and the
    `authorizedUsers` guard, so it never becomes a second, weaker way in: it adds a
    condition, and an empty `authorizedUsers` still fails closed. The command path
    then re-checks, **more strictly** than the ingress guard: a command requires a
    **named** login in the allowlist (`control.rejected` / `unauthorized-actor`
    otherwise), because the ingress guard intentionally allows an *actor-less*
    action — a CI event, or a comment whose author has been deleted — which must
    never be able to start or stop a session. The parser recognises the fixed
    configured vocabulary and yields one of four commands — no text from a comment
    reaches an argv, a path, a prompt or a work-item ref.
  - Every command is recorded (`control.command` with actor, source and effect;
    `control.rejected` when a work item is not armed), and the last command per work
    item is kept beside its session (`<registryDir>/control/`).
  - **A command already on the thread when the poller first sees the work item still
    counts** (issue-119). First sight baselines the existing thread as read — the
    spawned session reads it itself — but a control command is an instruction to
    the-loop that nothing has executed yet, so baselining it would silence it
    permanently (the item stays armed-but-never-started, `spawns: 0` every cycle).
    WHEN a first-sight thread carries **unambiguous** control commands from
    authorized users THEN those comments SHALL be held back from the baseline and
    forwarded on that same cycle, in thread order (so the last command wins), while
    every *other* comment SHALL still be baselined; the arming decision for the cycle
    is taken once, on that comment path, rather than a presence event being emitted in
    addition. The poller decides only *which comments are unresolved* — parsing,
    the named-authorized-actor re-check, execution and recording all stay in the
    dispatcher — so an unauthorized, self-authored (`<!-- the-loop:agent-comment -->`)
    or ambiguous keyword comment is baselined exactly as before, and
    `control.enabled: false` restores the plain first-sight baseline verbatim. A
    work item that **already has a control record** is skipped too: a first sight may
    *bootstrap* control state, never replay over state the-loop has already recorded.
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
- **That routing decision is recorded, not recomputed** (issue-172,
  [decision-064](../decisions/decision-064.md)). WHEN an event carrying a pull request is
  dispatched into a session registered against a **different** work item — delivered into an
  existing one, or spawning one — THEN the system SHALL persist the binding
  `PR → that work item` as a link record in the registry directory
  (`<registryDir>/<pr-slug>.link.json`, see [state on disk](../cli/state.md)), rewriting it
  only when the target actually changes.
  - WHEN a later event's ref has **no session record of its own** THEN the system SHALL
    resolve it through that stored binding, and deliver into the bound session. Resolution
    is ordered — the ref's own record first, the binding second — and **single-hop**: a
    binding whose target is itself bound is not followed.
  - Consequently a PR whose linkage GitHub no longer reports SHALL still reach the session
    that owns the work. Before issue-172 the binding existed only as a value re-derived from
    `gh` on every event, so **unlinking the PR in the Development panel, editing the closing
    keyword out of its body, a `gh` too old for `closingIssuesReferences`, or one transient
    GraphQL error** silently re-pointed routing at the PR itself — past a running session —
    and the event was dropped or answered with a duplicate session. Storing the decision is
    also what makes the recovery ladder (deliver → respawn resuming the recorded
    conversation → fresh session) reachable for a PR-keyed event at all.
  - The binding **adds** a resolution and never removes one: a session the derived linkage
    still finds is matched as before, so a PR deliberately re-linked to a different live
    work item delivers to both. Control commands (`the-loop start|stop|pause|resume` on a
    PR) resolve through the same order.
  - The binding SHALL NOT change **what a close ends**: a session matched through a binding
    is left open on a `pull_request` `closed` exactly as one matched through the derived
    linkage is (`session.kept_open`, issue-101 above). Closing a session SHALL NOT remove
    its bindings — a closed session is reopenable, and the binding is still true;
    `the-loop sessions reset` removes them, in both directions.
  - `session.linked` records each binding as it is made (and `session.unlinked` as it goes),
    so `the-loop events --type session.linked` answers "which PR is bound to what" without
    opening a file. A record that is missing, unreadable or hand-edited into something that
    is not a work-item ref reads as **no binding** — the pre-issue-172 behaviour, never an
    error into a dispatch.
- The auto-execute label SHALL work on **PRs directly**: a labelled PR linked to no
  GitHub issue is routed as its own work item (`github:OWNER/REPO#<pr-number>`), so PRs
  stay monitorable when the ticketing system is not GitHub (Jira, …) — `work-on` adds
  the label to the PR it opens and registers the session against the PR's ref.
- Spawned sessions SHALL be hosted as attachable
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
- **Stopping and restarting the poller SHALL have no observable effect** (issue-159): a
  poller that was stopped and started behaves as one that never stopped. Five rules make
  that true, on top of the durable per-item ledger.
  - **At most one poller per state root.** `poll start` SHALL take an exclusive advisory
    lock on its pidfile — `--once` included — and a second `start` against the same state
    SHALL refuse, name the holding pid and exit non-zero (`poller.blocked`) without
    touching the ledger. Two pollers sharing one ledger interleave read-modify-write over
    the same records and re-forward each other's comments, which is the sharpest form of a
    restart being visible. The lock is the pidfile itself, so "who is running" and "how do
    I signal them" cannot disagree; it is scoped per state root (two roots, two pollers),
    and the kernel releases it however the process dies — so a pidfile left by a `SIGKILL`
    is simply unlocked and needs no manual cleanup.
  - **`poll stop` SHALL be verified and blocking.** It signals a pid only when the lock
    proves a poller holds it (a stale pidfile is reported and removed, never signalled —
    under pid reuse the old behaviour sent `SIGTERM` to an unrelated process), and it
    returns only once the poller has actually exited, bounded by `--timeout` (default 30s);
    a poller that outlives the timeout is reported and the command exits non-zero.
  - **Progress SHALL be durable per work item.** Each item's record is written as soon as
    that item is done — including when processing it raised, so an attempt already spent
    cannot be spent twice — instead of at the end of the cycle. A hard kill then loses the
    item in flight rather than everything the cycle learned.
  - **A stop SHALL be honoured inside a cycle.** The poller finishes the work item in
    flight, persists it, and processes no further items or providers; the summary and
    `poll.cycle` carry `interrupted`. An interrupted cycle SHALL NOT run closure
    reconciliation — a partial listing is not evidence that the unlisted items ended, and
    reconciling on one would close live sessions (the same rule issue-94 applies to a
    *failed* listing).
  - **A shutdown SHALL return unspent retry budget.** `Dispatcher.stop` reports the
    deliveries it abandoned undelivered (`dispatch.abandoned`) and the poller un-counts the
    attempt each of them spent (`poll.attempts_released`), leaving the event **unresolved**
    rather than baselined. Without this, restarts accumulate toward `polling.maxRetries`
    and can permanently abandon a comment nothing ever tried to deliver.
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
  `--dangerously-skip-permissions`. The spawn directory is trusted under **every**
  `harnessTrust.scope` (the key that gates the dialog for a repo shipping
  `.claude/settings.json` grants has no ancestor walk); `scope` decides only whether a
  second entry additionally widens trust to the workspace root (`workspace-root`, the
  default, covering every checkout under it) or not (`directory`). Writes are
  non-destructive (named keys only, merged, atomic, skipped when already
  correct, refused on an unparseable file), and permission-neutral: the bypass
  disclaimer is accepted only when this harness's `harnessArgs` already ask for bypass
  mode. Best-effort — a failure warns, emits `workspace.trust_failed` and still spawns.
  Audited as `workspace.trusted`; `harnessTrust.enabled: false` opts out. See
  [interactive-sessions](interactive-sessions.md).
- A comment/review the-loop itself posted (identified by an embedded marker, since it
  is posted under the operator's own credentials and is otherwise indistinguishable by
  author) SHALL be dropped before dispatch, so the-loop never resumes a session on its
  own reply (`the_loop.authz.is_self_authored`; same check in `the-loop poll`).
- WHEN **any** producer writes a comment on the-loop's behalf — the spawned harness or
  the daemon itself (today: the interactive-session announcement) — THEN the body SHALL
  be stamped by `the_loop.authz.mark_self_authored`, the producer-side counterpart of
  that check: a visible attribution line plus the marker, idempotent, and applied only
  to text the-loop composed (never to payload-derived text). An unmarked daemon comment
  is authorized — it is posted with the operator's own credentials — so the marker is
  the only thing preventing it from being delivered into the session it describes
  (issue-104).
- Everything the CLI **generates** lives under one configured root (`state.root`,
  default `.the-loop`), organised by whether it travels between machines (issue-128,
  decision-046): one **portable** record per work item at `<root>/portable/<slug>.json`
  (its `control` section — what an authorized user armed — and its `poll` section — which
  comments have been seen), the machine-**local** session registry under `<root>/local/`,
  the event log under `<root>/logs/`, the receiver pidfile at `<root>/gh-webhook.pid`.
  The root supplies **defaults only** for the local paths — an explicitly configured
  `registryDir`/`eventLog.path`/`pidfile` is still used verbatim — while `portable/`
  always follows the root. Two writers share a work-item record, so a write SHALL replace
  only its own section (read-modify-write): a poll cycle must never erase a control
  command the other ingress recorded a moment earlier. Pre-issue-128 locations
  (`<root>/sessions/`, `<root>/sessions/control/`, `<root>/sessions/poll-state.json`, and
  the pre-issue-106 `.the-loop/poll-state.json`) SHALL still be READ once per work item
  and written forward, so an upgrade never re-baselines a watched thread nor forgets what
  was armed; nothing writes there any more.
- **Dispatch also drives the process graph** (issue-113, `routing.graph`, default on).
  A successful spawn enters the work item's start node — which is what runs the entry
  hooks that write the `loop:<phase>` label — and a successfully delivered event advances
  the graph one node boundary, carrying the event's comments to the gate's
  `classify-feedback`. The coupling lives in the dispatcher, so the poller and the
  receiver behave identically; it honours the same `control.requireStartCommand` gate the
  spawn path does; and it is best-effort — any failure is logged as `graph.link_failed`
  and the delivery still counts. **Where the specs are comes from the work item's own
  checkout** (`workflow.specDir`, default `docs/specs`), read only after the `origin`
  remote has proved the checkout is that repository's; `routing.graph.specDir` is an
  optional override for a checkout with no harness config, and setting it applies to every
  watched repository. A work item skipped for want of that directory is recorded as
  `graph.skipped` — the delivery still succeeds, so without the record an inert graph had
  no explanation (issue-123). See [process-graph](process-graph.md).
- The `webhooks.*` and `routing.*` keys above live in the **CLI config**
  (`cli-config.yaml`, resolved via `--config`/env/cwd/home — see `cli/README.md`),
  independent of any repo's
  `.the-loop/harness-config.yaml` — the daemon is not tied to a single repo, and **no
  repository configures the daemon** (decision-032, decision-044).
  `routing` is a **top-level** key, not part of `webhooks`: it configures what happens to
  an event once accepted, which is what the poller does with the very same values, so one
  declaration governs both ingresses (issue-142, decision-053). A config still nesting it
  under `webhooks.ghWebhook` is refused, naming the replacement and the upgrade command.
  `routing.authorizedUsers` has no fallback: it must be set explicitly in the CLI
  config or the receiver fails closed (acts on no human-authored events). The rule runs
  in one direction only: the graph coupling above *does* read a work item's own checkout
  for `workflow.phaseLabelPrefix`, `workflow.specDir` and `notifications`, after
  `_checkout_belongs_to` has proved via the checkout's `origin` remote that it is that
  repository's.

## Design

[`docs/specs/issue-15/design.md`](../specs/issue-15/design.md) ·
[architecture § triggers](../architecture/architecture.md)

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-172 | The PR → session binding stopped being recomputed from `gh` on every event (2026-08-07): dispatching a PR event into a linked work item's session records a durable link record beside the session record, and a ref with no session of its own resolves through it — so unlinking the PR, editing out the closing keyword, an older `gh` or one failed listing no longer strands a running session. Additive and single-hop; issue-93's derivation and issue-101's close rule are unchanged | [spec](../specs/issue-172/), [decision-064](../decisions/decision-064.md), [state](../cli/state.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/172) |
| issue-159 | Stopping and restarting the poller became invisible (2026-08-05): an exclusive lock on the pidfile makes two pollers on one ledger impossible (`--once` included), `poll stop` verifies the pid against that lock and waits for the process to exit, each work item's record is persisted as it finishes, a stop ends the cycle after the item in flight (and an interrupted cycle never reconciles closures), and a shutdown hands back the retry budget of dispatches it abandoned | [spec](../specs/issue-159/), [poll](../cli/commands/poll.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/159) |
| issue-156 | Process runner removed; tmux is the only runner (2026-08-05): dispatch always pastes into a tmux-hosted session, the `cli`-under-process interaction warning went with the runner choice, and the tmux-hosting requirement is unconditional | [spec](../specs/issue-156/), [interactive-sessions](interactive-sessions.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/156) |
| issue-142 | `routing` promoted out from under `webhooks.ghWebhook` to a top-level key: the block was never the receiver's — the poller reads it verbatim for dispatch and `the-loop sessions` reads it again — so its scope is now legible from the config's shape rather than from a comment. A relocation only: same options, same defaults, same behaviour, with the cross-command import replaced by one shared accessor and the old path refused rather than ignored (schema `0.4.0`) | [spec](../specs/issue-142/), [decision-053](../decisions/decision-053.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/142) |
| issue-136 | Pre-spawn trust reached the checkout it was for: `hasTrustDialogAccepted` is written on the exact spawn directory under every `scope` (the gate that decides whether the dialog appears for a repo shipping `.claude/settings.json` grants has no ancestor walk), so `scope` now only widens | [spec](../specs/issue-136/), [decision-052](../decisions/decision-052.md), [interactive-sessions](interactive-sessions.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/136) |
| issue-134 | A spawned session is told **where its answers come from** instead of guessing: `routing.interaction.mode` (`work-item` default, or `cli`) is rendered into every prompt through `$interaction_directive`, appended when a custom template omits the placeholder, and reported on `session.spawned`; artifact iteration in pull-request review became a stated invariant of the loop | [spec](../specs/issue-134/), [decision-051](../decisions/decision-051.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/134) |
| issue-135 | The default execution-control keywords changed shape from colon-joined (`the-loop:start-execution`) to a short command (`the-loop start`); the vocabulary, matching semantics and trust boundary from issue-106 are unchanged, and an operator's own explicit `keywords` override is unaffected | [spec](../specs/issue-135/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/135) |
| issue-123 | The graph coupling stopped sourcing a repo-scoped fact from the operator's machine: `routing.graph.specDir` became an optional override, so each watched repository's own `workflow.specDir` is honoured, and a spec-directory skip is recorded as `graph.skipped` rather than a debug line under a successful delivery | [spec](../specs/issue-123/), [decision-044](../decisions/decision-044.md), [process-graph](process-graph.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/123) |
| issue-119 | The poll path stopped swallowing a control command that predates first sight: unprocessed, authorized, unambiguous keyword comments are held back from the first-sight baseline and forwarded on the same cycle, so a labelled item whose start comment already existed actually starts | [spec](../specs/issue-119/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/119) |
| issue-128 | Generated state reorganised by portability: one `portable/<slug>.json` per work item (control + poll sections, read-modify-write) and machine-local session handles under `local/`, replacing three writer-shaped stores; `polling.stateFile` retired through the version-gated config migration; the pre-issue-128 locations read forward on upgrade | [spec](../specs/issue-128/), [decision-046](../decisions/decision-046.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/128) |
| issue-111 | The session registry treats `<root>/sessions/` as shared state: listings read only `<slug>.json` files it wrote, keeping the corrupt-entry warning meaningful | [spec](../specs/issue-111/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/111) |
| issue-106 | Execution control: four declared keywords (`the-loop:start-execution`, …) an **authorized** user steers with, the auto-execute label demoted to *necessary but not sufficient* (`routing.control.requireStartCommand`, default on), `paused` sessions, CLI parity with the same paper trail, and one `state.root` for everything the CLI generates | [spec](../specs/issue-106/), [decision-040](../decisions/decision-040.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/106) |
| issue-104 | The loop-prevention marker gained a producer-side helper (`mark_self_authored`) applied to the daemon's own comments — the session announcement no longer re-enters the session it announces | [spec](../specs/issue-104/), [decision-031](../decisions/decision-031.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/104) |
| issue-101 | A work item may be delivered by **several** PRs: a `pull_request` `closed` event now ends only the session registered against that PR itself, leaving a linked issue's session (and its checkout) running until the issue's own close | [spec](../specs/issue-101/), [decision-039](../decisions/decision-039.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/101) |
| issue-94 | A finished work item now ends its session on **both** ingress paths: the poller reconciles active sessions against each successful listing and closes the ones whose item is closed/merged upstream; the receiver treats `issues`/`closed` like `pull_request`/`closed` instead of delivering it into the conversation | [spec](../specs/issue-94/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/94) |
| issue-93 | An event on a PR resolves the PR's **linked issues first** (`closingIssuesReferences` + branch/keyword conventions, incl. PR conversation comments delivered as `issue_comment`), so PR activity reuses the linked issue's session instead of spawning a second one | [spec](../specs/issue-93/), [decision-036](../decisions/decision-036.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/93) |
| issue-90 | Pre-seed the harness config before spawning (`routing.harnessTrust`) so spawned sessions stop stalling on the workspace-trust dialog / bypass-permissions disclaimer | [spec](../specs/issue-90/), [decision-037](../decisions/decision-037.md) |
| issue-84 | Dispatch-lifecycle emoji reactions (`routing.reactions`, opt-in): 👀 started / 🎉 completed / 😕 error on the triggering comment or issue/PR, best-effort via `gh`, no-op where unsupported | [spec](../specs/issue-84/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/84) |
| issue-113 | Dispatch now drives the process graph: a spawn enters the start node (so the phase labels finally get written) and a delivered event advances it with the comments attached; `routing.graph` toggles it | [spec](../specs/issue-113/), [process-graph](process-graph.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/113) |
| issue-63 | `webhooks.*` moved out of the per-repo plugin config into an independent, repo-agnostic CLI config | [spec](../specs/issue-63/), [decision-032](../decisions/decision-032.md) |
| issue-64 | Added the self-reply marker guard (drops the-loop's own comments/reviews before dispatch, on both trigger paths, so it never resumes a session on its own reply) | [decision-031](../decisions/decision-031.md) |
| issue-80 | Bounded per-event retry policy on the poll path (`polling.maxRetries`, default 3): stop baselining failed spawns/comments as processed, retry each cycle, then log `poll.spawn_failed`/`poll.comment_failed` and ignore; a new comment retriggers | [spec](../specs/issue-80/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/80) |
| issue-32 | Added the tmux runner option for spawned sessions (dispatch via paste-injection; PR-close kills the tmux session) | [spec](../specs/issue-32/), [decision-021](../decisions/decision-021.md) |
| issue-15 | Added session registry, event→session routing and harness resume (receiver shipped in v0 gained `--route`) | [spec](../specs/issue-15/), [decision-016](../decisions/decision-016.md) |
| issue-1 | Shipped the HMAC-verified `gh-webhook` receiver (v0) | [spec](../specs/issue-1/), [decision-005](../decisions/decision-005.md) |
