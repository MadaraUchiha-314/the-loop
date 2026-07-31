# State on disk

What the daemon writes, where it writes it, what is inside — and which of it means
anything on another machine.

Read this before you back up, wipe, or move a working setup between laptops.

::: tip Moving machines? The short answer
Track **one** directory in git: `<state.root>/portable/`. It holds one file per work item
— what an authorized user armed, and which comments have already been seen. The
[block below](#carrying-state-to-another-machine) is three lines.

Leave `local/`, `logs/` and the pidfile ignored. The session records in `local/` must
**not** travel: copying them is [worse than losing
them](#what-must-never-be-carried).
:::

## Where it lives

Everything the CLI **generates** sits under one configured root,
[`state.root`](/config/cli/#state-root) (default `.the-loop`, relative to the process's
working directory), split by whether it travels:

```
.the-loop/
├── portable/
│   └── github-octo-repo-15.json   # one per work item: control + poll state — tracked
├── local/
│   └── github-octo-repo-15.json   # that item's session handle — never tracked
├── logs/
│   └── events.jsonl               # the decision trail
└── gh-webhook.pid                 # the running receiver
```

Everything here is JSON or JSONL, meant to be read with `jq`, `cat` and `tail -f`. The two
record stores are rewritten atomically (`tempfile` + `os.replace`), so a crash never leaves
half a file; the event log is appended to a line at a time, and the pidfile is written once
at startup.

Two paths can be pointed elsewhere explicitly —
[`routing.registryDir`](/config/cli/routing-options#registrydir) for `local/`, and
[`eventLog.path`](/config/cli/observability-options#eventlog-path) /
[`pidfile`](/config/cli/webhook-options#pidfile) — but `portable/` follows `state.root`,
because "where does the half I track live?" should have exactly one answer.

## Two kinds of state

The layout is the answer to one question, so it is worth stating the question. Everything
the-loop writes is one of two things:

- **Facts about the world.** What GitHub already told us, and what an authorized human
  asked for. True no matter which machine is running. Slow to rebuild, and some of it
  cannot be rebuilt at all — nothing upstream records that a `stop` was honoured.
- **Handles to this machine.** A harness conversation id, a working directory, a pid, a
  local audit trail. These name things that exist only where they were created. Cheap to
  rebuild — the daemon rebuilds them by spawning — and actively harmful when moved.

Grouping the files by **which of those they are**, rather than by which component writes
them, is what makes the `.gitignore` recipe three lines instead of a puzzle
([decision-046](/decisions/decision-046)).

## The classification

| Path | Written by | Holds | Travels? |
|---|---|---|---|
| `<root>/portable/<slug>.json` | execution control + the poller | what was armed, and which comments are already seen | **portable** |
| `<root>/local/<slug>.json` | the session registry | conversation id, `cwd`, runner, tmux target, status | **local** |
| `<root>/logs/events.jsonl` | every ingress, and `sessions` | one JSON object per decision | **local** |
| `<root>/gh-webhook.pid` | `gh-webhook start` | the receiver's pid | **local** |

The same table is declared in code, in
[`the_loop/state.py`](https://github.com/MadaraUchiha-314/the-loop/blob/main/cli/the_loop/state.py)
(`GENERATED_PATHS`), and a test fails the build when a new generated path is added without
classifying it, or when this page and the declaration disagree.

One more file belongs to this picture but lives elsewhere: `docs/specs/<id>/graph-state.json`
is checked in by design — the [process graph](/capabilities/process-graph) records where a
work item is, and it must survive a machine change, a session change and a multi-day human
review. It is a cache, never an authority, so a stale copy degrades to a recompute. The
portable half above is classified on exactly that reasoning.

## Work-item record — `<root>/portable/<slug>.json`

One file per work item, named for its ref (`github:octo/repo#15` →
`github-octo-repo-15.json`), with two independent sections.

```json
{
  "ref": "github:octo/repo#15",
  "control": {
    "command": "start",
    "source": "comment",
    "actor": "octocat",
    "requestedAt": "2026-07-31T09:11:58Z",
    "note": ""
  },
  "poll": {
    "seenComments": ["2451…", "2452…"],
    "commentAttempts": {"2453…": 1},
    "spawn": {"attempts": 0, "gaveUp": false, "deliveryId": ""},
    "lastPolledAt": "2026-07-31T10:42:00Z"
  }
}
```

### `control` — what an authorized user asked for

| Field | Meaning |
|---|---|
| `command` | the **last** command recorded: `start`, `stop`, `pause` or `resume` |
| `source` | `comment` (a keyword on the ticket) or `cli` (`the-loop sessions …`) |
| `actor` | the GitHub login that asked |
| `requestedAt` | when |

Written when a control keyword is accepted (from either ingress) or a
`sessions start|stop|pause|resume` runs; cleared when the work item ends. It answers one
question — *did an authorized user ask for this work item to be running?* — which is what
makes a start survive a daemon restart, and what lets a `stop` durably disarm a labelled
item so it does not quietly re-spawn on the next event.

**If you delete it:** an armed item is disarmed. A labelled work item stops being worked
with no error anywhere — the daemon is behaving exactly as configured, on a record that is
no longer there. This is the state you most want to carry, and the one nothing upstream
can rebuild.

### `poll` — what the poller has already seen

| Field | Meaning |
|---|---|
| `seenComments` | comment ids already baselined or delivered — capped, and pruned each cycle to what still exists upstream |
| `commentAttempts` | in-flight delivery attempts per comment, against [`maxRetries`](/config/cli/polling-options#maxretries) |
| `spawn` | the presence/spawn retry ledger: attempts, whether it gave up, the in-flight delivery id |
| `lastPolledAt` | the last cycle that saw the item |

An item is *baselined* on first sight — the whole existing thread is marked seen, because
the spawned session reads it itself — and the section is dropped when the item ends, so a
reopened item is first-sight again rather than skipped forever.

**If you delete it:** every watched thread is first-sight again. Nothing breaks, but the
poller re-baselines them, and an item that had been given up on gets a fresh spawn budget.

::: tip Why one file, two writers
Control comes from a keyword a human typed; the poll section from what the poller saw. They
are written by different components, and grouping by *writer* is what used to spread this
across three stores. Writes are read-modify-write per section, so a poll cycle can never
clobber a control command recorded a moment earlier by the other ingress.
:::

## Session record — `<root>/local/<slug>.json`

One file per work item that has a session.

```json
{
  "workItem": {
    "ref": "github:octo/repo#15",
    "provider": "github", "owner": "octo", "repo": "repo", "number": 15
  },
  "harness": "claude",
  "harnessSessionId": "0f1c…",
  "cwd": "/Users/you/.the-loop/workspace/github.com/octo/repo/issue-15",
  "status": "active",
  "createdAt": "2026-07-31T09:12:04Z",
  "lastEventAt": "2026-07-31T10:41:55Z",
  "runner": "tmux",
  "tmuxTarget": "loop-github-octo-repo-15",
  "recentDeliveries": ["8f2c…"]
}
```

| Field | Meaning |
|---|---|
| `harness` / `harnessSessionId` | which harness, and the conversation to resume |
| `cwd` | where a resume must run (the work item's checkout) |
| `status` | `active`, `paused` (suppressed, not gone) or `closed` |
| `runner` / `tmuxTarget` | how the session is hosted; the tmux session to attach to |
| `recentDeliveries` | the last 50 delivery ids, so a restart does not re-deliver |

**Lifecycle.** Written on spawn or `sessions register`; updated on every delivered event;
flipped to `closed` when the work item itself ends. Closed records are kept — that is what
makes a finished tmux session still attachable.

**If you delete it:** the daemon forgets the work item has a session and spawns a fresh
one on the next event — a new conversation with no memory of the old one, in the same
checkout. Recoverable, at the cost of context.

**Never carry it to another machine.** See [what must never be
carried](#what-must-never-be-carried).

## Event log — `<root>/logs/events.jsonl`

Append-only JSONL: one object per decision, from both ingresses and the `sessions`
command. This is how you answer *"why did nothing happen?"* — drops carry a
machine-readable `reason`. Query it with [`the-loop events`](/cli/commands/events), or with
`jq`. See [observability](/config/cli/observability-options#eventlog-path).

**If you delete it:** you lose the audit trail, and nothing else. No behaviour reads it.

## Receiver pidfile — `<root>/gh-webhook.pid`

Written by `gh-webhook start`, removed by `gh-webhook stop`. A stale file after a crash is
harmless; `stop` reports the process is gone.

## Carrying state to another machine

Track `portable/` in git. Paste this into the `.gitignore` of the repository your
`state.root` lives in — it is the block this repository uses for its own state:

```gitignore
# the-loop: generated state under state.root (default .the-loop) — see
# https://madarauchiha-314.github.io/the-loop/cli/state
# Local handles (session records, event log, pidfile) never leave the machine.
# .the-loop/portable/ is the half that travels with the work, so it is tracked.
.the-loop/local/
.the-loop/logs/
.the-loop/*.pid
.the-loop/portable/*.tmp
```

The one non-obvious line is the last: `portable/*.tmp` re-excludes the atomic writer's
temporaries — a crash between `mkstemp` and `os.replace` leaves one behind.

### The hand-off

The daemon never commits anything. Carrying state is a deliberate moment:

```bash
# on the machine you are stopping
the-loop gh-webhook stop            # or stop the poller
git add .the-loop/portable
git commit -m "chore: hand off the-loop state"
git push

# on the machine you are starting
git pull
the-loop sessions list              # empty — sessions are local, and that is correct
the-loop gh-webhook start
```

The new machine knows which items are armed and which comments it has already seen, and
spawns its own sessions as events arrive. `sessions list` being empty is the design
working, not state that failed to arrive.

### If `state.root` is outside a repository

The default is relative, so running the daemon from a checkout puts state in that
checkout. If yours is `~/.the-loop` (or any absolute path), there is no repository to
track it in — two options:

- **Copy `portable/`.** With `rsync` or anything else. Nothing else is needed, and nothing
  else should come.
- **Point `state.root` at a tracked directory** — the same "dev box repo" pattern the
  [CLI config](/config/cli/#where-the-file-is-found) already supports. Note that
  `state.root` does **not** expand `~`.

### The two costs

Worth knowing before you adopt it:

1. **A dirty working tree while the daemon runs.** Every accepted control keyword and
   every poll cycle writes a tracked file, so `git status` in that repository is rarely
   clean. Commit at hand-off, not continuously.
2. **Hand-resolved conflicts if two machines run at once.** Both would write the record of
   any work item they *both* touched. The intended shape is one active machine at a time —
   that is what a hand-off is. If you do collide, taking either side is safe: the worst
   case is a re-baselined thread.

### Upgrading from the pre-issue-128 layout

State used to live in `<root>/sessions/` (session records), `<root>/sessions/control/`
(control records) and one `<root>/sessions/poll-state.json`. Nothing is lost on upgrade:
when a work item's new record has no such section yet, the-loop reads the old location
once and writes it forward, so no watched thread is re-baselined and nothing armed is
forgotten. Writes only ever go to the new layout, so each work item converges the first
time it is touched. Delete `<root>/sessions/` once `the-loop sessions list` and
`the-loop events` look right.

While both trees exist you may see a record like `{"ref": …, "sealed": true}`, or a
section written as `null`. That is a work item whose state the-loop ended deliberately,
marked so the old tree cannot bring it back; the markers disappear with the old tree.

The `polling.stateFile` option is gone with it — the ledger is a directory now, not a
file. A config that still sets it is refused loudly rather than ignored; run
[`the-loop migrate-config`](/cli/commands/migrate-config) (or
`/the-loop:upgrade-the-loop`).

## What must never be carried

The **session registry** — `<root>/local/<slug>.json` — is the one file where copying is
worse than losing.

A session record is a handle to a conversation and a directory on the machine that made
it. On another machine the conversation id resumes nothing and the `cwd` may not exist.
But `find_by_work_item` still counts the record as **live**, so:

- the duplicate-session guard refuses to spawn the session the new machine actually needs
  (*"an active session already exists for github:octo/repo#15"*), and
- every event routed to that work item is delivered to a conversation that is not there.

The work item ends up armed, watched, and worked on by nobody.

There is a second reason, independent of that one: `cwd` is an absolute path from the
operator's filesystem — username and directory layout — and `harnessSessionId` is a
resume handle to a conversation. Neither belongs in a repository, whoever can read it.

## Security

Tracking state in a repository is publishing it, and — if that repository accepts pull
requests — accepting proposals about it. Both are bounded, and worth stating plainly.

**What `portable/` discloses.** A work-item record holds a ref, one of four fixed
keywords, a GitHub login, timestamps and comment ids. All of it is already visible on the
ticket it describes. The file that would disclose something new — the session record, with
its absolute paths and resume handle — is on the local side of the line, for that reason
among others.

**A tracked control section is an input.** `start_requested` gates autonomous spawning, so
a forged `start` merged into a repository the daemon later pulls is an attempt to arm a
work item without commenting on it. Three things bound that:

1. **The record only arms.** The [auto-execute label](/config/cli/routing-options#autoexecutelabel)
   is still required and [`spawnOnUnmatched`](/config/cli/routing-options#spawnonunmatched)
   still governs — and applying a label needs write access to the repository.
2. **The diff is loud.** A pull request touching `.the-loop/portable/` is a configuration
   change; review it like one, the way `reviews.critics[]` is reviewed as executable
   config.
3. **Choose the repository accordingly.** Track state where only you can push. A
   repository that accepts third-party pull requests means arming records are proposable
   by strangers; the label gate is what keeps that insufficient rather than dangerous.

**Fail-closed behaviour is unchanged.** A missing or unreadable record reads as "nothing
recorded", and the daemon declines to spawn on its own.

## Next

- **[Concepts](/cli/concepts)** — work items, sessions, guards, the model this state serves.
- **[`sessions`](/cli/commands/sessions)** — inspecting and steering what the registry holds.
- **[`events`](/cli/commands/events)** — querying the log.
- **[`state.root`](/config/cli/#state-root)** — moving all of it somewhere else.
