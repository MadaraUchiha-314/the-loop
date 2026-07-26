---
type: requirements
phase: requirements-definition
workItem: "issue-98"
status: draft
approvedBy: []
collaborators: [product-manager, engineer]
overrides: {}
---

# Requirements: `the-loop sessions` — one place to see and manage tracked work

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (https://kiro.dev/docs/specs/). Tier 3 (`human-approves-pr`): spec + code are
> approved together at the PR.

## Introduction

[Issue #98](https://github.com/MadaraUchiha-314/the-loop/issues/98) asks for an
operator-facing surface over the daemon: *"shows a table of what all issues are
being tracked by the-loop's poller … links from work item to tmux session (if
present) or process to PR if available … I should be able to fully manage these
sessions from the-loop CLI"*, plus **pause/resume monitoring** of a single work
item, reachable **either** from the CLI **or** by putting a label on the ticket,
with those labels created during `init`/onboarding. Explicitly *not* wanted: a
TUI. Plain, well-spaced stdio is the bar.

Today `the-loop sessions` already exists with `register | list | attach | close`
(issue-15, issue-32, issue-86), but it falls short of the ask on three counts:

1. **It only knows about sessions, not about tracking.** `sessions list` walks
   the session registry (`.the-loop/sessions/*.json`). The poller's own ledger
   (`.the-loop/poll-state.json`, issue-80) holds every work item it has seen —
   including items it is tracking but has *not* (yet, or ever) spawned a session
   for: a spawn that is mid-retry, or one that exhausted its retry budget and
   was given up. Those are exactly the rows an operator is looking for when
   something "isn't happening", and no command shows them.
2. **A row does not link anywhere.** It prints the work-item ref, harness,
   session id, runner, tmux target and status. There is no work-item URL, no PR,
   no process id, no attach command — so the operator has to reconstruct all of
   it by hand.
3. **Monitoring is all-or-nothing.** The only lever is `sessions close`, which
   *ends* the session (and, per issue-94, the harness conversation inside it).
   There is no way to say "leave this work item alone for now, don't act on its
   activity, and pick it back up later" — for either ingress path (webhook or
   poll). An operator who wants a noisy or half-baked ticket to stop waking an
   agent must today remove the auto-execute label, which also loses the session.

This work therefore extends the existing `sessions` command (the name already
makes sense — it stays) into the **complete management surface** for what the
daemon is doing, and adds a **pause** concept that both ingress paths honour and
that a GitHub label can drive.

### Scope note — what "process id" can mean here

The issue asks each row to link to "tmux session (if present) or process
(process id)". These are not symmetric in the current design and the
requirements below reflect the truth rather than the wish:

- **`runner: tmux`** — a long-lived tmux session hosts the harness TUI; its
  pane pids are live, queryable state (`tmux list-panes`, already used by
  `TmuxRunner`), so a real pid can be shown.
- **`runner: process`** — the harness is invoked in *print mode* through
  `subprocess.run` for the duration of one dispatch and then exits
  (`HarnessAdapter._run`). There is no persistent process to point at between
  dispatches, and the daemon's transient children are not visible to a separate
  CLI invocation. What *is* stable and useful is the **daemon process that owns
  the session** — the `poll`/`gh-webhook` process that spawned it. That is what
  a process-runner row shows.

## Requirements

### Requirement 1 — one table of everything the-loop is tracking

**User story:** As an operator, I want a single table of every work item
the-loop is tracking, so that I can see at a glance what is being worked, what
is stuck, and what is idle.

#### Acceptance criteria

1. **1.1** WHEN `the-loop sessions list` is run THEN it SHALL print one row per
   work item drawn from the **union** of the session registry and the poller's
   state ledger, so an item the poller tracks without a session is visible.
2. **1.2** WHEN a work item has a registry session THEN its row SHALL carry the
   session's harness, harness session id, runner, status and last-event time.
3. **1.3** WHEN a work item is known only to the poller THEN its row SHALL show
   a `tracked` status and, WHEN the poller has given up spawning for it
   (`spawn.gaveUp`), SHALL show that distinctly (`spawn-failed`) with the
   attempt count, since that is the state an operator most needs to notice.
4. **1.4** The command SHALL support `--status` filtering over the displayed
   statuses (`active`, `closed`, `paused`, `tracked`, `spawn-failed`) and
   `--format table|json`, where `json` emits the same fields as machine-readable
   data (one object per row).
5. **1.5** Output SHALL be plain, column-aligned stdio — no TUI, no cursor
   control, no colour required to read it — and SHALL remain readable when a
   field is missing (rendered `-`).
6. **1.6** WHEN neither the registry nor the poll state yields any row THEN the
   command SHALL say so on stderr and exit `0` (nothing tracked is not an
   error).

### Requirement 2 — every row links onward

**User story:** As an operator, I want each row to tell me where to go next —
the ticket, the terminal, the PR — so that I do not have to reconstruct links by
hand.

#### Acceptance criteria

