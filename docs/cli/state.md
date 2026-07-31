# State on disk

What the daemon writes, where it writes it, what is inside — and which of it means
anything on another machine.

Read this before you back up, wipe, or move a working setup between laptops.

::: tip Moving machines? The short answer
Track **two** paths in git — `<state.root>/sessions/control/` and
`<state.root>/sessions/poll-state.json` — with the [block below](#carrying-state-to-another-machine).
They carry what an authorized user armed and which comments have already been seen.

Leave everything else ignored. The session registry in particular must **not** travel:
copying it is [worse than losing it](#what-must-never-be-carried).
:::

## Where it lives

Everything the CLI **generates** sits under one configured root,
[`state.root`](/config/cli/#state-root) (default `.the-loop`, relative to the process's
working directory):

```
.the-loop/
├── sessions/
│   ├── github-octo-repo-15.json      # session record — one per work item with a session
│   ├── poll-state.json               # what the poller has already seen
│   └── control/
│       └── github-octo-repo-15.json  # control record — what an authorized user asked for
├── logs/
│   └── events.jsonl                  # the decision trail
└── gh-webhook.pid                    # the running receiver
```

Each of those four paths can also be set explicitly
([`registryDir`](/config/cli/routing-options#registrydir),
[`stateFile`](/config/cli/polling-options#statefile),
[`eventLog.path`](/config/cli/observability-options#eventlog-path),
[`pidfile`](/config/cli/webhook-options#pidfile)); the root only fills in what you left
out. Everything here is JSON or JSONL, meant to be read with `jq`, `cat` and `tail -f`.
The three record stores — sessions, control, poll state — are rewritten atomically
(`tempfile` + `os.replace`), so a crash never leaves half a file; the event log is
appended to a line at a time, and the pidfile is written once at startup.

## Two kinds of state

The portability question has a different answer for each, and every answer on this page
follows from the split:

- **Facts about the world.** What GitHub already told us, and what an authorized human
  asked for. These are true no matter which machine is running. They are slow to rebuild,
  and some of them cannot be rebuilt at all — nothing upstream records that a `stop` was
  honoured.
- **Handles to this machine.** A harness conversation id, a working directory, a pid, a
  local audit trail. These name things that exist only where they were created. They are
  cheap to rebuild — the daemon rebuilds them by spawning — and actively harmful when
  moved.

"Make the state portable" is therefore not answered by copying the directory. Half of it
is not state *about* anything; it is a set of local handles.

## The classification

| Path | Written by | Holds | Travels? |
|---|---|---|---|
| `<root>/sessions/<slug>.json` | the session registry | conversation id, `cwd`, runner, tmux target, status | **local** |
| `<root>/sessions/control/<slug>.json` | execution control | the last `start`/`stop`/`pause`/`resume`, and who asked | **portable** |
| `<root>/sessions/poll-state.json` | the poller | seen comment ids, retry ledgers, last poll time | **portable** |
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
two portable files above are classified on exactly that reasoning.

## Session record — `<root>/sessions/<slug>.json`

One file per work item that has a session, named for the work-item ref
(`github:octo/repo#15` → `github-octo-repo-15.json`).

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

## Control record — `<root>/sessions/control/<slug>.json`

One file per work item an authorized user has steered, in the same file-per-item shape,
in a subdirectory beside the sessions it steers.

```json
{
  "ref": "github:octo/repo#15",
  "command": "start",
  "source": "comment",
  "actor": "octocat",
  "requestedAt": "2026-07-31T09:11:58Z",
  "note": ""
}
```

| Field | Meaning |
|---|---|
| `command` | the **last** command recorded: `start`, `stop`, `pause` or `resume` |
| `source` | `comment` (a keyword on the ticket) or `cli` (`the-loop sessions …`) |
| `actor` | the GitHub login that asked |
| `requestedAt` | when |

**Lifecycle.** Written when a control keyword is accepted (from either ingress) or a
`sessions start|stop|pause|resume` runs; cleared when the work item ends.

**What it answers.** *Did an authorized user ask for this work item to be running?* —
which is what makes a start survive a daemon restart, and what lets a `stop` durably
disarm a labelled item so it does not quietly re-spawn on the next event.

**If you delete it:** an armed item is disarmed. A labelled work item stops being worked
with no error anywhere — the daemon is behaving exactly as configured, on a record that is
no longer there. This is the state you most want to carry, and the one nothing upstream
can rebuild.

## Poll state — `<root>/sessions/poll-state.json`

One file for the whole poller, `{"items": {"<ref>": {…}}}`.

```json
{
  "items": {
    "github:octo/repo#15": {
      "seenComments": ["2451…", "2452…"],
      "commentAttempts": {"2453…": 1},
      "spawn": {"attempts": 0, "gaveUp": false, "deliveryId": ""},
      "lastPolledAt": "2026-07-31T10:42:00Z"
    }
  }
}
```

| Field | Meaning |
|---|---|
| `seenComments` | comment ids already baselined or delivered — capped, and pruned each cycle to what still exists upstream |
| `commentAttempts` | in-flight delivery attempts per comment, against [`maxRetries`](/config/cli/polling-options#maxretries) |
| `spawn` | the presence/spawn retry ledger: attempts, whether it gave up, the in-flight delivery id |
| `lastPolledAt` | the last cycle that saw the item |

**Lifecycle.** An item is *baselined* on first sight — the whole existing thread is marked
seen, because the spawned session reads it itself — and its ledger is dropped when the item
ends, so a reopened item is first-sight again rather than skipped forever.

**If you delete it:** every watched thread is first-sight again. Nothing breaks, but the
poller re-baselines them, and an item that had been given up on gets a fresh spawn budget.

::: warning The pre-issue-106 location
Before the state root existed this file was `.the-loop/poll-state.json`. If that one is
still on disk and the new one is not, the poller keeps using it and warns once. It is the
same file and equally portable — move it to `sessions/poll-state.json` to silence the
warning and match the recipe below.
:::

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

Track the two portable files in git. Paste this into the `.gitignore` of the repository
your `state.root` lives in — it is the block this repository uses for its own state:

```gitignore
# the-loop: generated state under state.root (default .the-loop) — see
# https://madarauchiha-314.github.io/the-loop/cli/state
# Local handles (session records, event log, pidfile) never leave the machine.
.the-loop/sessions/*
.the-loop/logs/
.the-loop/*.pid
# Portable: what an authorized user armed, and which comments have been seen.
!.the-loop/sessions/control/
!.the-loop/sessions/poll-state.json
.the-loop/sessions/control/*.tmp
```

Three details in there are easy to get wrong:

- It excludes `sessions/*`, **not** `sessions/`. Git does not descend into an excluded
  *directory*, so a `!` re-include beneath one has no effect. Excluding the directory's
  contents leaves the directory itself visible, which is what makes the next line work.
- `!sessions/control/` re-includes the **directory**. The files inside are then not
  matched by `sessions/*` at all, because a `*` does not cross a `/`.
- `control/*.tmp` re-excludes the atomic writers' temporaries — a crash between
  `mkstemp` and `os.replace` leaves one behind. (The poll state's temporaries are already
  covered by `sessions/*`.)

### The hand-off

The daemon never commits anything. Carrying state is a deliberate moment:

```bash
# on the machine you are stopping
the-loop gh-webhook stop            # or stop the poller
git add .the-loop/sessions/control .the-loop/sessions/poll-state.json
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

- **Copy the two paths.** `sessions/control/` and `sessions/poll-state.json`, with `rsync`
  or anything else. Nothing else is needed, and nothing else should come.
- **Point `state.root` at a tracked directory** — the same "dev box repo" pattern the
  [CLI config](/config/cli/#where-the-file-is-found) already supports. Note that
  `state.root` does **not** expand `~`.

### The two costs

Worth knowing before you adopt it:

1. **A dirty working tree while the daemon runs.** Every accepted control keyword and
   every poll cycle writes a tracked file, so `git status` in that repository is rarely
   clean. Commit at hand-off, not continuously.
2. **Hand-resolved conflicts if two machines run at once.** `poll-state.json` is one JSON
   object; two daemons polling the same repos will conflict in it. The intended shape is
   one active machine at a time — that is what a hand-off is. If you do collide, taking
   either side is safe: the worst case is a re-baselined thread.

## What must never be carried

The **session registry** — `<root>/sessions/<slug>.json` — is the one file where copying
is worse than losing.

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

**What the portable files disclose.** A control record holds a work-item ref, one of four
fixed keywords, a GitHub login and a timestamp. Poll state holds refs, comment ids and
timestamps. All of it is already visible on the ticket it describes. The file that would
disclose something new — the session record, with its absolute paths and resume handle —
is on the local side of the line, for that reason among others.

**A tracked control record is an input.** `start_requested` gates autonomous spawning, so
a forged `start` merged into a repository the daemon later pulls is an attempt to arm a
work item without commenting on it. Three things bound that:

1. **The record only arms.** The [auto-execute label](/config/cli/routing-options#autoexecutelabel)
   is still required and [`spawnOnUnmatched`](/config/cli/routing-options#spawnonunmatched)
   still governs — and applying a label needs write access to the repository.
2. **The diff is loud.** A pull request touching `.the-loop/sessions/` is a configuration
   change; review it like one, the way `reviews.critics[]` is reviewed as executable
   config.
3. **Choose the repository accordingly.** Track state where only you can push. A
   repository that accepts third-party pull requests means arming records are proposable
   by strangers; the label gate is what keeps that insufficient rather than dangerous.

**Fail-closed behaviour is unchanged.** A missing or unreadable control record reads as
"nothing recorded", and the daemon declines to spawn on its own.

## Next

- **[Concepts](/cli/concepts)** — work items, sessions, guards, the model this state serves.
- **[`sessions`](/cli/commands/sessions)** — inspecting and steering what the registry holds.
- **[`events`](/cli/commands/events)** — querying the log.
- **[`state.root`](/config/cli/#state-root)** — moving all of it somewhere else.
