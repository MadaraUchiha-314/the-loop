---
type: bugfix
phase: requirements-definition
workItem: issue-119
status: approved
approvedBy: []
severity: high
collaborators: [engineer]
overrides: {}
---

# Bugfix spec: a start command that predates first sight is silenced by its own baseline

> Phase 1 of 3 for a bug (bugfix → design → tasks). Human approval for this
> tier-3 change happens at the PR (`autonomy.tiers."3": human-approves-pr`).

## Summary

On the **poll** (pull) ingress, a labelled work item whose
`the-loop:start-execution` comment already exists the first time the poller sees
it is **never started**. The item is armed by the label, the operator has asked
for it to run, and every subsequent cycle logs `spawns: 0` forever.

The two mechanisms are individually correct and collide:

- `_awaiting_start` (issue-106) refuses to arm a presence event while no start
  has been recorded — right, because a presence event would be refused by the
  dispatcher anyway and would burn the issue-80 retry budget;
- first-sight baselining (issue-34) marks the **whole existing thread** seen,
  because a spawned session reads the thread itself and the webhook path only
  ever delivers events *going forward*.

`_awaiting_start`'s design note says the start "still gets through: it arrives as
an ordinary comment event". That holds only when the start comment arrives
**after** first sight. When it predates first sight, the baseline swallows it:
it is in `seenComments`, so it is never a candidate, never forwarded, never
parsed by the dispatcher, and the `ControlStore` never records a `start`. The
item is armed-but-unstartable, and nothing short of a *new* comment (or
`the-loop sessions start`) recovers it.

The webhook ingress does not have this hole because the label and the comment are
two separate deliveries, each processed live. The poller collapses "the item
appeared" and "the comments it already had" into one first sight, losing the
ordering the webhook path gets for free.

## Steps to reproduce

1. CLI config: `polling` enabled with a GitHub source, `spawnOnUnmatched:
   labeled`, `control.requireStartCommand: true` (the default), the operator in
   `routing.authorizedUsers`.
2. On an issue the poller has **not** yet seen, add the auto-execute label **and**
   comment `the-loop:start-execution` before the next poll cycle — e.g. label an
   existing issue that already carries the comment, or add both between cycles.
3. Let the poller run.

**Observed:** the first cycle logs first sight and `spawns: 0`; `poll-state.json`
lists the start comment under `seenComments`; `<registryDir>/control/` is never
written; every later cycle logs `spawns: 0`. Observed on a real issue: comment
posted `16:47:24Z`, first polled `16:47:26Z`.
**Expected:** the poller reads the start that is already on the thread and the
work item starts — the same outcome the webhook path gives, and the same outcome
posting the identical comment one cycle later gives.

## Expected vs actual

- **Expected:** WHEN an authorized user's control command is already on a work
  item's thread the first time the poller sees that item THEN the command SHALL
  be honoured, exactly as if it had been posted one cycle later.
- **Actual:** first-sight baselining resolves every existing comment, including
  control commands nobody has processed, so the command is discarded unread and
  the item can never leave the armed-but-unstarted state.

## Root cause (confirmed)

`cli/the_loop/poller/poller.py`, `_process_item`, the first-sight branch:

```python
if first_sight:
    if item_authorized and not has_session:
        self._try_spawn(...)                      # _awaiting_start() -> returns
    self.state.baseline_comments(ref, live_ids, _utcnow())
    return
```

`_try_spawn` → `_awaiting_start` returns True (`control.require_start_command`
is on and `ControlStore.start_requested(ref)` is False), so no presence event is
emitted — correct. `baseline_comments(ref, live_ids, …)` then writes **every**
live comment id into `seenComments`. On the next cycle the item is known and the
candidate filter is `comment.id not in seen`, so the start comment is skipped.
It is never handed to `Dispatcher.handle`, which is the only place
`parse_command` runs and the only writer of the `ControlStore`. Since
`start_requested` stays False, `_awaiting_start` keeps refusing: a closed loop.

The baseline is *right* about ordinary comments — replaying a whole thread into a
freshly spawned session is exactly what issue-34 avoided. It is wrong about
**control commands**, which are instructions to the-loop itself rather than agent
input, and which the spawn gate depends on having read.

## Acceptance criteria (EARS)

### Read the control commands the thread already carries

1. WHEN the poller sees a work item for the first time AND its thread already
   carries an unambiguous control command from an authorized user THEN that
   comment SHALL NOT be baselined as seen; it SHALL be processed through the
   ordinary comment path instead. (AC1)
2. WHEN such a first sight happens THEN the deferred control comments SHALL be
   handled on **that same cycle** (no extra poll interval of latency), in the
   order the provider lists them, so the **last** command on the thread is the
   one the `ControlStore` ends up holding — a thread carrying `start` then
   `stop` leaves the item disarmed. (AC2)
