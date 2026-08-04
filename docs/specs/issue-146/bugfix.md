---
type: bugfix
phase: requirements-definition
workItem: issue-146
status: approved
approvedBy: []
severity: high
collaborators: [engineer]
overrides: {}
---

# Bugfix spec: a respawn collides with the tmux session it is replacing, and retries the identical collision

> Phase 1 of 3 for a bug (bugfix → design → tasks). Human approval for this
> tier-3 change happens at the PR (`autonomy.tiers."3": human-approves-pr`).

## Summary

With `routing.runner: tmux`, a delivery that finds a work item's tmux session
dead falls back to respawning it (issue-80) — optionally resuming the recorded
conversation first (issue-89). Both halves of that fallback end in
`tmux new-session -d -s loop-<slug>`, and **`loop-<slug>` is a deterministic
name**: if a session already holds it, tmux refuses with
`duplicate session: loop-<slug>` and the dispatch fails. Nothing in the-loop
recognises that error, so the next event takes the identical path and fails
identically. The work item is stuck: every event on the ticket is logged as
`dispatch.failed` and then dropped, even though the session tmux is protecting
is alive and could have handled it.

Two things make the collision reachable in the first place, and one makes it
unrecoverable:

1. **An unanswered liveness probe is read as "the session is gone."**
   `TmuxRunner.has_session` calls `tmux has-session` with a hard-coded 10 s
   timeout and treats *any* non-success as absent — including a timeout, an
   `OSError`, or a tmux that never answered. A busy or attached tmux server is
   exactly the condition the reporter describes ("probe timeout while the pane
   is busy/attached"), and `TmuxRunner.deliver`'s liveness check is built on
   that same call, so a slow server turns a **live** session into
   `session_missing: true` and sends a perfectly healthy work item down the
   respawn path. `new-session` then runs with `routing.dispatchTimeoutSeconds`
   (default 1800 s) rather than 10 s, so it waits long enough to get the real
   answer — `duplicate session`. The 10 s probe and the 1800 s spawn disagree
   about reality, and the spawn is the one that is right.

2. **The pre-flight clear is unchecked and unconditional.** `TmuxRunner.spawn`
   does check `has_session` and kills a leftover before spawning, but it
   (a) **ignores the result of `kill-session`**, so a clear that failed still
   proceeds into `new-session` and the collision, and (b) kills whatever it
   finds — including a session whose **harness is still running**. An idle
   detached agent is indistinguishable from a busy one, so the "successful"
   branch of today's code silently destroys a live agent mid-work, and the
   failing branch crash-loops. Neither outcome is acceptable.

3. **`duplicate session` has no handler, and the failure is retryable.**
   `_respawn_tmux` never asks whether the target name is occupied before
   replacing it, `TmuxRunner.spawn` cannot tell a collision from any other tmux
   error, and the resulting `dispatch.failed` releases the delivery id — so the
   poller re-forwards it and the same collision recurs. Per event the poll path
   *is* bounded (`polling.maxRetries`, default 3, issue-80), so this is not
   literally an unbounded loop; the effect is worse than one, because after the
   budget the event is baselined as resolved and **lost**. Every subsequent
   event repeats the cycle, which is what "retrying every ~60s for 90+ minutes
   across restarts … no progress" looks like from the outside.

Tracked as [issue #146](https://github.com/MadaraUchiha-314/the-loop/issues/146).

## Steps to reproduce

1. Run `the-loop poll start` (or `gh-webhook start --route`) with
   `routing.runner: tmux` against a work item that has a live, registered tmux
   session (`tmuxTarget: loop-<slug>`).
2. Make the liveness probe fail while the session is alive — e.g. load the tmux
   server so `tmux has-session` exceeds its 10 s probe timeout, or (equivalently
   for the collision) leave a session holding `loop-<slug>` that `kill-session`
   cannot clear.
3. Post a comment on the work item.
4. Delivery reports `session_missing`; the dispatcher respawns. `tmux
   new-session -d -s loop-<slug>` exits 1 with `duplicate session: loop-<slug>`.
5. `session.resume_failed` + `dispatch.failed`; the delivery id is released.
6. Every later cycle and every later event repeats steps 3–5 identically.

## Expected vs actual

- **Expected:** before falling back to `tmux new-session`, the-loop checks
  whether a session already holds the target name. A session whose harness is
  **still running** is never spawned over — the pending event is delivered into
  it, which is what the operator wanted all along. A **dead/retained** leftover
  is cleared, and the clear is *verified* before spawning. If tmux reports
  `duplicate session` anyway, that is treated as authoritative and resolved
  once — not repeated. When no progress is possible the dispatch is recorded as
  **skipped** (not released for retry), so the same collision cannot be
  re-attempted forever.
- **Actual:** an unanswered probe is read as "gone"; the pre-flight clear is
  unchecked and kills live sessions; `duplicate session` is an unrecognised
  generic error; the dispatch is released for retry and the identical failure
  recurs until the event's budget is spent and it is dropped.

## Root cause (confirmed by reading the code)

| # | Site | Defect |
|---|------|--------|
| C1 | `runner.py: has_session` | `_run` failure (timeout / `OSError` / tmux missing) is indistinguishable from tmux answering "no such session", and both return `False`. `has_live_session` documents a deliberate *fail-live* bias for the unreadable-pane case but inherits fail-**gone** from this call, contradicting its own contract. |
| C2 | `runner.py: spawn` | The `kill-session` result is discarded; execution continues into `new-session` regardless. |
| C3 | `runner.py: spawn` | A leftover is killed whether or not its harness is alive — a live agent is destroyed on the path that "works". |
| C4 | `runner.py: spawn` | `duplicate session` is returned as an opaque error string; nothing re-probes or retries. |
| C5 | `dispatcher.py: _respawn_tmux` | Replaces the session without ever asking whether the target name is occupied. |
| C6 | `dispatcher.py: _respawn_tmux` | Every failure is `dispatch.failed` + `deduper.discard(...)`, i.e. "retry me", including failures that can only recur. |

## Acceptance criteria (EARS)

### Probing a tmux session

1. WHEN the-loop probes a tmux session AND tmux **answers** (any exit status)
   THEN the system SHALL use that answer; WHEN tmux does **not** answer (probe
   timeout, `OSError`, binary missing) THEN the system SHALL treat the session's
   state as **unknown** and SHALL NOT report it as absent. (AC1)
2. WHEN a delivery's liveness probe is unknown rather than a definite
   "absent"/"dead" THEN the system SHALL NOT report `session_missing`, so an
   unanswered probe cannot trigger a respawn of a live session; the delivery
   fails and is retried as an ordinary transient fault instead. (AC2)

### Spawning against an occupied name

1. WHEN a spawn is asked for a `loop-<slug>` name whose session is **live** (its
   harness is still running) THEN the system SHALL NOT kill it and SHALL NOT
   spawn over it, and SHALL report the collision distinguishably (a session
   already exists; it is live). (AC3)
2. WHEN a spawn is asked for a name held by a **dead/retained** session THEN the
   system SHALL clear it and SHALL verify the clear before spawning; WHEN the
   clear cannot be verified THEN the system SHALL report the collision rather
   than proceeding into `new-session`. (AC4)
3. WHEN `tmux new-session` fails with `duplicate session` — the collision the
   pre-flight probe missed — THEN the system SHALL re-decide from tmux's own
   answer (live occupant → report it; clearable leftover → clear and retry the
   spawn **exactly once**) and SHALL NOT retry indefinitely. (AC5)

### Recovering the pending event

1. WHEN a respawn is about to start AND the work item's tmux session is in fact
   **live** THEN the system SHALL deliver the pending event into that session
   instead of respawning, mark the delivery processed, and record the averted
   respawn distinguishably from a real one. (AC6)
2. WHEN a spawn on the respawn path reports a **live** occupant THEN the system
   SHALL likewise deliver the pending event into it rather than failing. (AC7)
3. WHEN a collision is with an occupant that is **not** live and cannot be
   cleared THEN the system SHALL record the dispatch as **skipped** — an
   observable, non-retryable outcome that does **not** release the delivery id —
   rather than a failure that will be re-attempted. (AC8)
4. WHEN a respawn fails for any other reason THEN behaviour SHALL be unchanged:
   `dispatch.failed`, delivery released for retry (issue-80). (AC9)

### Observability

1. An averted respawn and a skipped-because-occupied dispatch SHALL each be
    visible in `the-loop events` under their own type/reason, distinct from
    `session.respawned`, `session.resume_failed` and a transient
    `dispatch.failed`. (AC10)

### Picking up items already stranded (owner follow-up, [comment](https://github.com/MadaraUchiha-314/the-loop/issues/146#issuecomment-5175052576))

1. WHEN the poller processes a work item whose ledger records comments
    **abandoned by a spent retry budget** AND that give-up was recorded by a
    *different* CLI version than the one running THEN the system SHALL
    un-resolve those comments exactly once, with a fresh retry budget, and emit
    an observable record — so an item stranded by a bug an upgrade fixed is
    picked up on the next cycle instead of staying stuck forever. A give-up
    recorded by the *running* version SHALL NOT be re-armed, so `poll --once`
    from cron cannot re-forward abandoned comments every minute. (AC11)

### A killed tmux session keeps its conversation (owner follow-up)

1. WHEN the registry holds an **active** tmux-mode session whose tmux session
    has been killed THEN the next event for that work item SHALL respawn a fresh
    tmux session under the same `loop-<slug>` name running the **same** harness
    conversation (`claude --resume <recorded harnessSessionId>`), and the
    registry SHALL keep that id. This is issue-89 behaviour that issue-146 was
    breaking; it SHALL be regression-tested here. A harness with no interactive
    resume (anything but Claude Code) SHALL keep falling back to a fresh
    conversation with `session.resume_failed`. (AC12)

## Out of scope

- **Recovering comments abandoned *before* this change shipped.** AC11 records a
  give-up so it can be re-armed; a give-up already in a ledger carries no such
  record and is indistinguishable from a delivered comment, so it is not
  recovered. Replaying every seen comment on an upgrade to catch it would
  re-forward whole threads. What un-sticks an already-stranded item is the
  collision fix itself — the next event on it lands.
- **A proactive recovery sweep at daemon start.** AC11 un-sticks the *ledger*;
  healing the session stays reactive, driven by the re-forwarded event on the
  next cycle. A sweep would have to invent a boot prompt for a session nobody
  asked anything of, where the re-armed event is a real one — and it would
  duplicate the delivery/respawn path that already works.
- **Re-arming a given-up *spawn*.** Items stranded by this bug have a registered
  session (the collision is *with* it), so the poller never armed a spawn for
  them; `spawn.gaveUp` is not what strands an issue-146 victim. Left alone rather
  than re-armed speculatively.
- **Adopting an orphaned live session on the first-spawn path.** When a *live*
  session holds `loop-<slug>` but the registry has no session for the work item
  (a lost/reset registry, or `killHarnessOnClose: false` on a closed item), the
  first-spawn path (`_spawn_tmux`) will now **fail loudly** with an actionable
  error instead of killing the occupant. Registering the-loop against a session
  it did not spawn — inheriting a harness id it does not know — is a separate
  enhancement; refusing to destroy a running agent is the fix here, and the
  operator's remedy (`tmux kill-session -t loop-<slug>`, or
  `the-loop sessions reset`) is named in the error.
- **Retry backoff.** The issue notes "no backoff". Backoff is the wrong lever
  for a deterministic collision — slowing an identical failure down does not
  make it heal. Retry *accounting* already exists (`polling.maxRetries`); this
  work removes the recurrence and gives the unrecoverable case a non-retryable
  outcome instead.
- **Proactive tmux health monitoring.** Recovery stays reactive, driven by a
  delivery or a poll cycle (unchanged from issue-80).
- **Making the probe timeout configurable.** The fix is to stop
  *misinterpreting* an unanswered probe, not to tune how long it waits.

## Security considerations

No new attack surface, and one destructive capability **narrowed**.

- **Trust boundaries unchanged.** Every decision this work adds is taken from
  tmux's own answers about a session name the-loop itself minted
  (`target_for(work_item)` → `loop-<slug>`) plus the session registry (a local
  file the-loop wrote). No event payload, comment body, or other untrusted input
  reaches a tmux argv, a path, or a spawn decision. The event still travels
  through the same template that frames the payload as untrusted data, and the
  upstream authorized-actor guard is untouched.
- **Fewer destructive operations, not more.** The one privileged action in this
  path — `tmux kill-session` — becomes *conditional* (dead/retained occupants
  only) where it was unconditional, so a live harness can no longer be destroyed
  by a mis-read probe. The existing `_LOOP_TARGET_RE` guard on signalling pane
  pids is unchanged, and the names passed to `kill-session` are still only
  `target_for()` output, never a registry-supplied string.
- **Fail-closed under uncertainty.** An unknown probe result no longer licenses
  a replacement spawn; the ambiguous cases degrade to "retry the delivery" or
  "skip, loudly", never to "kill and recreate". The one retry this work adds
  (after a `duplicate session`) is bounded to a single extra attempt in code, so
  it cannot become a spawn amplifier, and the skipped outcome deliberately does
  **not** release the delivery id — removing, rather than adding, a way for a
  hostile or crashing session to induce repeated harness spawns.
- **No new secrets, files, network calls, or config surface.**

## Open questions

None. The issue states the expected behaviour ("check whether a session with
that target name already exists … attach/route the event into it instead of
spawning, or otherwise skip respawn and just mark dispatch as skipped"); this
spec follows it, and resolves the one place it leaves open (live vs. dead
occupant) by routing into a live one and skipping only when the occupant is dead
and unclearable.
