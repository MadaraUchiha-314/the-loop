# Capability: webhook-triggers

> GitHub events (comments, reviews, CI results) reach the *right* running harness
> session on the user's own machine, programmatically.

## What it is

The local trigger path: an HMAC-verified webhook receiver plus event → session routing,
so a PR comment or workflow result resumes the Claude Code / Cursor session working
that item — the self-hosted equivalent of claude.ai/code PR watching.

## Current behaviour

- The receiver (started by `the-loop start` per `webhooks.ghWebhook.enabled`, or in
  the foreground by `python -m the_loop.daemon_entry gh-webhook`) SHALL run an HTTP
  receiver (default `127.0.0.1:8787`,
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
- **A forwarded event carries the instruction, not GitHub's metadata** (issue-243,
  [decision-086](../decisions/decision-086.md)). The `$payload_excerpt` block is a
  **field allow-list per container**, not a subset of the raw payload — the same function
  for both ingresses, so a comment reads identically whether it was pushed or polled.

  | Event | What the excerpt carries |
  |---|---|
  | `issue_comment` | the comment's `body`, `html_url`, `author` |
  | `pull_request_review_comment` | the same, preceded by `path` and `line` |
  | `pull_request_review` | `state`, `body`, `html_url`, `author` |
  | `issues` / `pull_request` | the acting `actor`, the entity's `number`, `title`, `state`, `html_url` (plus `draft`/`merged` for a PR), and the `label` name when the action is `labeled`/`unlabeled` |
  | `workflow_run` / `check_run` / `check_suite` | `name` where the object has one, `status`, `conclusion`, `head_branch`, the URLs, and a check run's own `output` title and summary |
  | `status` | `state`, `context`, `description`, `target_url` |

  - WHEN a comment event is rendered THEN the excerpt SHALL carry **no** `sender` or
    `user` object, no `issue` object, and no `api.github.com` URL: an author is a bare
    login, and the comment's own URL already names the issue or pull request it lives on.
  - WHEN a lifecycle event is rendered THEN the excerpt SHALL carry the entity's **title
    but not its body**: a spawned session's first act is `/the-loop:work-on <ref>`, which
    reads the ticket itself, and the body was both the largest string in the excerpt and
    the largest attacker-controlled one — travelling with *every* event about that item,
    not only the spawn.
  - WHEN free text (`body`, `description`, a check run's `summary`) is longer than the
    per-field cap THEN **that field alone** SHALL be truncated with a visible marker, the
    rendered excerpt SHALL remain parseable JSON, and the object's `html_url` — and an
    inline comment's `path`/`line`, which are emitted first — SHALL survive it.
  - IF an event has no rule of its own (an operator's extra `webhooks.ghWebhook.events`
    entry) THEN it SHALL be distilled over whichever known containers it carries, and
    SHALL never fall back to the raw payload. IF nothing is recognised THEN the excerpt
    SHALL render `{}` and the prompt SHALL otherwise be delivered unchanged: an
    unrecognised shape costs the session context, never the delivery of an event an
    authorized human already caused.
  - The excerpt is **prompt text only**. Routing, `authorizedUsers`, the self-comment
    marker check, control-keyword parsing, reaction targeting and head-ref resolution all
    read the **full** payload and are unaffected by what it omits.
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
    its PR**, asked by running **`the-loop ask`** (issue-208 — the verb posts the
    comment, stamps the loop-prevention marker centrally and records the wait as a
    `session.awaiting_input` event; manual `gh` + marker is the stated fallback when
    the CLI is unavailable), after which the session waits for the reply to
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
  *who* may be an input; the declared keywords say *when*:
  `the-loop start`, `the-loop stop`, `the-loop pause`, `the-loop resume`, plus
  `the-loop contribute` (issue-185) — a spawn-arming sibling of `start` that also
  selects the **contribution loop** for the item's outer walk: the-loop joining an
  existing, in-progress issue or PR as a contributor, which then refuses to begin
  until an authorized user has stated a goal and success criteria
  (see [process-graph](process-graph.md)) — `the-loop do` (issue-225), the same
  spawn-arming sibling one loop over: it selects the **ad-hoc loop**, a tactical task
  that runs no PDLC process at all, and typing the word IS the recorded declaration
  that the item runs without one — and `the-loop cleanup` (issue-186), the
  other end of the life cycle. All configurable (issue-135 — the
  pre-issue-135 defaults were `the-loop:start-execution` and its three siblings).
  - WHEN an **authorized** user's comment on the work item or its PR carries one of
    them THEN the-loop SHALL execute that command and SHALL NOT forward the comment to
    the harness; keywords match as whole tokens, case-insensitively, and a comment
    carrying **two different** ones SHALL execute nothing and forward nothing
    (`control.ambiguous`). The control surface is **comments only** — a keyword in the
    work item's own body or a PR description is not a command.
  - A command comment is executed instead of forwarded, so it can never reach a gate as
    an event — which is why a **spawning** one is handed to the graph with the spawn
    (issue-199): WHEN a spawn enters a start node whose actor is `human` THEN that
    node's exit chain SHALL be evaluated once with the spawning comment attached, so
    `the-loop contribute` carrying a goal reaches `phase-selection` on its own. An agent
    start node and a respawn SHALL evaluate nothing.
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
    only when they act, disarming ones (`pause`, `stop`, `cleanup`) always.
    `requireStartCommand: false` restores the pre-issue-106 label-alone behaviour.
  - **cleanup** SHALL release the work item's **local** resources — every endpoint's
    tmux session, the workspace checkout, the machine-local session record — and keep
    the portable record and everything remote (issue-186; the mechanics are in
    [interactive-sessions](interactive-sessions.md)). It is the one control command that
    **destroys**, so it carries the same named-actor re-check the others do and runs
    with or without a live session: the retroactive case — a checkout still on disk long
    after its session went — is what the command is for. It disarms the item like a stop.
  - WHEN a work item closes AND the close event names an **authorized** actor THEN the
    cleanup above SHALL run after the session is auto-closed; WHEN it names none, or an
    unauthorized one, THEN the cleanup SHALL be **deferred** (`cleanup.deferred`) and
    the session merely closed. A close action is not obliged to say who performed it,
    and an unattributable event must not destroy an operator's uncommitted work — the
    `cleanup` keyword from a named human is the remedy, which is why it exists.
    In practice this splits the two ingresses: a **webhook** closure carries `sender`,
    so it cleans up when that login is authorized, while a **polled** closure is
    reconstructed from the item's state and names no actor at all — so on a polling
    deployment every closure defers, and cleanup is always the keyword's job.
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
  (`Closes #N`, `Fixes: #N`, `Closes OWNER/REPO#N`, `GH-N`, a full issue URL). A
  **qualified** reference naming a different repository SHALL resolve to the work item in
  **that** repository (issue-183, [decision-069](../decisions/decision-069.md)) — a work
  item's contributions may span repositories, and the pull request delivering one of them
  lives where its code does while the ticket lives in the origin repository. The
  head-branch convention stays local: `issue-<n>` on a branch says nothing about a
  repository — and, since issue-269, nothing about **existence** either, which is why a ref
  resting on it alone is checked before anything acts on it (below). This widens which work
  item an **arrived** event names, and nothing else:
  the ingress (the operator's receiver and poll sources) and the arming gate
  (`the-loop start`) are unchanged. Consequently a
  PR comment/review/CI result SHALL be delivered into the **existing session for the
  linked issue** (reusing its tmux session) rather than spawning a second one, and WHEN
  nothing matches and the spawn policy allows it THEN the session SHALL be spawned
  against the **issue's** ref, not the PR's (issue-93, decision-036).
- **A work item a branch name invented is dropped before anything acts on it**
  (issue-269, [decision-095](../decisions/decision-095.md)). Of the three linkage sources
  above, the branch convention is the only one that supplies a repository the event never
  stated — so it is the only one that can name a work item nobody created. WHEN an event
  yields a work-item ref **only** through that convention (a pull request's head branch, or
  a CI event's `head_branch` / `branches[].name`) AND no live session record on this machine
  owns any of the event's refs THEN the system SHALL ask the provider whether the ref exists
  (`gh api repos/<owner>/<repo>/issues/<n>`, a ref on GitHub Enterprise asked of its own
  host) before that ref becomes a spawn target or a control-command target; WHEN the answer
  is a definitive HTTP 404 THEN the ref SHALL be removed from the event's work items
  (`routing.linkage_dropped`) and the event routed on what remains; and WHEN every one of an
  event's work items is removed this way THEN the event SHALL be dropped
  (`dispatch.dropped`, reason `work-item-not-found`) **without** releasing its delivery id,
  because a work item that does not exist is a permanent condition. Every other answer — no
  `gh` on PATH, a timeout, a 403, a 5xx, unusable coordinates, a non-GitHub provider — SHALL
  keep the ref and route exactly as before: an unavailable check is not evidence of absence.
  A ref GitHub itself reported (`closingIssuesReferences`) or one a closing keyword named is
  **never** questioned — those state their repository, and issue-183's cross-repository
  routing acquires no network dependency. Answers are cached per ref (bounded, in-process),
  so a repeatedly-commented pull request costs one call.
  - **The record answers before GitHub is asked, and before a list index is trusted.** WHEN
    an event names a work item this machine holds a live session record for — through its
    own ref, or through a durable PR → work-item binding — THEN that record's work item
    SHALL be the target of a control command, of the `requireStartCommand` test and of an
    unmatched event's spawn, whatever order the refs were emitted in, and the existence
    check SHALL NOT be consulted at all. Before issue-269 those three read
    `work_items[0]` — which, with a branch-invented ref present, is the ghost: the
    operator's `the-loop start` was recorded against a ref that 404s, and a full session
    (clone, registry entry, tmux session) was spawned for it, without the spec chain that
    lives on the real work item.
  - **A polled pull-request comment is a pull-request event.** The poller synthesises a
    comment event over the pull request's own payload (key `pull_request`, head branch
    included) and renames it `issue_comment`; the router read only `payload["issue"]` for
    that name, so on the poll ingress **every** pull-request comment answered "this event
    carries no pull request" — no `session.pr_linked` binding was written from a comment,
    and no pull-request endpoint was ever chosen for one. Both now happen there exactly as
    they do for a webhook (issue-269). No real webhook carries a `pull_request` beside an
    `issue_comment`, so that path is unchanged.
  - **A 404 on the work item after a spawn is reported, not obeyed.** WHEN the session
    announcement fails because the work item itself is not found THEN the system SHALL
    record `session.work_item_missing` at error level, naming the remedy, and SHALL
    remember the ref as missing so the next event naming it through a branch convention is
    dropped without a second call — and SHALL NOT end the session: a repository the
    operator's credential cannot see answers 404 for items that do exist, and killing a
    live agent (with its checkout and its uncommitted work) on an ambiguous signal is worse
    than the situation being reported.
- **That routing decision is recorded, not recomputed — and each PR is a session of its
  own** (issue-172, [decision-064](../decisions/decision-064.md)). WHEN an event carrying a
  pull request is dispatched to a work item's session — delivered into an existing one, or
  spawning one — THEN the PR SHALL be durably recorded on that work item's **single
  session record** (`pullRequests[]`, see [state on disk](../cli/state.md)), so which work
  item owns a PR's events is read from the record on later events and never re-derived
  from `gh`. Before issue-172 the binding was recomputed per event, so **unlinking the PR
  in the Development panel, editing the closing keyword out of its body, a `gh` too old
  for `closingIssuesReferences`, or one transient GraphQL error** silently re-pointed
  routing at the PR itself — past a running session — and the event was dropped or
  answered with a duplicate session.
  - **A session is given only with a working tree of its own** (issue-253,
    [decision-088](../decisions/decision-088.md) D2) — the invariant every mode below is
    subject to. WHEN a pull request endpoint would be spawned AND no checkout can be
    prepared for that pull request alone THEN no session SHALL be spawned, the event SHALL
    be delivered into the work item's session, and the refusal SHALL be recorded as
    `session.pr_session_declined` with a `reason` of `no-separate-checkout`,
    `workspace-failed` or `shared-worktree`. Before issue-253 an endpoint got a session of
    its own **in the work item's working tree**, so two harness conversations shared one
    branch with no lock and no owner: they interleaved commits, restarted each other's
    services and ran the same verification twice against a tree each was changing under
    the other.
  - **How many sessions a work item's pull requests get is the work item's choice**
    (issue-260, [decision-093](../decisions/decision-093.md)), made at `phase-selection`
    and frozen into its portable record; `routing.tmux.sessionPerPr` (issue-258,
    [decision-092](../decisions/decision-092.md)) is the **default** it is chosen against.
    WHEN routing a pull request's event THEN the system SHALL read that work item's frozen
    `graph.sessionPerPr` and SHALL fall back to the configured value when the record
    carries none or carries a value outside the vocabulary — so a work item started before
    the choice existed, and a hand-edited record, both route exactly as they do today. The
    three modes are unchanged:
    - WHEN it is `never` THEN every pull request's events SHALL be delivered into the work
      item's single session — the pre-issue-172 behaviour.
    - WHEN it is `cross-repository` (**the default**) THEN a pull request in **another**
      repository — a contribution this work item makes elsewhere (issue-183) — SHALL work
      in its **own** tmux session with its **own** harness conversation, and a pull request
      in the work item's **own** repository SHALL be delivered into the work item's
      session: that pull request is the work item's own delivery — its branch, its
      checkout, and under `outer-loop-on-pull-request` the very conversation the work
      item's session is already holding there.
    - WHEN it is `always` THEN every pull request delivering the work item SHALL be a
      candidate for its own session, its own repository included.
    - WHEN the configured value is neither a boolean nor one of those three names THEN the
      system SHALL resolve it to `cross-repository` and SHALL log the value it rejected;
      the legacy booleans SHALL resolve to `cross-repository` (`true`) and `never`
      (`false`), so a configuration written before issue-258 keeps its meaning.
    - WHEN the retry path asks whether a delivery was handled THEN it SHALL resolve the
      endpoint by the **same** per-work-item mode dispatch used, so a comment delivered
      into the work item's session under `never` is never re-forwarded as unhandled.
  - An endpoint's session SHALL run in a checkout of **that pull request's** repository,
    keyed on the pull request's own slug (`routing.workspace.root`), spawned lazily by the
    first event that needs it and announced like any other spawn. WHEN the pull request is
    in the work item's **own** repository THEN that checkout SHALL additionally hold the
    pull request's head branch, and SHALL be declined otherwise: under
    `workspace.strategy: worktree` the work item's own session already holds that branch,
    git cannot check one branch out into two worktrees of one clone, and the fallback tree
    would put the endpoint on the default branch instead of the pull request's code. In
    practice `always` is therefore served by `workspace.strategy: clone`.
  - Resolution is **additive**: a ref with its own record resolves to it, and only a ref
    with none is looked up across the live records' PR lists — so a recorded PR never
    suppresses a work item the derived linkage still finds, and a deliberate re-link
    delivers to both (loud, where the failure it replaces was silent). A PR whose
    endpoint is closed, or unspawnable, falls back to the work item's session — an event
    is never lost to endpoint bookkeeping.
  - WHEN the closed object of a `pull_request` `closed` event is a **recorded PR** of a
    still-open work item THEN that PR's endpoint SHALL be closed (its tmux session
    handled per the same retention rules as any close, `session.pr_closed`) and the work
    item's session left running (`session.kept_open`) — issue-101's several-PRs rule,
    now expressed in the model. Control commands on a PR resolve to its work item's
    record, so a `the-loop stop` commented on a PR whose linkage broke still stops the
    session that owns the work.
  - `session.pr_linked` records each PR as it is recorded and `session.pr_spawned` each
    endpoint spawn, so `the-loop events` answers "which PRs deliver what" without opening
    a file. An unreadable `pullRequests` entry reads as "that PR is unrecorded" — never
    an error into a dispatch, and never fatal to the work item's own session.
  - **Deliberately out of scope here:** a PR endpoint has no process graph. The graph
    stays keyed to the work item; the per-PR **inner-loop** graph the endpoint model
    enables is defined and built as its own work item (decision-064 § the direction this
    sets).
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
- **Both ingresses read the same three comment surfaces** (issue-246). GitHub files an
  instruction left on a pull request under one of three objects, and a work item's session
  SHALL receive all three whichever ingress is running:

  | Surface | GitHub object | Event delivered | Payload key |
  |---|---|---|---|
  | Conversation comment | `IssueComment` (`IC_`) | `issue_comment` | `comment` |
  | Review body | `PullRequestReview` (`PRR_`) | `pull_request_review` | `review` (incl. `state`) |
  | Inline review-thread comment | `PullRequestReviewComment` (`PRRC_`) | `pull_request_review_comment` | `comment`, **with `path` and `line`** |

  - WHEN a polled pull request carries a review or a review-thread comment THEN the poller
    SHALL forward it **exactly once** — deduped across cycles and restarts by its own node
    id, on the same ledger, retry budget and give-up accounting as a conversation comment.
    A review and the N inline comments it contains are **N+1 independent deliveries**,
    because each has its own id.
  - WHEN a review-thread comment is forwarded THEN its **file and line** SHALL travel with
    it (the line it was written against, when the diff has since moved past it): the anchor
    is part of the instruction. The diff hunk SHALL NOT be forwarded — the payload excerpt
    is capped, and a hunk can truncate the instruction it was meant to contextualise.
  - WHEN a review carries an **empty body**, or has not been submitted (`PENDING`), THEN
    nothing SHALL be forwarded for it. An approval with no words carries no instruction,
    and a draft review is not something its author has said. Whether the review **state**
    itself should mean anything is deliberately undecided: it is carried as context and
    nothing acts on it.
  - Every one of these SHALL pass the guards a conversation comment passes, in the same
    order and the same place: the self-comment marker first, then `authorizedUsers` judged
    by **that comment's own author**, then control parsing. No new credential, no new
    network path — the reads go through the operator's own `gh`.
  - WHEN the polled item is an **issue** THEN the requests SHALL be exactly the one the
    poller always made; the two extra reads are per **pull request** only.
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
  (`Dispatcher.delivery_status`: done/**settled**/inflight/unhandled) rather than assuming
  success at enqueue time. (The webhook path relies on GitHub redelivery, repaired for dead tmux
  sessions by the respawn above — see [interactive-sessions](interactive-sessions.md).)
- **An event refused on purpose is never replayed, and never counted as a pending
  delivery** (issue-270). Two things suppress delivery deliberately: a work item nobody has
  started (`requireStartCommand`) and a **paused** session. In both cases the event is
  dropped (`dispatch.dropped`, reason `awaiting-start` / `session-paused`), its delivery id
  is deliberately **kept** — releasing it would have GitHub redeliver, and the poller
  re-forward, every comment on every labelled item nobody has started — and **nothing is
  replayed when the item is later started or the session resumed**. What was said is not
  lost: it is on the thread, and the prompt a spawned session receives tells it to read that
  thread from the top, including what arrived before the start. WHEN such an event was
  forwarded by the **poll** path THEN the dispatcher SHALL record the delivery as *settled*
  and the poller SHALL resolve the comment — baselined in `seenComments`, no entry in
  `commentAttempts`, nothing counted against `maxRetries`, **no** `gaveUp` record (so no
  later version re-arms it into a late replay) and no abandonment notice — recording it once
  as `poll.comment_settled` with the reason. The same applies to a comment that **carried a
  control keyword**: it was executed, refused or found ambiguous by the-loop and was never a
  delivery at all, so a re-forward after a restart would have executed the command twice.
  Every *failure* path is unchanged: a failed dispatch still releases its delivery id and
  still spends a retry, and `spawn-policy`, `session-occupied`, `session-vanished` and
  `work-item-not-found` keep the accounting they had.
- **A comment the poller abandons SHALL be reported on the work item** (issue-240). WHEN
  the retry budget for a comment is exhausted THEN, after the give-up is recorded, the
  poller SHALL post one comment on that item — naming the abandoned comment, the number of
  attempts, and that it will not be retried — carrying the self-comment marker so it is
  never read back as human input (`poll.giveup_reported`). Until then the only signal was
  a 😕 reaction and a line in the local event log, so a human who told an agent to do
  something had no way to learn the agent was never told. The notice states the recovery:
  **post the instruction again** — a new comment id carries a full retry budget, and
  nothing the-loop stores needs editing. Posting is **best-effort in one direction only**:
  it MAY fail (no `gh`, a non-GitHub provider, an API error — `poll.giveup_report_failed`)
  and the give-up SHALL be recorded regardless; it SHALL NEVER cause a comment to be
  treated as delivered, and SHALL NEVER end a poll cycle. The notice is built from the
  comment's id, URL and attempt count only — **no text from the abandoned comment is
  echoed** into something the-loop posts with the operator's credentials.
- **Stopping and restarting the poller SHALL have no observable effect** (issue-159): a
  poller that was stopped and started behaves as one that never stopped. Five rules make
  that true, on top of the durable per-item ledger.
  - **At most one poller per state root.** The poller SHALL take an exclusive advisory
    lock on its pidfile — `--once` included — and a second start against the same state
    SHALL refuse, name the holding pid and exit non-zero (`poller.blocked`) without
    touching the ledger. Two pollers sharing one ledger interleave read-modify-write over
    the same records and re-forward each other's comments, which is the sharpest form of a
    restart being visible. The lock is the pidfile itself, so "who is running" and "how do
    I signal them" cannot disagree; it is scoped per state root (two roots, two pollers),
    and the kernel releases it however the process dies — so a pidfile left by a `SIGKILL`
    is simply unlocked and needs no manual cleanup.
  - **Stopping the poller (`the-loop stop`) SHALL be verified and blocking.** It signals
    a pid only when the lock proves a poller holds it (a stale pidfile is never
    signalled — under pid reuse the old behaviour sent `SIGTERM` to an unrelated
    process), and it returns only once the poller has actually exited, bounded by a
    timeout (default 30s); a poller that outlives the timeout is reported and the
    command exits non-zero.
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
  - **The poller SHALL be able to outlive the shell that started it** (issue-191,
    re-shaped by issue-228). `the-loop start` spawns it detached — its own session
    (`start_new_session`), output to `<state.root>/logs/poller.out` — and reports
    success only once the daemon holds its pidfile lock, so a poller that exits during
    startup is a reported failure, not a silent one; `the-loop status` reports liveness
    from the lock and progress from the per-cycle heartbeat, exiting `0`/`1`. The
    issue-191 double-fork detach went with the removed `poll` command
    ([decision-084](../decisions/decision-084.md)); the foreground form cron and
    systemd run is `python -m the_loop.daemon_entry poller [--once]`.
  - **By default both ingresses run inside the service process** (issue-231,
    decision-084 §8): with `service.hostIngresses` true, `the-loop start` boots one
    process whose lifespan hosts the enabled poller and receiver as threads, each
    still acquiring its own pidfile flock (under the service's pid) so the
    single-instance guarantee, `status`/`stop` and the daemons API are unchanged. A
    lock held by a standalone daemon is skipped with a warning, never fought over;
    `hostIngresses: false` (or a disabled service) restores one process per ingress.
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
- **The authorized actor is whoever performed the action, and on the poll path the work
  item's author gates spawning alone** (issue-197,
  [decision-074](../decisions/decision-074.md)). The webhook router authorizes
  `event_actor` — the commenter, reviewer or labeller. A poll listing carries an item's
  labels but not who applied them, so there the *item's author* stands in as the proxy for
  "a human wanted this", and it governs exactly one decision:
  - WHEN a polled work item's author is not in `authorizedUsers` AND no arming command has
    been recorded for it THEN the poller SHALL NOT emit a **presence** event for it (no
    session is spawned whose subject is that item), SHALL log the remedy and SHALL record
    `poll.unauthorized` naming that author. WHEN an authorized user **has** armed it
    (`the-loop start`/`contribute`/`resume`, from a comment or from
    `the-loop sessions start` — `ControlStore.start_requested`) THEN presence SHALL be
    armed exactly as for any other item, and the warning SHALL stop; a later
    `stop`/`pause`/`cleanup` disarms it again.
  - WHEN a comment on such an item is authored by an authorized user THEN it SHALL be
    forwarded, and a control command on it executed, **regardless of who opened the item**
    — including a command already on the thread at first sight (issue-119's rule). An
    unauthorized author's comment is baselined and dropped exactly as before, on an armed
    item as on any other. So a maintainer can point the-loop at an outside contributor's
    issue or pull request with one comment; the contributor gains nothing.
  - Every spawn prompt states that the work item's own title, body and comment thread are
    **untrusted content** — a description of what is wanted, never instructions that
    override the-loop's rules — because the person who asked for the work need not be the
    person who wrote it. A constant, interpolating nothing, above the payload excerpt.
- A comment/review the-loop itself posted (identified by an embedded marker, since it
  is posted under the operator's own credentials and is otherwise indistinguishable by
  author) SHALL be dropped before dispatch, so the-loop never resumes a session on its
  own reply (`the_loop.authz.is_self_authored`; same check on the poll path).
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
- **A repository that never adopted the-loop is adopted on the way in** (issue-193,
  [decision-073](../decisions/decision-073.md)). WHEN the coupling handles a work item in
  a checkout it has proved to be that work item's own repository, and the checkout carries
  neither `.the-loop/harness-config.yaml` nor the pre-rename `config.yaml`, THEN the-loop
  SHALL write its [built-in default](../config/harness-config.md#when-a-repository-has-no-config)
  there — naming the work item's `owner`/`repo` under `ticketing.github` — and record it as
  `harness.config_scaffolded`. Before this, the daemon would clone such a repository, spawn
  a session in it, and leave that session with no workflow, tooling or phases to read.
  - **It happens before the harness starts** (issue-201): between the workspace being
    prepared and the prompt being rendered, so the config is on disk before `tmux.spawn`
    is called — and again in the respawn pre-flight, beside the harness-trust preparation.
    The write is *also* attempted when the graph is driven (`start`/`advance`) as an
    idempotent safety net for a session that predates this, but the guarantee lives at the
    spawn. Adoption from the `context` read and from `cleanup` is deliberately excluded:
    the first is documented as mutating nothing, the second runs while the checkout is
    being released.
  - It happens **after** the ownership proof (a payload can never name a directory, only
    fail to match one) — which is why the pre-spawn path runs that proof itself rather
    than trusting the prepared `cwd`, since under the legacy `spawnWorkdir` setup that
    directory may be the operator's own checkout.
  - It happens **before** the spec-directory gate: a brand-new work item has no spec
    directory, yet its session is about to run in the checkout.
  - It happens **never for a contribution** — a repository the-loop was invited into as a
    guest keeps the-loop out of its history. An existing config of either name is never
    opened, so no inbound event can replace an operator's policy.
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
| issue-270 | A comment refused before the start stopped being filed as a delivery still in flight (2026-08-18): pre-start (and paused-session) events are suppressed on purpose and never replayed — the settled product decision — but the poll ledger recorded the refusal as `commentAttempts: 1` and left it there, so an operator could not tell "we are still trying" from "we decided not to", and after a restart the poller spent the rest of the budget, declared a terminal delivery failure, posted a notice on the ticket saying the comment never arrived after three attempts, and left a `gaveUp` record that the next CLI version re-armed — replaying the comment nobody asked to replay. A delivery the dispatcher is *finished* with is now recorded as **settled** (suppressed, or consumed as a control command) beside its dedup mark, and the poller resolves such a comment instead of counting it: baselined, never abandoned, one `poll.comment_settled` record naming the reason. The spawn prompt now tells the session to read the item's whole thread, which is where a refused comment still is | [spec](../specs/issue-270/), [decision-097](../decisions/decision-097.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/270) |
| issue-269 | A branch name stopped being able to invent a work item (2026-08-18): `issue-<n>` in a head branch resolved to a ref in the pull request's **own** repository and nothing ever checked that it existed, so in a multi-repository deployment (ticket in one repository, code in another) a ghost became `work_items[0]` — it absorbed the operator's `the-loop start` and had a whole session spawned against a ref that 404s, without the spec chain that lives on the real work item. A ref resting on the branch convention **alone** is now verified before it is acted on, and only a definitive 404 drops it; every other answer keeps it. The record answers first: a live session (its own ref, or a durable PR binding) is the target for control, the start test and the spawn, and where one exists the check is not consulted at all. A polled pull-request comment now names its pull request, so the binding is written and the endpoint chosen on that ingress too; and the announcement's own 404 is recorded as `session.work_item_missing` instead of a generic best-effort warning | [spec](../specs/issue-269/), [decision-095](../decisions/decision-095.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/269) |
| issue-260 | How many sessions a work item's pull requests get moved from the operator to the work item (2026-08-17): issue-258 gave the choice to `routing.tmux.sessionPerPr`, machine-wide — the same mistake issue-183 refused to make for `outer-loop-on-pull-request`, because one repository has both a one-repo bugfix and a three-repo migration and one daemon serves both. `phase-selection` now carries three rows (`pr-sessions-never` / `pr-sessions-cross-repository` / `pr-sessions-always`) with the deployment's configured value pre-ticked; exactly one ticked row is the choice, and none, several, an unreadable checklist or a token outside the vocabulary all resolve to that default. The resolved mode is frozen by the same signed `the-loop execute` into `graph-state.json` and the portable record (`graph.sessionPerPr`), and routing reads it there per work item ahead of the config key. Nothing else moved: the three modes mean what decision-092 said, decision-088 D2's tree requirement is untouched, the schema is unchanged, and a work item with no frozen mode routes exactly as before | [spec](../specs/issue-260/), [decision-093](../decisions/decision-093.md), [routing](../config/cli/routing-options.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/260) |
| issue-258 | How many sessions a work item's pull requests get became the operator's choice again (2026-08-17): issue-253 stated the same-repository collapse as a **rule** — `sessionPerPr: true` meant "only a pull request elsewhere splits", and no configuration gave a pull request in the work item's own repository a session of its own. The key is now three-valued — `never`, `cross-repository` (the unchanged default) and `always` — with the legacy booleans still parsing to the first two, so no existing config changes meaning. What did **not** become optional is decision-088 D2: an endpoint spawns only with a working tree of its own, and a same-repository endpoint's checkout must additionally hold the pull request's **head branch** (`Workspace.prepare(require_branch=True)`) — otherwise git's one-branch-per-worktree rule would have handed it a tree silently sitting on the default branch. `always` is therefore served by `workspace.strategy: clone` and declines to the single session under `worktree` | [spec](../specs/issue-258/), [decision-092](../decisions/decision-092.md), [routing](../config/cli/routing-options.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/258) |
| issue-253 | A work item stopped having two owners (2026-08-16): `sessionPerPr` gave every pull request delivering a work item its own harness conversation but never its own **checkout** — `_spawn_endpoint` spawned with `record.cwd`, and `Workspace.prepare` keys both strategies on the work-item slug, so under *every* configuration a pull request's session ran in the work item session's tree. Two agents, one branch, no lock: on issue-239 they interleaved commits, restarted each other's services and ran the same verification twice against a tree each was changing under the other. Now a pull request in the work item's **own repository** is the work item's session's — no second spawn — and a pull request in **another** repository spawns only into a checkout of its own, keyed on its slug, or not at all (`session.pr_session_declined`) | [spec](../specs/issue-253/), [decision-088](../decisions/decision-088.md), [routing](../config/cli/routing-options.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/253) |
| issue-243 | A forwarded event stopped carrying GitHub's metadata (2026-08-16): the `$payload_excerpt` block was a subset of the raw payload — nine containers copied whole, cut at 4,000 characters — so an ordinary comment delivered a 61-character instruction inside 4,014 characters of `user` objects, `reactions` and the whole `issue`, with the cut landing mid-string so the "JSON" did not parse. It is now a **field allow-list per container** with free text capped per field: a comment is its body, its address and its author's login; an inline comment keeps its anchor ahead of the body; lifecycle and CI events keep what makes them actionable. Measured on the same payload, 4,014 → 203 characters and the whole prompt 6,676 → 2,865. Nothing that acts on an event changed — the gates still read the full payload | [spec](../specs/issue-243/), [decision-086](../decisions/decision-086.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/243) |
| issue-240 | A comment abandoned after `polling.maxRetries` is now reported **on the work item** (`poll.giveup_reported`), naming the comment, the attempts and the recovery — posting it again — instead of leaving a 😕 reaction as the only signal. Best-effort and ledger-first: the notice can fail without changing what was recorded, and it echoes no text from the comment it reports | [spec](../specs/issue-240/), [interactive-sessions](interactive-sessions.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/240) |
| issue-246 | The poll ingress reached parity with the receiver on **what a comment is** (2026-08-16): it read only the `IssueComment` connection, so an instruction left as a PR **review** or as an **inline review-thread comment** was never forwarded — silently, since nothing was read there was nothing to drop or log. The provider now merges all three surfaces into one chronological list (`gh pr view --json comments` plus paginated `gh api …/pulls/<n>/{reviews,comments}`), emits each as the event a real webhook would have carried, and forwards an inline comment with its file/line anchor; empty-body and `PENDING` reviews are dropped as carrying no instruction, an issue costs the one request it always did, and the retained-id cap grew to fit three streams in one ledger | [spec](../specs/issue-246/), [polling](../config/cli/polling-options.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/246) |
| issue-228 | The ingresses stopped owning the operator surface (2026-08-14): the poller and receiver are started by `the-loop start` per `polling.enabled` / `webhooks.ghWebhook.enabled` (both default off), the `poll` command is gone (`daemon_entry poller [--once]` is the foreground/cron form; the run loop itself is unchanged), a start is proven by the daemon's pidfile lock instead of the removed double-fork handshake, and the receiver now holds its pidfile as a flock like the poller — so `daemon_status`, `the-loop status` and a truthful blocking `the-loop stop` all answer from the lock (the `gh-webhook` command itself folded away on the owner's PR #229 review, its run loop relocated to `the_loop.webhook.daemon`). Amended in the same PR (issue-231): `service.hostIngresses` (default true) runs both ingresses as threads inside the service process, locks kept per-ingress under the service's pid | [spec](../specs/issue-228/), [decision-084](../decisions/decision-084.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/228), [issue-231](https://github.com/MadaraUchiha-314/the-loop/issues/231) |
| issue-225 | An eighth control keyword, `do` (`the-loop do`, `routing.control.keywords.do`): arms and spawns exactly as `start` at both spawn seams (same durable record, same named-actor authorization, same two-keyword refusal) and selects `pdlc-adhoc-loop` for the work item's outer walk — a tactical task with no PDLC process, resolved by the GraphLink state-first and then from the portable control record through the shared `LOOP_FOR_CONTROL_COMMAND` mapping. The existing token boundary already refuses `the-loop done`/`does`/`docs`, so no parser change was needed | [spec](../specs/issue-225/), [decision-083](../decisions/decision-083.md), [process-graph](process-graph.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/225) |
| issue-201 | Adoption moved to before the spawn (2026-08-10): issue-193 wrote the built-in default from `on_spawn`, which the dispatcher calls **after** `tmux.spawn` — so a session could begin, SessionStart hook included, in a checkout whose `.the-loop/` did not exist yet. A public `GraphLink.adopt` now runs between workspace preparation and the prompt render, and again in the respawn pre-flight, carrying the coupling's own gates (the prepared `cwd` is not yet proved to be the work item's repository); `_adopt` stays on the driving actions as an idempotent safety net. The ordering is asserted from inside the spawn call, not after the dispatch returns | [spec](../specs/issue-201/), [decision-073](../decisions/decision-073.md), [process-graph](process-graph.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/201) |
| issue-197 | The poll ingress stopped letting the work item's author decide whether anybody is listened to (2026-08-10): a comment is judged by its own author, so an authorized user's control comment on an outside contributor's issue arms and forwards; the item's author now gates only whether the poller starts work on it **by itself**, and an authorized user's recorded arming command satisfies that gate too. The spawn prompt states the work item itself is untrusted content | [spec](../specs/issue-197/), [decision-074](../decisions/decision-074.md), [polling](../config/cli/polling-options.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/197) |
| issue-199 | The spawning comment reaches the graph (2026-08-10): a spawn that enters a **human** start node now evaluates that node's exit chain once, with the spawning event's comments attached — so `the-loop contribute` carrying a goal moves the item to `phase-selection` without a second command, where before the arming comment (executed by the control path, never forwarded) could reach no gate at all and the item sat at its first node until some unrelated event arrived; agent start nodes and respawns evaluate nothing | [spec](../specs/issue-199/), [process-graph](process-graph.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/199) |
| issue-193 | The ingress adopts a repository that never ran `/the-loop:init` (2026-08-10): the graph coupling writes the-loop's built-in default to `.the-loop/harness-config.yaml` — naming the work item's owner/repo so `originRepo` resolves — after the `origin`-remote ownership proof and **before** the spec-directory gate, so the session the daemon just spawned has a config to read even on the run whose graph is skipped; recorded as `harness.config_scaffolded`, never overwriting an existing config, and never for a contribution | [spec](../specs/issue-193/), [decision-073](../decisions/decision-073.md), [process-graph](process-graph.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/193) |
| issue-186 | A seventh control keyword, `cleanup` (`the-loop cleanup`, `routing.control.keywords.cleanup`): releases a work item's LOCAL resources — every endpoint's tmux session, the workspace checkout, the machine-local session record — keeping the portable record and touching nothing remote. Runs with or without a live session (the retroactive case), disarms the item like a stop, and runs automatically on a closure **only** when the close event names an authorized actor; otherwise it is deferred and recorded | [spec](../specs/issue-186/), [interactive-sessions](interactive-sessions.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/186) |
| issue-185 | A sixth control keyword, `contribute` (`the-loop contribute`, `routing.control.keywords.contribute`): arms and spawns exactly as `start` at both spawn seams (same durable record, same named-actor authorization, same ambiguity refusal) and selects `pdlc-contribution-loop` for the work item's outer walk — resolved by the GraphLink state-first, then from the portable control record | [spec](../specs/issue-185/), [decision-070](../decisions/decision-070.md), [process-graph](process-graph.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/185) |
| issue-183 | Cross-repository linkage (2026-08-09): a qualified closing reference to another repository now routes to the work item **there** instead of being dropped, so a pull request delivering one repository's share of a multi-repo work item can reach its ticket; the PR's inner loop is addressed by repository as well as number, and an inner-loop prompt's claim command carries `--pr-repo` | [spec](../specs/issue-183/), [decision-069](../decisions/decision-069.md), [process-graph](process-graph.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/183) |
| issue-172 | Which session owns a PR's events stopped being recomputed from `gh` per event (2026-08-07): the work item's single session record now carries its `pullRequests[]`, each an endpoint with its own tmux session and harness conversation (`routing.tmux.sessionPerPr`, default on — `false` collapses to the pre-issue-172 single session), spawned lazily and closed individually when its PR closes. Additive resolution; issue-93's derivation and issue-101's close rule unchanged | [spec](../specs/issue-172/), [decision-064](../decisions/decision-064.md), [state](../cli/state.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/172) |
| issue-159 | Stopping and restarting the poller became invisible (2026-08-05): an exclusive lock on the pidfile makes two pollers on one ledger impossible (`--once` included), `poll stop` verifies the pid against that lock and waits for the process to exit, each work item's record is persisted as it finishes, a stop ends the cycle after the item in flight (and an interrupted cycle never reconciles closures), and a shutdown hands back the retry budget of dispatches it abandoned | [spec](../specs/issue-159/), [polling](../config/cli/polling-options.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/159) |
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
