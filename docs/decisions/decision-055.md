# Decision 055: the-loop never spawns over a live `loop-<slug>` — it routes into it

- **Status:** proposed
- **Date:** 2026-08-04
- **Deciders:** @MadaraUchiha-314 (issue #146)
- **Work item:** issue-146
- **Spec:** `docs/specs/issue-146/`
- **Refines:** [decision-021](decision-021.md) (the tmux runner and its deterministic
  session names), and the recovery paths issue-80 / issue-89 built on it

## Context

Issue #146: the respawn fallback ends in `tmux new-session -d -s loop-<slug>`, and
`loop-<slug>` is derived from the work item, so it is always the *same* name. When a
session already held it, tmux refused with `duplicate session: loop-<slug>`, the dispatch
failed, the delivery id was released, and the next cycle did the identical thing. The work
item was stuck with every event on it logged as a failure and then dropped — while the
session tmux was protecting was alive and could have handled them.

`TmuxRunner.spawn` did have a pre-flight check, and that made it worse rather than better:
it read `has_session` as "does it exist", where `has_session` returned `False` both when
tmux answered "no such session" **and** when tmux never answered at all (a 10-second probe
timeout against a busy or attached server — while `new-session` behind it waits
`dispatchTimeoutSeconds`, default 1800, and therefore gets the real answer). And when the
check *did* see a session, it killed it unconditionally, without even reading whether
`kill-session` worked. So the two possible outcomes were: crash-loop, or silently destroy
a live agent mid-work. An idle detached agent looks exactly like a busy one.

Three questions had to be answered, and only the third is really a decision: how to read a
probe tmux did not answer; what to do about an occupant; and who wins when tmux and our own
probe disagree.

## Decision

**`loop-<slug>` belongs to the work item, so an occupant of it is always that work item's
own agent. A live occupant is therefore never something to destroy — it is something to
talk to.**

Concretely:

1. **An unanswered probe is `unknown`, never `absent`.** `session_state` classifies from
   tmux's *exit status* (absent only when tmux answered), so a timeout, an `OSError` or a
   missing binary is its own state. `has_live_session` reads `unknown` as **live** — the
   bias its docstring already claimed — so a delivery attempts the paste and fails
   transiently if the session really is gone, rather than respawning over one that is
   running.
2. **A live occupant is never killed and never spawned over.** On the respawn path the
   pending event is delivered into it (`session.respawn_averted`). On the first-spawn path,
   where there is no registered session to deliver into, the spawn fails **loudly** with
   the operator's remedy rather than reclaiming the name.
3. **Only a definite "every pane is dead" licenses `kill-session`**, and the clear is
   verified (a failed kill against a session that is nonetheless gone counts as cleared).
   An unclearable dead occupant **skips** the event — `dispatch.dropped`,
   `reason: session-occupied`, delivery id deliberately kept — because releasing it is what
   made the identical collision recur.
4. **tmux wins a disagreement.** A `duplicate session` refusal is authoritative: re-decide
   from a fresh probe and spawn at most **once** more. Never a loop.

And, as the recovery half (owner follow-up on the ticket): **a give-up is recorded with the
CLI version that made it, and a different version re-arms it once.** An item stranded by
this bug had its events abandoned and baselined indistinguishably from delivered ones, so
the fix alone would have left it stuck forever.

## Consequences

- The crash-loop cannot start (a busy probe no longer triggers a respawn) and cannot
  persist (a collision is resolved, routed into, or skipped — never re-attempted
  identically).
- **A live agent can no longer be destroyed by a mis-read probe.** This is the quieter half
  of the fix: the branch that "worked" before was killing running sessions.
- `kill-session` — the one destructive operation on this path — is strictly more
  constrained than it was: gated on a definite dead-pane reading instead of unconditional.
- A from-scratch spawn against a live orphan now **fails** where it used to reclaim the
  name. That is deliberate, and it is loud: the log names `tmux kill-session -t
  loop-<slug>` and `the-loop sessions reset`. It only arises with
  `killHarnessOnClose: false` or a lost/reset registry, and in the former case refusing to
  kill is what the operator asked for. *Adopting* such a session (registering the-loop
  against a harness whose id it does not know) is deliberately out of scope.
- One extra tmux round-trip on the respawn path only — never on the happy path.
- An upgrade re-forwards comments an older version abandoned. Bounded (one full budget,
  once per version) and version-gated so `poll --once` from cron cannot loop on it.

## Alternatives considered

- **Keep killing the occupant, just check the kill succeeded.** Fixes the crash-loop and
  keeps the data-loss bug. Rejected.
- **Spawn under a suffixed name (`loop-<slug>-2`).** Abandons the deterministic name the
  registry, the announced attach command, `sessions attach` and `_LOOP_TARGET_RE` all rely
  on, and orphans the original. Rejected.
- **Exponential backoff on the failing dispatch.** The collision is deterministic; backoff
  makes an unhealable failure slower, not healable. Rejected in favour of removing the
  recurrence.
- **Make the probe timeout configurable.** Treats the symptom — a longer timeout still
  eventually mis-reads a loaded server. Rejected; the fix is to stop reading silence as
  absence.
- **Re-arm abandoned comments on every poller start** (rather than per version). Would
  re-forward them every minute under `poll --once` from cron. Rejected.