1. **2.1** Every row SHALL carry the work item's ref (`github:OWNER/REPO#N`) and,
   WHEN it can be derived, its URL.
2. **2.2** WHEN a row's session runs under `runner: tmux` THEN it SHALL show the
   tmux target, whether that tmux session is currently **live**, and the
   `tmux attach` command for it.
3. **2.3** WHEN a row's session runs under `runner: process` THEN it SHALL show
   the owning daemon process (`process:<pid>`) recorded at spawn time, and
   whether that pid is still alive.
4. **2.4** WHEN a pull request has been observed for a work item THEN the row
   SHALL show the PR (ref and, when known, URL); a work item with no observed PR
   SHALL render `-` rather than guessing.
5. **2.5** `the-loop sessions show --work-item <ref>` SHALL print the full detail
   for one row — ticket URL, PR, harness + session id, runner and host (tmux
   target/attach command or owning pid, with liveness), working directory,
   pause state and reason, created/last-event timestamps, and the poller's
   tracking state — as labelled `key: value` lines.

### Requirement 3 — pause monitoring for one work item

**User story:** As an operator, I want to stop the-loop acting on a specific
work item without tearing its session down, so that a noisy or not-ready ticket
stops waking an agent while I keep its context.

#### Acceptance criteria

1. **3.1** WHEN `the-loop sessions pause --work-item <ref>` is run THEN a durable
   pause record SHALL be written for that ref (surviving daemon restarts), with
   an optional `--reason`, and the command SHALL report what it did.
2. **3.2** WHILE a work item is paused, the **poller** SHALL NOT spawn a session
   for it and SHALL NOT forward its comments to a session.
3. **3.3** WHILE a work item is paused, the **webhook/dispatch** path SHALL NOT
   deliver its events to a session and SHALL NOT spawn one, recording the drop
   with reason `paused` in the event log.
4. **3.4** WHILE an **already-tracked** work item is paused, the poller SHALL
   keep its comment baseline current, so that resuming does not flood the
   session with a backlog of everything said during the pause (matching the
   "only events going forward" semantics of the webhook path). WHILE a work item
   the poller has **never seen** is paused, it SHALL record nothing for it, so
   that resuming leaves it first-sight and it is spawned for then — a pause must
   never become permanent.
5. **3.5** Pausing SHALL NOT close the session, kill its tmux session, end the
   harness conversation, or remove any checkout — a paused work item is
   *ignored*, not finished.
6. **3.6** WHEN a paused work item **ends** upstream (issue closed, PR
   merged/closed) THEN the existing closure handling SHALL still run: pause
   suppresses work, never cleanup, so a pause cannot leak a live session forever.
7. **3.7** Pausing a work item that is already paused SHALL be a no-op reported
   as such (idempotent), and SHALL NOT require an existing session — an
   operator may pause an item pre-emptively.

### Requirement 4 — resume monitoring

**User story:** As an operator, I want to undo a pause, so that the-loop picks
the work item back up.

#### Acceptance criteria

1. **4.1** WHEN `the-loop sessions resume --work-item <ref>` is run THEN the
   pause record SHALL be removed and the command SHALL report it.
2. **4.2** AFTER a resume, the next poll cycle / webhook event for that item
   SHALL be processed normally (spawn policy and routing exactly as if the pause
   had never happened).
3. **4.3** Resuming a work item that is not paused SHALL be a no-op reported as
   such, exiting `0`.

### Requirement 5 — *(deferred out of this work item)* pause/resume from a GitHub label

