# Decision 046: state is organised by portability — facts about the work travel; handles to a machine do not

- **Status:** proposed
- **Date:** 2026-07-31
- **Deciders:** @MadaraUchiha-314 (issue #128)
- **Work item:** issue-128
- **Spec:** `docs/specs/issue-128/`
- **Builds on:** [decision-040](decision-040.md) — which introduced the control records
  whose durability this makes portable — and issue-106's single `state.root`, which is
  what makes "everything the CLI generates" a set small enough to classify at all.
- **Follows:** the same reasoning that already checks `docs/specs/<id>/graph-state.json`
  into the repository (issue-109): state that must survive a machine change, a session
  change and a multi-day human review belongs in git, provided it is a cache or a
  statement rather than an authority over a local process.

## Context

[Issue #128](https://github.com/MadaraUchiha-314/the-loop/issues/128) asks how to carry
the state of the issues and PRs the-loop is tracking from one machine to another, and
which files to stop git-ignoring to make that work — `poll-state.json` alone, or
`sessions/` and `sessions/control/` too?

Nothing in the documentation could answer it. `state.root` is documented as a config
option — which paths default from it — and the sentence after the table said *"All of it
is git-ignored runtime state"*, which is where the question stopped. The **contents** of
those files, their lifecycles, and whether any of them mean anything on a second machine
were documented nowhere.

The blanket ignore was not merely uninformative, it was wrong in both directions at once:
it excluded two files that cannot be rebuilt, and it invited an operator to fix that by
tracking the directory — which would have carried the one file that must never move.

## Decision

**Everything the CLI generates is one of two kinds of thing, only one of them travels,
and the directory layout says which is which.**

- **Facts about the world** — what GitHub already told us, and what an authorized human
  asked for. True on any machine. **Portable**, and tracked in git:
  - `<state.root>/portable/<slug>.json` — one record per work item, with a `control`
    section (the last `start`/`stop`/`pause`/`resume`, who asked, when) and a `poll`
    section (which comments have been seen, and the retry ledgers).
- **Handles to this machine** — things that exist only where they were created. **Local**,
  and never tracked:
  - `<state.root>/local/<slug>.json` — the session registry.
  - `<state.root>/logs/events.jsonl` — the event log.
  - `<state.root>/gh-webhook.pid` — the receiver pidfile.
  - (and the per-work-item checkouts under `routing.workspace.root`, which are
    regenerable and not under `state.root` at all).

### The layout follows the classification (PR #129 review)

The first version of this decision classified the files but left them where they were —
three stores grouped by **writer** (`sessions/`, `sessions/control/`,
`sessions/poll-state.json`). The owner's question on the pull request was the right one:
*do we need so many files and folders?* Not for these reasons, no. Grouping by writer is
what forced a `.gitignore` recipe with two negations and an ancestor rule to express one
idea, and it is why "what is happening with #15?" meant looking in three places.

So the layout is the classification: **two directories, one file per work item in each.**
Three consequences beyond the tidiness — the recipe is three lines with no negations; the
single `poll-state.json` (the one file two machines were guaranteed to conflict in) becomes
per work item, so they collide only over an item they both worked; and a cycle writes only
the records it touched.

What did **not** change is why each store exists. The session registry and the control
records are not derivable from GitHub and are not optional: they survive a daemon restart,
and they are the IPC between the `the-loop sessions …` CLI and the daemon, which are
separate processes.

Three further consequences follow, and are accepted as part of the decision:

1. **The classification is declared in code** (`the_loop.state.GENERATED_PATHS`) and
   pinned by a test, so a new generated path cannot be added without answering "does this
   travel?", and the docs cannot drift from the answer.
   Two writers now share a work-item record, so every write is **read-modify-write** on
   its own section: a poll cycle must never erase a `start` the other ingress recorded a
   moment earlier.
2. **The recipe is a `.gitignore` block, published and dogfooded** — this repository
   tracks its own portable state with the exact block `docs/cli/state.md` prints.
3. **the-loop never commits state for you.** A hand-off is a human moment: commit on the
   machine that is stopping, pull on the machine that is starting.

### Why the session registry is excluded, specifically

It is the file an operator would most expect to carry, and the one where copying is worse
than losing. A session record names a harness conversation and an absolute `cwd` on the
machine that made it — but `find_by_work_item` still counts it as **live**, so on the new
machine the duplicate guard refuses the spawn that is actually needed and events are
routed to a conversation that is not there. The work item ends up armed, watched, and
worked on by nobody.

Independently: `cwd` discloses the operator's filesystem layout and `harnessSessionId` is
a resume handle. Neither belongs in a repository, whoever can read it.

## Consequences

**Positive.**

- A machine move is `git pull` plus starting the daemon. Armed items stay armed; watched
  threads are not re-forwarded from the top.
- The two files that **cannot** be reconstructed from GitHub — nothing upstream records
  that a `stop` was honoured — are the two that are now backed up as a side effect of
  ordinary version control.
- "What does the-loop write, and what is in it?" has a documented answer
  ([`docs/cli/state.md`](../cli/state.md)) for the first time.

**Negative / accepted costs.**

- A repository holding state has a working tree that goes dirty while the daemon runs.
- Two machines running at once will conflict inside `poll-state.json`, resolved by hand;
  the intended shape is one active machine at a time. Either side is safe to take — the
  worst case is a re-baselined thread.
- A tracked control record becomes an **input**: a forged `start` merged into a repository
  the daemon later pulls is an attempt to arm a work item without commenting on it. It is
  bounded by the auto-execute label (which needs repository write access) still being
  required, by a `.the-loop/sessions/` diff being an obvious review item, and by the
  documented recommendation to track state where only the operator can push.
- Operators whose `state.root` is outside a repository (`~/.the-loop`) copy `portable/`
  instead; the documentation says so rather than pretending git is the only route.
- **The layout change is breaking, and is migrated rather than sniffed.**
  `polling.stateFile` is removed — a file path cannot address a per-work-item ledger — so
  a config still declaring it is refused with the replacement named, and
  `the-loop migrate-config` removes it and bumps the schema to `0.3.0`. On disk nothing
  is moved destructively: the pre-issue-128 locations are **read** when a work item's new
  record has no such section and written forward on the next write, so no watched thread
  is re-baselined and nothing armed is forgotten. The operator deletes the old tree when
  they are satisfied.

## Alternatives considered

| Option | Why not |
|---|---|
| `the-loop state export/import` | The state is already plain JSON in one directory and git already moves everything else in the-loop. A bundle command is a second, weaker transport to maintain, and answers none of the questions the issue asked. |
| One file per work item holding *both* halves (session handle included) | Puts a machine handle inside the file that is tracked in git — an absolute `cwd` and a resume id in a repository, and a portability boundary that has to be enforced field by field instead of by directory. |
| Track `sessions/` too, teaching the registry to ignore foreign records | Makes the duplicate-session invariant — the guard that stops two agents working one item — machine-aware, to solve a problem better solved by not copying the file. The new machine must spawn its own session either way. |
| Document only, ignore everything as before | Answers the "is it documented?" question and leaves the other three as prose nobody can execute. The `.gitignore` block *is* the answer. |
| Commit state automatically from the daemon | A daemon writing commits into an operator's repository is a surprise with a blast radius. Hand-off stays human. |