3. WHEN a labelled item is first seen with a pre-existing authorized
   `the-loop:start-execution` comment THEN a session SHALL be spawned for it
   (via the dispatcher's control path, which records the `start` first). (AC3)

### Change nothing else about first sight

1. WHEN a first-sight thread carries **no** unprocessed control command THEN the
   whole thread SHALL be baselined and no comment SHALL be forwarded — the
   pre-existing behaviour, unchanged. (AC4)
2. WHEN a first-sight thread carries control commands THEN every **other**
   comment on it SHALL still be baselined (never forwarded), so a spawned session
   is not fed the thread it can read itself. (AC5)
3. A comment SHALL NOT be deferred when it is unauthorized, self-authored (the
   `<!-- the-loop:agent-comment -->` marker), carries two conflicting keywords
   (`control.ambiguous`, which executes nothing anyway), or when
   `routing.control.enabled` is false. Each SHALL be baselined as it is today.
   (AC6)
4. WHEN the work item's own author is not authorized THEN nothing on its thread
   SHALL be deferred or forwarded — the existing item-level authorization guard
   is unchanged. (AC7)
5. WHEN the work item **already has a control record** THEN nothing on its thread
   SHALL be deferred: a first sight may *bootstrap* control state, never replay
   over state the-loop has already recorded. (AC11)

### Do not double-spawn

1. WHEN control comments are deferred on first sight THEN the arming decision
   for that cycle SHALL be taken **exactly once** — on the ordinary comment path,
   after the commands have been forwarded — rather than a first-sight presence
   event being emitted *in addition* to it. (AC8)

### Regression coverage & documentation

1. The fix SHALL include a regression test that fails before it and passes
   after, driving a **real** `Dispatcher` + `ControlStore` through a first sight
   whose thread already carries the start keyword, asserting a session is
   spawned. (AC9)
2. The behaviour SHALL be recorded in the affected capability doc
   (`docs/capabilities/webhook-triggers.md`) in the same PR. (AC10)

## Out of scope

- **Changing `_awaiting_start`.** Not arming presence for an unstarted item is
  correct and stays; this fixes the assumption it rests on, not the gate.
- **Replaying ordinary comments on first sight.** The baseline exists for a
  reason (issue-34); only control commands — instructions to the-loop, not agent
  input — are exempted.
- **A poll-side control parser with its own authority.** The dispatcher stays the
  single place that parses, authorizes, applies and records a command. The poller
  only decides *which* comments are still unprocessed.
- **The webhook path.** It never had this defect (label and comment are separate
  deliveries) and is untouched.
- **Retro-fixing already-baselined items.** An item whose start was swallowed
  before this fix stays baselined; the documented workarounds (a fresh comment,
  or `the-loop sessions start`) still apply, as does deleting its entry from
  `poll-state.json`.

## Security considerations

**No new attack surface. One new read of comment text, on the poller side, whose
only output is a set of comment ids.**

- **Untrusted actors / trust boundary.** The boundary is unchanged: comment text
  may cause a *daemon action* only through `Dispatcher.handle`, which parses the
  fixed keyword vocabulary, re-checks for a **named** authorized actor and then
  applies one of four constants. This change does not move that boundary — it
  only stops the poller from discarding a comment before the boundary is reached.
- **The poller's new read is a filter, not an authority.** `parse_command` is
  pure and side-effect free; the poller uses its result solely to decide whether
  a comment id is baselined now or forwarded. It records no control state, spawns
  nothing directly, and no text from the body reaches an argv, a path, a prompt
  or a work-item ref.
- **Fail closed, and no widening of who is heard.** A comment is deferred only
  when it passes the *same* guards the known-item forward path already applies:
  `is_authorized(comment.author, authorizedUsers)` (empty allowlist ⇒ nobody) and
  not `is_self_authored`. An unauthorized or self-authored comment carrying the
  start keyword is baselined exactly as today — it is not deferred, not
  forwarded, and cannot start anything (AC6). The item-level author guard is
  applied first, unchanged (AC7).
- **Abuse case A1 — a stranger's start comment.** A start keyword from a login
  outside `authorizedUsers` on a first-sight thread must not defer, forward or
  start anything. Negative test.
- **Abuse case A2 — the-loop's own comment.** A self-marked body carrying a
  keyword (the CLI posts exactly this shape, `control.command_comment`) must not
  be deferred: it was already applied locally, and re-applying it is the
  loop-prevention failure issue-104 closed. Negative test.
- **Abuse case A3 — an unarmed item.** Deferring changes nothing about arming: a
  start on an item the spawn policy does not arm is still refused by
  `_spawn_refusal` (`spawn-policy`) and, per the issue-106 asymmetry, leaves
  nothing standing.
- **Bounded.** The scan is one regex pass over the comments of one item, already
  fetched for this cycle; the deferred set is a subset of `live_ids`, which is
  itself capped by `_SEEN_COMMENTS_CAP` on write. No new I/O, subprocess,
  credential or network call.
- **Fail-safe on the state file.** Deferring means "not yet baselined", so a
  crash between cycles re-reads the same comment next time; the dispatcher's
  delivery dedup and the issue-80 retry budget bound the repeat, exactly as for
  any other forwarded comment.

## Open questions

None. The reporter's diagnosis is exact and names both viable fixes; `design.md`
records why the second ("don't baseline an unprocessed start comment") is taken.
