# Decision 040: the auto-execute label arms a work item; an authorized user's explicit command starts it

- **Status:** proposed
- **Date:** 2026-07-26
- **Deciders:** @MadaraUchiha-314 (issue #106)
- **Work item:** issue-106
- **Spec:** `docs/specs/issue-106/`
- **Refines:** [decision-031](decision-031.md) (the self-comment marker — now
  load-bearing for *commands*, not just prompts) and the authorized-actor guard
  introduced with [decision-032](decision-032.md)'s CLI config
  (`routing.authorizedUsers`).

## Context

Issue #106: *"The auto-execute label is a necessary but not a sufficient
condition. Any action that the-loop has to forward to the agent harness has to
come from an authorized user."*

Before this, the daemon had two gates:

- **who** — `routing.authorizedUsers`: an action authored by anyone else is
  ignored on both ingress paths (fail closed on an empty list);
- **which** — `routing.autoExecuteLabel`: only labelled work items may spawn.

Nothing said **when**. Labelling an issue *was* the trigger, so the label could
not express "this is ready to be worked, but not yet", and there was no way to
hold a running session off, or to stop one, short of `sessions close` (which
discards the conversation) or killing the daemon. Symmetrically, a comment could
only ever become **harness input** — text the agent reads and interprets —
because nothing in a thread was addressed to *the-loop itself*.

## Decision

1. **Declare a fixed control vocabulary** in the CLI config
   (`routing.control.keywords`), defaulting to `the-loop:start-execution`,
   `the-loop:stop-execution`, `the-loop:pause-execution` and
   `the-loop:resume-execution`. An **authorized** user's comment carrying one is
   *executed by the-loop* and never forwarded to the harness.
2. **Demote the label to "necessary but not sufficient"**:
   `routing.control.requireStartCommand` defaults to **true**, so a labelled work
   item is armed and spawns only once the start command has been issued — on
   either ingress path, and under `spawnOnUnmatched: always` as well.
3. **Make the request durable**: the last command per work item is recorded beside
   its session (`<registryDir>/control/`), so a start survives a daemon restart
   (and a retried spawn), while a `stop`/`pause` disarms the item again.
4. **Add `paused` as a session status** — delivery suppressed, conversation and
   tmux session intact — alongside `active` and `closed`.
5. **Give the CLI parity with the keywords** (`the-loop sessions start|pause|
   resume|stop`), each posting the *same keyword* back to the work item, marked as
   the-loop's own so the daemon never reads its own action back.
6. **Put everything the CLI generates under one configured root** (`state.root`),
   with the session-related tracking together under `<root>/sessions/`.

### Why the default is `true` (the behaviour change)

It is a behaviour change for existing operators: labelling an issue no longer
starts a session by itself. We chose it anyway, because the issue is a *security*
issue and the safe default is the one that fails closed. The label is a
low-friction, sticky, widely-writable signal — anyone with triage rights can add
it, it survives on the issue forever, and it says nothing about *now*. Requiring
an explicit, timestamped, attributable command from an allowlisted user makes
"who started this autonomous run, and when?" answerable from the event log, and
makes an accidental label a no-op instead of an agent. `requireStartCommand:
false` restores the previous behaviour in one line, and both daemons say so at
startup.

### Why parsing lives downstream of the existing guards

Control parsing happens in the dispatcher, **after** the router/poller have
dropped self-authored comments (issue-104) and unauthorized actors (issue-63). So
the vocabulary can only ever *add* a condition; it can never become a second,
weaker way in. The parser recognises the configured keywords and returns one of
four constants — no substring of a comment reaches an argv, a path, a prompt
template or a work-item ref (the item acted on is the router's own extraction).

### Why ambiguity is refused rather than resolved

A comment carrying two different keywords executes nothing **and forwards
nothing**. Any precedence rule would have to guess which half of a contradictory
instruction the human meant, on the one surface where guessing wrong starts or
kills an autonomous agent.

## Alternatives considered

- **A second label per command** (`the-loop: paused`). Labels are state, not
  events: they carry no author at the moment of the change that the payload can
  be trusted for, no free-text context, and they are awkward for
  start-then-stop-then-start. Comments are already the paper trail the loop keeps
  everything else in.
- **Default `requireStartCommand: false`** (opt-in tightening). Rejected: it
  leaves the insecure default in place for everyone who does not read the release
  notes, which is the opposite of how every other gate in the-loop is shipped
  (`authorizedUsers` fails closed, `spawnOnUnmatched` defaults to `never`).
- **A dedicated bot account / separate token** so the-loop's own comments are
  distinguishable by author. Still rejected (decision-023's operating model): the
  daemon posts with the operator's own `gh` credentials, and the marker contract
  already solves loop prevention without asking every operator to provision a bot.
- **Letting the CLI's comment be re-read by the daemon** instead of marking it.
  That is the issue-104 loop, now with commands: the daemon would re-apply its own
  action every poll cycle, forever.
- **Migrating the poll-state file** to its new default location on upgrade.
  Rejected as too clever for a file whose loss silently re-forwards every watched
  thread; the poller keeps using a legacy file that exists and warns once instead.

## Consequences

- **Upgrade note (the one breaking change).** With `requireStartCommand: true`, a
  labelled work item waits: comment `the-loop:start-execution` or run `the-loop
  sessions start`. Both daemons log this at startup, and the CLI README carries
  the note.
- The daemon gains a *write* it did not have before on the CLI path (the
  paper-trail comment) — best-effort, behind the operator's own `gh`, skippable
  with `--no-comment`, and consistent with reactions (issue-84) and the session
  announcement (issue-86).
- The event log answers a question it could not before: `control.command` records
  who asked for a run to start or stop, from where, and what it did.
- `find_by_work_item` now means "live" (`active | paused`), which is what makes a
  paused session keep owning its work item — nothing spawns a second session for
  it, and its work item closing still closes it.
