# Decision 050: a reset erases the-loop's memory of a work item, and nothing else — and it is not a control verb

- **Status:** proposed
- **Date:** 2026-08-04
- **Deciders:** @MadaraUchiha-314 (issue #137)
- **Work item:** issue-137
- **Spec:** `docs/specs/issue-137/`
- **Builds on:** [decision-040](decision-040.md) — the four-verb control vocabulary this
  deliberately does **not** join — and [decision-046](decision-046.md), whose
  portable/local split is what makes "which of it goes?" answerable at all.

## Context

Issue #137 comes from dogfooding: *"when we find a bug in the-loop and fix the-loop's CLI,
once the CLI is released we need a way to reset the progress for a work item."*

The CLI remembers a work item in four places, and every one of them survives an upgrade —
the session record, the `control` section, the `poll` section, and the workspace checkout.
That memory is the point right up until the code that created it was wrong. Then it is the
obstacle: the item is holding a conversation the old CLI started, a ledger saying every
comment on the thread is handled, and a record saying it is armed.

Nothing erased it. `sessions stop` ends the session and leaves a **closed** record and the
whole poll ledger, so the item is still known and its thread still baselined. Deleting the
files by hand — the actual workaround — is booby-trapped: dropping `portable/<slug>.json`
lets the pre-issue-128 readers hand the old `start` straight back, so the item returns
*armed*.

Three questions had to be answered, and they are what this record is for: how far the
erasure reaches, who may ask for it, and what happens to the trail.

## Decision

**`the-loop sessions reset` erases everything the-loop's CLI holds about a work item on
this machine — through the erasure paths that already exist — and nothing else. It is an
operator command, not a control verb.**

1. **Scope: the-loop's memory, not the work item's record.** The session record is
   deleted, the `control` and `poll` sections cleared, and the checkout removed per the
   existing close policy. The **repository** is untouched: `docs/specs/<id>/graph-state.json`,
   the spec artifacts and the phase label are checked in on the work item's branch, are the
   reviewer's record as much as the agent's, and `GraphState.reconstruct()` re-derives the
   current node from the artifacts anyway. A CLI that rewrote tracked files as a side effect
   of local maintenance would be a larger surprise than the one being removed.
2. **Composition, not a second teardown.** A live session ends through
   `Dispatcher.close_session` — the path a merge, a stop keyword and `sessions stop` all
   take — so tmux retention, harness termination and workspace policy behave identically
   however a session ends. The portable sections are cleared through
   `WorkItemStore.write_section(..., None)`, whose seal-vs-delete rule is precisely what
   stops the legacy resurrection. The only new primitive is `SessionRegistry.forget`.
3. **Deleted, not closed.** A closed record still lists and is still `attach`-able; that
   *is* the "the CLI still remembers this" the reset exists to end.
4. **No `reset` keyword, and no comment.** The four control verbs are a *comment*
   vocabulary that happens to have a CLI half. Reset is the reverse: shell-only, with no
   comment ingress. Adding a keyword would let a comment delete local state — a new trust
   boundary for a maintenance action whose entire audience already has a shell on the
   machine. And the honest comment has nothing to say to the ticket's readers: posting
   `stop-execution` would assert durable intent the reset has just **cleared**, leaving the
   thread contradicting the disk.
5. **The event log is the trail, and it is append-only.** Every reset appends one
   `session.reset` — including a reset that found nothing — and nothing in the command can
   rewrite or truncate the log. A command that could erase its own trail is not auditable.
6. **The dangerous readings must be typed.** A bare `reset` is a usage error, never "reset
   everything"; `--all` is explicit; one invalid ref resets none of them; `--dry-run`
   rehearses. Where a reset can be undone (a running daemon) or surprise (a config that
   re-spawns first-sight items), the command **warns and proceeds** — an operator may
   legitimately reset one item while the daemon serves others, and a refusal would only be
   routed around by a `--force` that means less.

## Consequences

**Positive.**

- The dogfooding loop closes: fix the CLI, release, reset, start again — without `rm`, and
  without the resurrection trap that hand-deletion carries.
- Recovering from a bad release across everything in flight is one command.
- Reset inherits every close-path behaviour for free, and cannot drift from it.
- Clearing `control` **disarms**, so the failure mode of a half-understood reset is an item
  that waits rather than one that runs.

**Negative / accepted costs.**

- **A retained tmux session outlives its record.** With `keepSessionOnClose` (the default)
  the transcript is kept, but `sessions attach --work-item` can no longer find it — the
  record is gone. It is reachable as `tmux attach -r -t loop-<slug>`, and documented as
  such. Accepted: killing a transcript is more destructive than orphaning it, and a reset
  is not the place to make that call for the operator.
- **Uncommitted work in a checkout is not recoverable.** This is the existing close policy,
  not a new one; the reset gives it its own output line rather than hiding it in a list.
- **Resetting under a running daemon can be partly undone.** A warning, not a lock: a lock
  would need the daemon's cooperation to be correct, and would still be wrong the moment
  the operator has two.
- **A reset does not restart the item.** Deliberate — `sessions start` does, and keeping
  them apart means a reset never begins something nobody asked for.

## Alternatives considered

| Option | Why not |
|---|---|
| Add `reset` to the control keywords | Lets a comment delete local state: a new remote trust boundary for a shell-only maintenance action. The control parser's narrowness (four fixed constants) is a property worth keeping. |
| Post `stop-execution` on the ticket after a reset | Records durable intent the reset just cleared — the ticket would contradict the disk. |
| `unlink()` the portable record | Resurrects a pre-issue-128 record through the legacy readers; the store's `sealed` tombstone is the existing, tested answer. |
| Extend `sessions stop` with `--forget` | Overloads a *control* verb with an erasure whose blast radius is different in kind; `stop` is answerable by comment, and this must not be. |
| A top-level `the-loop reset` | The state is session-keyed and its wiring already lives in `sessions_cmd`; a sibling command would duplicate the store, dispatcher and layout resolution. |
| Also reset `graph-state.json` and the spec artifacts | They are tracked files on the work item's branch, and re-derivable. Local maintenance must not rewrite the repository. |
| Refuse to run while the daemon is up | The operator may legitimately reset a subset; a refusal invites a `--force` that then means "ignore all warnings". |
| A bare `reset` meaning `--all` | The most destructive reading must be the one you have to ask for. |
