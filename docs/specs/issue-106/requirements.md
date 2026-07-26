---
type: requirements
phase: requirements-definition
workItem: "issue-106"
status: draft
approvedBy: []
collaborators: [product-manager, engineer]
overrides: {}
---

# Requirements: authorized execution control (start/stop/pause/resume) + one state root

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (https://kiro.dev/docs/specs/). Tier 4 (`human-approves-pr`): this changes the
> daemon's **trigger** boundary — the authorization surface — so the spec and the
> code are approved together at the PR, with a security review on the gate.

## Introduction

[Issue #106](https://github.com/MadaraUchiha-314/the-loop/issues/106) asks for a
second, explicit condition on everything the-loop forwards to an agent harness:

> The auto-execute label is a necessary but not a sufficient condition. Any
> action that the-loop has to forward to the agent harness (claude/cursor) has
> to come from an authorized user.

Today the daemon has exactly one authorization gate — `routing.authorizedUsers`
(`the_loop.authz`), enforced on both ingress paths — and one *intent* gate, the
`the-loop: auto-execute` label. That combination answers "may this person's text
be acted on?" but never "did a human actually ask for this run, right now?". The
consequences the issue is after:

1. **Labelling is an irreversible trigger.** Adding the label to an issue is
   enough to spawn an autonomous session. There is no way for the person who
   labelled it to say "not yet", and no way to stop, pause or resume a run other
   than killing the daemon or `the-loop sessions close`, which throws the
   conversation away.
2. **There is no vocabulary for control.** An authorized user can only steer a
   session by talking *to the agent* (a comment is forwarded into the harness
   conversation and the agent decides what to do with it). Nothing in the
   comment thread reaches **the-loop itself**. The issue asks for declared
   keywords — defaults `the-loop:start-execution`, `the-loop:stop-execution`,
   `the-loop:pause-execution`, `the-loop:resume-execution` — that the daemon
   interprets rather than forwards.
3. **The CLI cannot do what a comment can.** Someone with shell access to the
   machine running the-loop should be able to start/stop/pause/resume a work
   item's session, and — for the sanctity of the ticket — that action should
   leave the *same* trace on the issue an authorized user's comment would have,
   carrying the loop-prevention marker so the daemon does not read its own
   comment back (the issue-104 contract).
4. **Session state has nowhere to live.** Pausing is a durable state a restart
   must survive, and "an authorized user asked for a start" must outlive the
   comment that said so. The registry today knows only `active`/`closed`.
5. **Generated state is scattered.** `.the-loop/sessions/`,
   `.the-loop/poll-state.json`, `.the-loop/logs/events.jsonl` and
   `.the-loop/gh-webhook.pid` each carry their own default path. The issue asks
   for the session-related tracking files to be consolidated under `sessions/`
   and for **one configured root** under which everything the CLI generates
   lives.

## Requirements

### Requirement 1 — declared control keywords, interpreted by the-loop

**User story:** As an authorized user, I want to type a declared keyword in a
comment on the work item or its PR, so that I can start, stop, pause or resume
the-loop's execution without the daemon guessing my intent from prose.

#### Acceptance criteria

1. **1.1** the-loop SHALL declare four control commands in the CLI config
   (`webhooks.ghWebhook.routing.control.keywords`) with the defaults
   `the-loop:start-execution`, `the-loop:stop-execution`,
   `the-loop:pause-execution` and `the-loop:resume-execution`.
2. **1.2** WHEN a comment (issue comment, PR conversation comment, PR review or
   review comment) carries a declared keyword THEN the-loop SHALL interpret it
   as that control command instead of forwarding the comment into the harness
   conversation.
3. **1.3** A keyword SHALL match only as a **whole token** — delimited by
   whitespace, a line start/end, or common markdown punctuation — and
   case-insensitively, so `the-loop:start-execution.` and a keyword on its own
   line both match while `xthe-loop:start-executionx` does not.
4. **1.4** WHEN a comment carries **two or more different** control keywords
   THEN the-loop SHALL treat the comment as ambiguous: no command is executed,
   the comment is **not** forwarded to the harness, and the drop is recorded
   (`control.ambiguous`) — a request the operator can see and re-state.
5. **1.5** The control vocabulary SHALL be recognised on **both** ingress paths
   (webhook receiver and poller) through one shared implementation, so the two
   can never diverge.
6. **1.6** A control comment SHALL be honoured only when it passes the **existing**
   guards first: it is not the-loop's own comment (`authz.is_self_authored`) and
   its author is in `routing.authorizedUsers`. An unauthorized author's control
   keyword SHALL be dropped exactly like any other unauthorized input — no
   command, no forward. The control path SHALL additionally require a **named**
   actor: `is_authorized` deliberately allows an *actor-less* action (a CI event
   carries status, not instructions), and a body-bearing event can reach the
   dispatcher without one (a comment by a deleted account has no author on the
   poll path) — harmless while a comment could only become agent input, not
   harmless once it can start or stop a session.
7. **1.7** WHEN `routing.control.enabled` is false THEN no comment SHALL be
   interpreted as a command and comments SHALL be forwarded as they are today.

### Requirement 2 — the label is necessary, not sufficient

**User story:** As an operator, I want labelling an issue to *arm* autonomous
execution rather than start it, so that a session only ever begins because an
authorized human explicitly asked for it.

#### Acceptance criteria

1. **2.1** `routing.control.requireStartCommand` SHALL default to **true**:
   with `spawnOnUnmatched: labeled`, a labelled work item SHALL NOT spawn a
   session until an authorized user has issued the **start** command for it.
2. **2.2** WHEN `requireStartCommand` is true AND `spawnOnUnmatched: always`
   THEN the start command SHALL be required just the same — "always" widens
   *which items* may spawn, never *who* may start them.
3. **2.3** WHEN an authorized user issues the start command on a work item that
   is labelled (or whose spawn policy is `always`) AND has no live session THEN
   a session SHALL be spawned, on either ingress path.
4. **2.4** WHEN the start command arrives for a work item that is **not** armed
   (no auto-execute label under `spawnOnUnmatched: labeled`, or the policy is
   `never`) THEN no session SHALL be spawned, the refusal SHALL be recorded with
   its reason, and **nothing SHALL be left standing**: arming the work item
   afterwards SHALL NOT start it. Only a start issued *while* the item is armed
   starts it — otherwise adding the label would still be the trigger, which is
   what this work item removes. *(Owner decision on PR #107.)*
5. **2.5** A start request SHALL be **durable** once it is honoured: an accepted
   start survives a daemon restart, so a spawn that failed and is retried later
   does not need the comment again. A **refused** start is not retained (2.4).
6. **2.6** WHEN `requireStartCommand` is false THEN spawning SHALL behave exactly
   as it does today (label/policy alone), so an operator can keep the pre-#106
   behaviour.
7. **2.7** A control command SHALL never *widen* who may trigger the-loop: it is
   an additional condition on top of `authorizedUsers`, never a replacement for
   it. In particular an empty `authorizedUsers` still fails closed.

### Requirement 3 — pause, resume and stop act on a live session

**User story:** As an authorized user, I want to pause a running session and
resume it later, so that I can hold an agent off (a release window, a
conversation I want to have first) without discarding what it knows.

#### Acceptance criteria

1. **3.1** The session registry SHALL support a `paused` status alongside
   `active` and `closed`, persisted in the session's registry file so it survives
   a daemon restart.
2. **3.2** WHEN a session is `paused` THEN events for its work item SHALL NOT be
   delivered to the harness; each suppressed event SHALL be recorded
   (`dispatch.dropped`, reason `session-paused`) rather than silently discarded.
3. **3.3** WHEN the **resume** command is issued for a paused session THEN it
   SHALL return to `active` and subsequent events SHALL be delivered again.
   Events suppressed while paused are NOT replayed — the harness is told to
   re-read the thread instead (the same "only events going forward" contract the
   receiver already has).
4. **3.4** WHEN the **stop** command is issued THEN the work item's session SHALL
   be closed through the same path a work item's closure already takes — registry
   entry closed, the harness process in a retained tmux session terminated per
   `routing.tmux.killHarnessOnClose`, workspace cleaned per
   `keepCheckoutOnClose` — so stopping leaves no orphaned agent.
5. **3.5** WHEN **start** is issued for a session that is already `paused` THEN
   it SHALL resume it (start means "execution should be running"), and when
   issued for an already-`active` session it SHALL be a recorded no-op.
6. **3.6** WHEN pause/resume/stop is issued for a work item with **no** live
   session THEN nothing SHALL be spawned, and whether it is *remembered* depends
   on the direction: a **disarming** command (`pause`, `stop`) SHALL be recorded
   as the work item's control state, so a stopped item does not re-spawn on the
   next event; an **arming** command (`start`, `resume`) that could not act SHALL
   NOT be recorded (2.4). *(Owner decision on PR #107.)*
7. **3.7** A `paused` session SHALL still be found by the registry as a **live**
   session, so nothing spawns a second session for a work item that has a paused
   one.
8. **3.8** A **close** event (issue closed, PR merged/closed) SHALL close a paused
   session exactly as it closes an active one — pausing must not leak an agent
   past the end of its work item.

### Requirement 4 — the same control from the CLI, with the same paper trail

**User story:** As an operator on the machine running the-loop, I want
`the-loop sessions start|stop|pause|resume` to do exactly what the comment
keywords do, and to leave the same visible trace on the ticket.

#### Acceptance criteria

1. **4.1** `the-loop sessions start|stop|pause|resume --work-item <ref>` SHALL
   apply the same command the corresponding keyword applies.
2. **4.2** Each such invocation SHALL post a comment on the work item whose body
   carries the **same keyword** an authorized user would have typed, plus a
   short human-readable line saying it came from the CLI, so the issue thread
   remains a complete record of every control action.
3. **4.3** That comment SHALL carry the loop-prevention marker
   (`authz.mark_self_authored`), so neither ingress path reads it back as a new
   command (issue-104's contract) — the local action has already been applied.
4. **4.4** Posting SHALL be **best-effort**: a missing/failing `gh` SHALL warn
   and SHALL NOT undo or fail the local action. `--no-comment` SHALL skip it.
5. **4.5** `the-loop sessions start` SHALL spawn a session locally (through the
   same dispatcher machinery the daemon uses: workspace checkout, harness trust,
   runner, announcement) when the work item has no live session, so an operator
   with CLI access is not waiting on the daemon's next event or poll cycle.
6. **4.6** `the-loop sessions list` SHALL show each session's status (including
   `paused`) and the last control command recorded for the work item, so the
   operator can see what state a work item is in.
7. **4.7** Every CLI control action SHALL be recorded in the event log with its
   source (`cli`), alongside the ones recorded for comment-sourced commands
   (`comment`).

### Requirement 5 — one configured root for everything the CLI generates

**User story:** As an operator, I want a single configured directory that holds
everything the-loop's CLI writes, with the session-related tracking files
together under `sessions/`, so I can back it up, relocate it or wipe it in one
move.

#### Acceptance criteria

1. **5.1** The CLI config SHALL carry a top-level `state.root` (default
   `.the-loop`) naming the root directory under which every file the CLI
   generates lives.
2. **5.2** The **defaults** of the generated-file paths SHALL be derived from
   that root: the session registry at `<root>/sessions/`, the control records at
   `<root>/sessions/control/`, the poll state at
   `<root>/sessions/poll-state.json`, the event log at `<root>/logs/events.jsonl`
   and the receiver pidfile at `<root>/gh-webhook.pid`.
3. **5.3** An **explicitly configured** path (`routing.registryDir`,
   `polling.stateFile`, `eventLog.path`, `webhooks.ghWebhook.pidfile`) SHALL
   continue to be used verbatim, so existing configs keep working unchanged and
   the root only supplies defaults.
4. **5.4** WHEN `polling.stateFile` is not configured AND the pre-#106 default
   file (`.the-loop/poll-state.json`) exists while the new default does not
   THEN the poller SHALL keep using the legacy file and SHALL warn once, naming
   the new location — an upgrade must never silently re-baseline every watched
   thread (which would re-forward the whole comment history).
5. **5.5** All session-related tracking the CLI maintains — registry entries and
   control records — SHALL live under `<root>/sessions/`.
6. **5.6** The root SHALL be documented in `.the-loop/cli-config.schema.json`,
   the shipped `cli-config.yaml` and `cli/README.md`, and the schema SHALL
   continue to reject unknown keys.

### Requirement 6 — configuration, observability and docs

1. **6.1** `routing.control` (`enabled`, `requireStartCommand`, `keywords`,
   `ghBinary`) SHALL be documented in `.the-loop/cli-config.schema.json`, the
   shipped cli-config YAML and `cli/README.md`, and SHALL hot-reload with the
   rest of `RoutingConfig`.
2. **6.2** New event types SHALL be registered in `eventlog.EVENT_TYPES`:
   `control.command` (a command was recognised and applied, with its source and
   the resulting effect), `control.rejected` (recognised but refused — not armed,
   nothing to act on) and `control.ambiguous` (two conflicting keywords in one
   comment). Pause/resume of a session SHALL emit `session.paused` /
   `session.resumed`.
3. **6.3** The affected capability docs
   (`docs/capabilities/webhook-triggers.md`, `docs/capabilities/cli.md`,
   `docs/capabilities/interactive-sessions.md`) SHALL be updated in the same PR,
   and the behaviour change in 2.1 SHALL be called out as an upgrade note.

## Security considerations (threat-model-lite)

- **Untrusted actors.** Anyone who can comment on a watched issue/PR can write
  the keywords. That is precisely why control commands are gated by the
  *existing* `authorizedUsers` allowlist and evaluated **after** it (R1.6): the
  vocabulary adds a condition, it never becomes a second, weaker way in (R2.7).
  An empty allowlist still fails closed.
- **Trust boundary: comment text → daemon action.** Before #106 a comment could
  only ever become *harness input* (data the agent reads). It can now become a
  *daemon action* (spawn/pause/resume/close). The boundary is kept narrow by
  construction: the parser recognises a **fixed, configured vocabulary** and
  yields one of four enum values — no free-form text from a comment reaches the
  dispatcher's control path, is interpolated into a shell command, or names a
  path, harness, session id or work item. The work item acted on comes from the
  router's own extraction, never from the comment body.
- **Privilege direction.** The commands available are deliberately asymmetric in
  risk: pause/stop/resume only ever *reduce or restore* activity for a session
  that already exists. The only command that can *begin* autonomous execution is
  start, and it needs everything the old path needed (authorized author, armed
  work item, spawn policy) **plus** the explicit request — so #106 strictly
  tightens the trigger surface (R2.1 flips the default to fail-closed).
- **Self-comment loop.** The CLI posts the same keyword a human would, which
  would otherwise be read back as a fresh command on the next poll cycle and
  re-applied forever. The issue-104 marker contract is therefore mandatory on
  the CLI's comment (R4.3), and control parsing happens strictly after the
  self-authored check (R1.6).
- **Denial of service by an authorized user.** A user in the allowlist can pause
  or stop sessions; they can already close issues and remove labels, so this
  grants no new power. Every control action is recorded in the event log with
  its actor and source (R4.7, R6.2), so the record shows who did what.
- **Fail-closed on doubt.** An ambiguous comment executes nothing (R1.4); an
  unparseable/absent control config falls back to the documented defaults; a
  work item that is not armed refuses the start (R2.4).
- **No new secrets, no new network surface.** The CLI's comment is posted with
  the operator's own `gh` credentials, like reactions (issue-84) and the session
  announcement (issue-86), and nothing new listens on a socket.