The issue also asked for the pause/resume controls to be available as a GitHub
label. That is **deferred to its own work item**, by the owner's call on
[PR #100](https://github.com/MadaraUchiha-314/the-loop/pull/100): making the
label safe turns out to be a security design question rather than a wiring one,
and it does not belong in a session-management change.

What the deferred item has to settle (researched here, so the follow-up starts
with it):

1. **Who may drive the label.** Only logins in `routing.authorizedUsers` should
   be able to pause or resume with it.
2. **Why presence-as-state cannot express that.** A gate that asks "is the label
   on the item right now?" cannot authorize a **removal** — "the label is gone"
   is indistinguishable from "nobody ever paused it" — so anyone with triage
   rights could resume a parked agent. The label therefore has to be a *trigger*
   that writes the pause ledger, with the ledger as the only thing the gate
   reads.
3. **Where the actor comes from.** Free on the webhook path (`labeled` /
   `unlabeled` carry `label.name` + `sender.login`); absent from every other
   payload and from the poll listing, but recoverable from
   `GET /repos/{owner}/{repo}/issues/{n}/events` (`actor.login` + `label.name`,
   PRs included) — worth one call only when the label and the ledger disagree.
4. **Labels are not only reductive** (owner, PR #100): an authorized person
   labelling a *stranger's* issue should put it into the loop, with comment
   filtering continuing to gate what the agent then acts on. So label
   authorization is a broader question than pause alone — it touches
   auto-execute too, which is exactly why it wants its own spec.
5. Creating the operational labels during `init`/onboarding (`labels ensure`)
   travels with that work item — issue-98 asked for it, and it is only useful
   once the labels do something.

The CLI controls (R3, R4) are unaffected and ship here.

### Requirement 7 — housekeeping from the same command

**User story:** As an operator, I want to clear out records the daemon has
finished with, so that the table stays about live work.

#### Acceptance criteria

1. **7.1** `the-loop sessions prune` SHALL remove **closed** session records
   whose tmux session no longer exists (process-runner records: any closed
   record), reporting each removal.
2. **7.2** It SHALL refuse to remove an `active` record, and SHALL leave a closed
   record whose tmux session is still live (that is the retained transcript from
   issue-86) unless `--include-retained` is passed.
3. **7.3** It SHALL support `--dry-run`.
4. **7.4** Pruning SHALL never kill a tmux session or a process — it removes
   *records*; ending things stays `sessions close`'s job.

### Requirement 8 — the surface stays honest and documented

#### Acceptance criteria

1. **8.1** Every new/changed subcommand SHALL be documented in `cli/README.md`
   with its flags and an example of the output.
2. **8.2** The capability docs (`docs/capabilities/cli.md`,
   `docs/capabilities/interactive-sessions.md`) and the skill's
   `reference/automation.md` SHALL describe pause/resume in the same PR.
3. **8.3** New config keys SHALL be added to `.the-loop/cli-config.schema.json`,
   the shipped `templates/cli-config.yaml`, and this repo's own
   `.the-loop/cli-config.yaml`, with defaults that keep existing behaviour
   unchanged for an operator who edits nothing.

### Requirement 9 — the daemon's runtime state lives in one place

*(Added during PR review: "we have all these files we're tracking now —
`poll-state.json`, `poll.pid`, everything in `sessions/` — and now another one.
Can we consolidate?" — [PR #100](https://github.com/MadaraUchiha-314/the-loop/pull/100),
[decision-040](../../decisions/decision-040.md).)*

**User story:** As an operator, I want everything the daemon writes in one
directory, so that I can tell my files from its files, ignore them with one
rule, and reset cleanly.

#### Acceptance criteria

1. **9.1** Every runtime-state path the daemon writes — session registry, pause
   ledger, poller ledger, both pidfiles, event log — SHALL default to a location
   under a single `.the-loop/state/` directory.
2. **9.2** WHEN a pre-move path exists AND its new-layout counterpart does not
   THEN the pre-move path SHALL still be used, so an operator who upgrades and
   changes nothing loses no session registry, no dedup ledger and no pidfile;
   the fact SHALL be logged once, naming the command that consolidates.
3. **9.3** WHEN a path is explicitly configured THEN it SHALL be used verbatim —
   never re-interpreted, never migrated.
4. **9.4** `the-loop state paths` SHALL print every runtime-state path, which
   layout each is on, and whether it exists.
5. **9.5** `the-loop state migrate [--dry-run] [--force]` SHALL move pre-move
   state into the new layout, SHALL be idempotent, SHALL refuse to overwrite an
   entry that exists in both layouts, and SHALL refuse to run at all while a
   daemon pidfile looks alive (moving a live registry could leave two daemons
   owning one work item) unless `--force` is passed.
6. **9.6** Migration SHALL NOT happen automatically on daemon start.
7. **9.7** `.gitignore`, the config schema, the shipped template and this repo's
   own CLI config SHALL reflect the new layout, with the pre-move paths kept
   ignored so an un-migrated checkout cannot commit its state.

## Non-goals

- **No TUI.** No curses/rich/live-refresh view; `watch the-loop sessions list`
  is the answer to "make it live".
- **No new daemon control plane.** Pause is per work item, not a global stop
  (`the-loop poll stop` already exists) and not a queue-draining lever.
- **No new auth or tokens.** GitHub writes keep going through the operator's own
  `gh`, exactly as reactions/announcements do.
- **No label mechanism at all** (deferred — see R5). The pause ledger is
  provider-agnostic and works for any ref.
- **Not a metrics/history view.** `the-loop events` remains the o11y trail.

## Security considerations

*(Threat model is required for every work item — `config.security.threatModel`.)*

- **No new external trigger.** With the label control deferred (R5), the only
  thing that pauses a work item is the operator's own CLI writing a local file.
  Nothing about the existing trust boundaries changes: the `authorizedUsers`
  prompt-injection guard (`the_loop.authz`) still decides whose items and
  comments are acted on, and the auto-execute label still gates spawning.
- **Trust boundary: the pause record is local state.** It is written by the
  operator's own CLI into the daemon's own directory and read back by the
  daemon. It carries a ref and a free-text reason; the reason is **display-only
  data** and MUST NOT be interpolated into any harness prompt or shell argv.
- **No secrets in output.** The table and `show` print refs, URLs, tmux targets,
  pids, and the working directory — never tokens, prompts or payloads.
- **Availability.** A corrupt or unreadable pause file MUST degrade to "nothing
  is paused" with a warning, never to a crash of the daemon and never to
  everything being silently paused.
