---
type: requirements
phase: requirements-definition
workItem: "issue-94"
status: draft
approvedBy: []
collaborators: [product-manager, engineer]
overrides: {}
---

# Requirements: closing a work item ends its harness session (poller + tmux)

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (https://kiro.dev/docs/specs/). Tier 3 (`human-approves-pr`): spec + code are
> approved together at the PR.

## Introduction

[Issue #94](https://github.com/MadaraUchiha-314/the-loop/issues/94) reports that
the poller never reacts to a work item ending — an issue closed, a PR merged —
so the harness session it spawned (and the tmux session hosting it) lives on.
Tracing the code confirms it, and finds a second, related gap:

1. **The poller is blind to closure.** `GitHubPollProvider.list_work_items()`
   asks `gh issue/pr list --state open --label <auto-execute>`. When the item is
   closed or the PR is merged it simply **disappears from the listing**, and the
   poller's per-item loop only ever runs over what the listing returned. Nothing
   compares the listing against the sessions the registry holds, so a closed
   item's session is never closed: it stays `active` in the registry, its tmux
   session stays up, and its `claude` process keeps running forever.
2. **The webhook path only handles PR close.** `Dispatcher.handle` auto-closes on
   `pull_request`/`closed` (merged or not), but an `issues`/`closed` event falls
   through to the normal routing path and is **delivered into the harness
   conversation** as an event prompt — waking the agent to work a ticket that is
   already done, rather than ending its session.
3. **Even a handled close leaves the conversation alive.** Since issue-86 the
   default is `routing.tmux.keepSessionOnClose: true`: the registry entry is
   closed, but the tmux session is *kept* — with the harness process still
   running inside it. So after a merge, `loop-<slug>` is still an interactive,
   writable `claude` TUI. Anything pasted or typed into it (a stray keystroke on
   an attached terminal, the ttyd browser terminal, a `tmux send-keys` from a
   script) resumes a session nobody is supervising. That is exactly what the
   issue means by "the tmux session should be closed so that no stray input can
   open it — but the claude/cursor session should definitely be closed".

The issue also asks for the retained transcript to survive as a **read-only
view**. Retention itself already exists (issue-86: `keepSessionOnClose` +
tmux's `remain-on-exit` keep the pane and its scrollback after the harness
exits); what is missing is that the harness is *still running*, so "retained"
today means "still writable". Ending the harness process turns the retained pane
into what issue-86 was reaching for: a dead pane whose scrollback can be read
and cannot be typed into.

The work therefore has three parts: make the **poller notice** a closure, make
the **dispatcher treat an issue close like a PR close**, and make **closing a
session actually end the harness conversation** while keeping its transcript.

## Requirements

### Requirement 1 — the poller reacts to a work item that is no longer open

**User story:** As an operator running `the-loop poll`, I want a closed issue or
a merged PR to end its session, so that work items do not leave orphaned agents
running on my machine.

#### Acceptance criteria

1. **1.1** WHEN a poll cycle successfully lists a source's open labelled items
   THEN the poller SHALL reconcile the **active** registry sessions that source
   owns against that listing, and for every such session whose work item is not
   in it, ask the provider for that item's closure state.
2. **1.2** WHEN the provider reports the item **closed** (issue closed, PR closed
   unmerged) or **merged** THEN the poller SHALL dispatch a synthesised close
   event through the same `Dispatcher` the webhook receiver uses, so the session
   is closed identically on both ingress paths (registry entry closed, tmux
   handled per R3, workspace cleaned).
3. **1.3** WHEN the provider reports the item still **open** (e.g. only the
   auto-execute label was removed) or **cannot answer** (API/network/auth error)
   THEN the poller SHALL leave the session untouched and retry on a later cycle
   — a closure is never inferred from doubt.
4. **1.4** WHEN listing a source's work items fails THEN that source's
   reconciliation SHALL be skipped for that cycle, so a failed or partial
   listing can never be read as "everything closed".
5. **1.5** WHEN reconciliation closes a session THEN the poller SHALL forget that
   item's poll state, so a **reopened** work item is first-sight again and spawns
   a fresh session instead of being ignored as already-known.
6. **1.6** The reconciliation SHALL consider only sessions the polling source
   owns (matching provider **and** configured repo scope), so a registry shared
   with other repos, other sources or the webhook receiver is untouched.
7. **1.7** The closure query and the closure event SHALL live behind the
   provider contract (`the_loop.poller.base`), so the poller core stays
   provider-agnostic and a future Jira provider opts in by implementing them —
   a provider that does not is simply never reconciled.

### Requirement 2 — closing the ticket closes the session on the webhook path too

**User story:** As an operator running the webhook receiver, I want closing the
issue to end its session, so that the two ingress paths behave the same and a
finished ticket never wakes its agent again.

#### Acceptance criteria

1. **2.1** WHEN an `issues` event with action `closed` matches an active session
   THEN the dispatcher SHALL close that session — as it already does for
   `pull_request`/`closed` — instead of delivering the event into the harness
   conversation.
2. **2.2** WHEN a close event matches no active session THEN nothing SHALL happen
   (in particular it SHALL NOT spawn one, whatever `spawnOnUnmatched` says).
3. **2.3** The router's authorization guard SHALL treat an issue close as the
   same kind of lifecycle signal it already exempts PR close for: it carries no
   free-form text into a harness and can only end the-loop's own session.
4. **2.4** WHEN a session is auto-closed THEN `session.autoclosed` SHALL record
   **why** (`issue-closed` | `pr-merged` | `pr-closed`) alongside the existing
   `merged` flag.

### Requirement 3 — closing a session definitely ends the harness conversation

**User story:** As an operator, I want a closed work item's `claude`/`cursor`
process to be gone, so that no stray input can resume an unsupervised agent.

#### Acceptance criteria

1. **3.1** WHEN a tmux-hosted session is closed (auto-close, or
   `the-loop sessions close`) AND `routing.tmux.killHarnessOnClose` is true
   (the default) THEN the harness process running in that session's pane SHALL
   be terminated — `SIGTERM`, escalating to `SIGKILL` if it is still alive after
   `routing.tmux.harnessKillGraceSeconds` — so the conversation cannot receive
   further input.
2. **3.2** WHEN the harness is terminated AND the tmux session is being retained
   THEN `remain-on-exit` SHALL be (re-)set on it first, so the pane and its
   scrollback survive the process exiting even if the spawn-time attempt failed
   or `remainOnExit` was off.
3. **3.3** WHEN `routing.tmux.keepSessionOnClose` is false THEN the tmux session
   SHALL be killed outright as today (which ends the harness with it); no
   separate termination step SHALL run.
4. **3.4** Termination SHALL be best-effort and never break a close: an already
   dead pane, an already gone tmux session, an unreadable pane list, a process
   that has already exited or a signal that is refused SHALL be logged and the
   close SHALL complete regardless.
5. **3.5** WHEN `killHarnessOnClose` is false THEN a retained session SHALL keep
   its running harness exactly as it does today (the pre-issue-94 behaviour).
6. **3.6** Only the pids tmux reports for **this session's own** `loop-<slug>`
   panes SHALL ever be signalled — never a pid from the registry, a payload, or
   a process-table scan. A recorded `tmuxTarget` that is not a the-loop session
   name (`loop-<slug>`) SHALL be refused outright, and a pid that is not
   positive SHALL never be signalled (`os.kill(0, …)` signals a whole process
   group).
7. **3.7** `process`-runner sessions are unaffected: they have no persistent
   harness process (one-shot subprocess per event), so closing one stays exactly
   as it is.

### Requirement 4 — the retained session is a read-only record

**User story:** As a human reading back what an agent did, I want to attach to a
finished session without any chance of typing into it.

#### Acceptance criteria

1. **4.1** WHEN `the-loop sessions attach` targets a **closed** session THEN it
   SHALL attach read-only (`tmux attach -r`) whether or not `--read-only` was
   passed, and say so on stderr.
2. **4.2** WHEN it targets an active session THEN `--read-only` SHALL keep its
   current opt-in behaviour.

### Requirement 5 — configuration, observability and docs

1. **5.1** `routing.tmux.killHarnessOnClose` (boolean, default `true`) and
   `routing.tmux.harnessKillGraceSeconds` (number ≥ 0, default `5`) SHALL be
   documented in `.the-loop/cli-config.schema.json`, both shipped cli-config
   YAMLs and `cli/README.md`, and SHALL hot-reload with the rest of
   `RoutingConfig`.
2. **5.2** New event types SHALL be registered in `eventlog.EVENT_TYPES`:
   `poll.closure_detected` (a poll cycle found a session's item closed/merged)
   and `session.harness_terminated` (the harness process in a retained tmux
   session was ended, with whether SIGKILL was needed).
3. **5.3** The affected capability docs (`docs/capabilities/interactive-sessions.md`,
   `docs/capabilities/webhook-triggers.md`) SHALL be updated in the same PR.

## Security considerations (threat-model-lite)

- **Untrusted actors.** Anyone who can close an issue/PR in a watched repo can
  now end the-loop's session for it. That is the intent, is bounded (it ends the
  agent, never starts or steers one), and matches the existing PR-close
  precedent — which is why the router's authorization exemption extends to it.
  The reverse direction is the one that matters and is unchanged: a close can
  never *spawn* a session (R2.2).
- **No new prompt-injection surface.** A closure is a *lifecycle* signal: the
  synthesised payload is built from the provider's own API answer (numbers,
  state, url) and is **never rendered into a harness prompt** — the close path
  returns before any template is rendered. Item titles/bodies from the API do
  not reach a harness.
- **Signalling processes.** The only pids ever signalled are those tmux reports
  for the panes of *this session's own* `loop-<slug>` target (R3.6) — a session
  the-loop itself spawned. Pids are never taken from the registry file, an event
  payload, or a process-table scan. Two guards keep a corrupted or hand-edited
  registry from aiming the signal: the recorded `tmuxTarget` must match
  `loop-<slug>` before any pane is even listed (otherwise the-loop would happily
  SIGTERM the panes of whatever tmux session that string named), and a
  non-positive pid is dropped rather than passed to `os.kill`, where `0`/negative
  mean "the whole process group". `ProcessLookupError`/`PermissionError` are
  handled: the-loop reports and moves on rather than escalating privileges.
- **Fail-closed on doubt.** Every uncertainty (a failed listing, an unanswerable
  closure query, an unparseable state) leaves the session **running** (R1.3,
  R1.4). The failure mode is a session that outlives its ticket — today's
  behaviour — never an agent killed mid-work because GitHub returned a 502.
- **Blast radius of a wrong close.** Closing a session is not destructive: the
  registry entry is marked closed (the file, and with it the harness session id,
  is kept), the tmux scrollback is retained, and the workspace cleanup that runs
  is the same one PR-close already performs (and is opt-out via
  `workspace.keepCheckoutOnClose`). A reopened item spawns again (R1.5).
- **Risk tier 3** (`human-approves-pr`), below
  `security.review.humanSignOffMinTier: 4` — no named human security sign-off is
  required. The schema edits are additive, opt-out config keys, matching the
  issue-86/issue-89 precedent for the same file.

## Out of scope

- Killing a `process`-runner dispatch in flight (R3.7) — those subprocesses are
  per-event and transient.
- Any new persistence of the transcript beyond tmux's retained scrollback (e.g.
  writing `capture-pane` output to a file). The dead retained pane plus
  `sessions attach` is the read-only view this issue asks for; a durable
  transcript artifact is a separate work item if wanted.
- Reacting to an issue/PR merely losing the auto-execute label (still open ⇒
  still routed, R1.3).
- Cursor: `cursor-agent` cannot be tmux-hosted at all (issue-32), so it has no
  interactive process to terminate; the config and code paths are harness-neutral
  and would cover it the day it can.
