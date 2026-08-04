---
type: requirements
phase: requirements-definition
workItem: "issue-137"
status: approved
approvedBy: [MadaraUchiha-314]
collaborators: [product-manager, engineer]
overrides: {}
riskTier: 3
---

# Requirements: reset the-loop CLI's state for a work item

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (https://kiro.dev/docs/specs/). This phase MUST be reviewed and approved by the
> required collaborators before moving to design.

## Introduction

[Issue #137](https://github.com/MadaraUchiha-314/the-loop/issues/137): *"while testing
the-loop's features or when we find a bug in the-loop and fix the-loop's CLI, once the CLI
is released we need a way to reset the progress for a work item or multiple work items that
are currently in-progress. Expose a CLI command to do this."*

The CLI remembers a work item across four places, and every one of them survives a CLI
upgrade:

| Where | What it remembers | Written by |
|---|---|---|
| `<state.root>/local/<slug>.json` | the harness conversation id, its `cwd`, runner, tmux target, status, recent deliveries | the session registry |
| `<state.root>/portable/<slug>.json` `control` | the last `start`/`stop`/`pause`/`resume` an authorized user asked for | execution control |
| `<state.root>/portable/<slug>.json` `poll` | which comments have already been seen, the retry ledgers, the spawn ledger | the poller |
| the workspace | that work item's worktree or per-work-item clone | the dispatcher |

That memory is the point: it is what makes a `stop` durable, what stops a redelivery
re-forwarding a whole thread, and what lets a daemon restart resume rather than re-spawn.
It is also exactly what is in the way after the operator fixes a bug **in the-loop itself**.
The item is mid-flight, its session is a conversation the old code started, its poll ledger
says every comment on the thread is already handled, and its control record says it is
armed. There is no way to say *"forget this work item; start it over on the new CLI"*.

Today the operator's only options are wrong in different directions. `sessions stop` ends
the session but leaves a closed record and the whole poll ledger behind, so the item is
still "known" and its thread still baselined. `sessions close` does less. Deleting files by
hand is the actual workaround, and it is booby-trapped: dropping
`portable/<slug>.json` outright **resurrects** whatever a pre-issue-128 tree still holds for
that item (`the_loop.workitem` § the legacy readers), so the item comes back armed.

This work item adds the missing verb. It erases the-loop's own memory of a work item on this
machine, through the paths that already own each piece of that memory, and it says out loud
what it removed.

## Requirements

### Requirement 1 — Reset one work item's CLI state

**User story:** As an operator who has just upgraded the-loop's CLI, I want to erase what the
CLI remembers about an in-progress work item, so that it starts over on the new code instead
of resuming a conversation the old code began.

#### Acceptance criteria (EARS)

1. WHEN the operator runs `the-loop sessions reset --work-item <ref>` THEN the system SHALL
   remove every piece of state the CLI holds for that work item on this machine: its session
   record, its `control` section and its `poll` section.
2. WHEN the work item has a **live** session (`active` or `paused`) THEN the system SHALL end
   it through the same close path `sessions stop` uses — registry entry closed, tmux/harness
   ended per `routing.tmux`, workspace checkout cleaned per
   `routing.workspace.keepCheckoutOnClose` — before removing its record, so a reset never
   leaves an orphaned harness running against state that no longer exists.
3. WHEN the session record is removed THEN it SHALL be **deleted**, not marked closed: a
   closed record still appears in `sessions list` and is still reachable by `sessions attach`,
   which is not what "reset" means.
4. WHEN the `control` section is removed THEN the work item SHALL be disarmed — a later
   `ControlStore.start_requested` for it SHALL be false — so a reset item does not re-spawn on
   the strength of a `start` recorded before the reset.
5. WHEN the `poll` section is removed THEN the work item SHALL be **first-sight** to the next
   poll cycle, so its thread is re-baselined rather than treated as fully seen.
6. IF the work item has no state at all THEN the system SHALL report that nothing was found
   and exit non-zero, distinguishing "there was nothing to reset" from "reset done" without
   treating it as a crash.
7. WHEN any single piece of state is absent but others are present THEN the system SHALL
   remove what is there and report precisely which pieces it removed.
8. WHEN the reset completes THEN the system SHALL report, per work item, which of the four
   pieces (session, control, poll, workspace) it acted on.

### Requirement 2 — Reset several work items, or all of them

**User story:** As an operator whose bug fix affected everything in flight, I want to reset
more than one work item in a single command, so that recovering from a bad release is one
step rather than one step per ticket.

#### Acceptance criteria (EARS)

1. WHEN `--work-item` is passed more than once THEN the system SHALL reset each named work
   item, in the order given.
2. WHEN `--all` is passed THEN the system SHALL reset every work item this machine holds any
   state for — the union of the session records and the portable records — and no others.
3. IF neither `--work-item` nor `--all` is passed THEN the system SHALL refuse and exit
   non-zero, because a bare `reset` must never mean "reset everything".
4. IF both `--work-item` and `--all` are passed THEN the system SHALL refuse and exit
   non-zero rather than pick one.
5. WHEN one work item in a multi-item run fails THEN the system SHALL continue with the
   remaining ones and exit non-zero at the end, so one broken record cannot strand the rest.
6. WHEN a `--work-item` value is not a valid work-item ref THEN the system SHALL report it and
   exit non-zero without resetting anything, because a typo must not silently select nothing.
7. WHEN the same work item is named more than once THEN the system SHALL reset it once,
   rather than reporting the repeat as "nothing to reset".

### Requirement 3 — Nothing the reset removes may come back on its own

**User story:** As an operator, I want a reset to actually stick, so that the work item does
not quietly return to the state I just cleared.

#### Acceptance criteria (EARS)

1. WHEN a pre-issue-128 state tree still holds a `control` or `poll` entry for the work item
   THEN the reset SHALL leave that work item's record **sealed** rather than deleting the file,
   so the legacy readers cannot resurrect what was just removed.
2. WHEN no legacy tree holds anything for the work item THEN the record file SHALL be removed
   entirely, leaving no empty husk in `portable/`.
3. WHEN a record is removed or sealed THEN the portable index (`portable/index.json`) SHALL be
   rewritten to match, so the directory's index never advertises a record that is gone.
4. WHEN the reset removes state THEN it SHALL write through immediately rather than defer to a
   later flush.

### Requirement 4 — The reset is auditable, and never rewrites the audit trail

**User story:** As an operator debugging *why* a work item behaved oddly, I want the reset
itself to be in the event log, so that "someone reset it" is a visible cause rather than an
unexplained gap.

#### Acceptance criteria (EARS)

1. WHEN a work item is reset THEN the system SHALL emit an event naming the work item, the
   actor who ran the CLI, and which pieces of state were removed.
2. WHEN a reset is requested for a work item with no state THEN the system SHALL emit an event
   recording that too, so a no-op reset is distinguishable from a reset that never ran.
3. WHEN a reset runs THEN the system SHALL NOT delete or rewrite any part of
   `<state.root>/logs/events.jsonl`: the log is append-only, and a command that could erase
   its own trail is not auditable.
4. WHEN `--dry-run` is passed THEN the system SHALL report exactly what it would remove,
   change nothing on disk, and emit no reset event; its exit code SHALL follow the same
   rule a real run's does (zero when it found state to report, non-zero when there was
   nothing), so a rehearsal is scriptable as a question about what is there.
5. WHEN `--dry-run` is passed AND the work item has a live session AND the configuration
   would remove its checkout on close THEN the report SHALL say so, because the checkout
   is the one piece a real run cannot give back.

### Requirement 5 — The dangerous cases are surfaced, not discovered

**User story:** As an operator, I want the command to tell me when a reset is about to be
undone or to have a surprising consequence, so that I find out before it happens rather than
from behaviour a week later.

#### Acceptance criteria (EARS)

1. IF the webhook receiver appears to be running (its pidfile names a live process) THEN the
   system SHALL warn that a daemon holding in-flight poll state can write it back after the
   reset, and recommend stopping it first — while still performing the reset, because the
   operator may have good reason.
2. IF execution control does not require an explicit start
   (`routing.control.requireStartCommand: false`) AND the ingress may spawn on unmatched items
   THEN the system SHALL warn that the work item can be re-spawned by the next poll cycle,
   since clearing the poll section makes it first-sight again.
3. WHEN the reset ends a live session THEN the output SHALL say so explicitly, because ending
   a running agent is the least reversible thing the command does.
4. WHEN a workspace checkout is removed THEN the output SHALL name the removal, since
   uncommitted work in that checkout does not survive it.

### Requirement 6 — It is documented and pinned like every other command

**User story:** As a maintainer, I want the new surface documented and covered by the existing
parity gates, so that it cannot drift the way an undocumented command does.

#### Acceptance criteria (EARS)

1. WHEN a new action is added to an existing command THEN its page under `docs/cli/commands/`
   SHALL document it, so `test_docs_parity.py` P1/P2 continue to hold.
2. WHEN the state layout gains a documented erasure path THEN `docs/cli/state.md` SHALL say how
   each classified path is reset, so the page that tells operators what to back up also tells
   them what to wipe.
3. WHEN the behaviour ships THEN the affected capability docs (`docs/capabilities/cli.md`,
   `docs/capabilities/interactive-sessions.md`) SHALL carry it as current behaviour with a
   history row for issue-137.
4. WHEN the command is added THEN it SHALL be covered by unit tests and by an integration test
   carrying a Gherkin docstring, per `config.testing`.

## Non-functional requirements

- **No new dependency, no new config key.** Reset reuses the stores, the dispatcher close path
  and the event log that already exist (minimalism ladder: reuse before adding). It reads the
  same `routing`/`state` config every other `sessions` action reads and introduces none.
- **Bounded blast radius.** Everything the command writes to or deletes lives under the
  configured state root (or the workspace root the close path already owns). It never writes
  outside them, and never touches the repository's tracked files.
- **Idempotent.** Running reset twice is the same as running it once, except that the second
  run reports "nothing to reset".

## Security considerations

- **Actors & trust:** the only actor is an operator with **shell access to the machine running
  the-loop**. That is the same privilege `sessions stop` already requires and, as
  `commands/sessions_cmd.py` states, is a strictly higher privilege than commenting on an
  issue. There is no new remote actor: reset is not in the control keyword vocabulary, so no
  comment — from an authorized user or anyone else — can trigger it. That is a deliberate
  boundary, not an omission (see design § Security design).
- **Trust boundaries & data:**
  - **argv → filesystem path.** A `--work-item` value decides which files are removed. It
    crosses into a path only through `WorkItemRef.parse` (which rejects anything that is not
    `<provider>:[<host>/]<owner>/<repo>#<number>`) and `WorkItemRef.slug` (which replaces every
    character outside `[A-Za-z0-9._-]`, so no separator survives). The removal targets are then
    built by the existing stores from that slug, inside their own roots — the command never
    joins a caller-supplied string onto a path itself.
  - **State root → deletion.** `--all` enumerates only files the stores themselves recognise as
    records; a stranger's file in a shared directory is not a record and is not removed.
  - **Event log.** The reset writes to the log through `eventlog.emit` only. It has no code path
    that opens the log for anything but appending.
- **Abuse cases (EARS):**
  1. WHEN a `--work-item` value contains path separators, `..`, a leading `-`, or a null byte
     THEN the system SHALL reject it as an invalid ref and remove nothing.
  2. WHEN a `--work-item` value parses but names a work item with no state THEN the system SHALL
     remove nothing and report it, never falling back to a broader match.
  3. WHEN `--all` runs against a state directory containing files the-loop did not write THEN
     those files SHALL be left alone.
  4. WHEN a record on disk is corrupt or unreadable THEN the system SHALL report it and continue
     with the other work items rather than raising.
  5. WHEN a removal fails (permissions, a read-only filesystem) THEN the system SHALL report the
     failure and exit non-zero rather than claiming state was removed.
- **Fail closed:** every ambiguity resolves toward *removing less and saying more* — no
  selector removes nothing (R2.3), an unparseable ref removes nothing (R2.6), `--dry-run`
  removes nothing. The one place fail-closed points the other way is the `control` section:
  removing it **disarms** the work item, which is the safe direction (a reset item waits for an
  explicit start rather than resuming on its own).
- **Risk tier: 3, not 4.** The command deletes operator state, which invites a higher tier, but
  the deletion is local, bounded to the state root, and every piece is rebuildable: the poll
  ledger rebuilds by re-baselining, the session handle by spawning, the control record by a
  `start`. The one genuinely irreplaceable thing in scope — uncommitted work in a workspace
  checkout — is removed by the **existing** close path under the **existing**
  `routing.workspace.keepCheckoutOnClose` policy, which this work item does not change. No
  sensitive path (`autonomy.sensitivePaths`) is touched: no schema, no workflow, no config
  file. Tier 3 is `human-approves-pr`, which this change gets.

## Out of scope

- **Resetting the work item's *spec* state.** `docs/specs/<id>/graph-state.json`, the spec
  artifacts and the phase label live in the **repository**, under version control, on the work
  item's branch. They are the agent's and the reviewer's record, `GraphState.reconstruct()`
  re-derives the current node from the artifacts anyway, and a CLI that rewrote a checked-in
  file as a side effect of local maintenance would be a much larger surprise than the one this
  work item removes. A reset clears the-loop's own memory; the repository's history is the
  repository's.
- **Erasing event-log history.** Deliberately impossible (R4.3).
- **A `reset` control keyword.** Adding one would let a *comment* delete local state, widening
  the comment trust boundary for a maintenance action whose whole audience already has a shell
  on the machine.
- **Restarting the item after the reset.** `sessions start` already does that, and keeping them
  separate means a reset never begins something the operator did not ask for.
- **Selecting by status or age** (`--status closed`, `--older-than`). YAGNI; the issue asks for
  one item, several, or all.

## Open questions

None blocking. The scope, the four pieces of state and the two warnings were stated on the
ticket before the spec was written
([#137 comment](https://github.com/MadaraUchiha-314/the-loop/issues/137#issuecomment-5173461655)),
together with the two assumptions this spec proceeds under: a reset is local maintenance rather
than a control action, and `--all` must be asked for explicitly.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed: an approval never silently
> discards a reviewer's suggestions, and the feedback travels with the document
> it concerns rather than living in a side-channel tracker.
