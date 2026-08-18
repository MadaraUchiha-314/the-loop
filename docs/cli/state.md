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
│   ├── index.json                 # what this directory holds, derived — tracked
│   └── github-octo-repo-15.json   # one per work item: control + poll state — tracked
├── local/
│   └── github-octo-repo-15.json   # that item's session handle(s) — never tracked
├── logs/
│   ├── events.jsonl               # the decision trail
│   └── poller.out                 # a daemonized poller's stdout/stderr
├── channels/
│   └── slack.json                 # channel conversations: thread bindings + read cursors — never tracked
├── gh-webhook.pid                 # the running receiver
├── poll.pid                       # the running poller — and its lock
└── poll-status.json               # the poller's heartbeat, read by `the-loop status`
```

Everything here is JSON, JSONL or plain text, meant to be read with `jq`, `cat` and
`tail -f`. The record stores and the heartbeat are rewritten atomically (`tempfile` +
`os.replace`), so a crash never leaves half a file; the event log and the poller log are
appended to a line at a time, and a pidfile is written once at startup.

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
| `<root>/portable/index.json` | the same store, derived | one entry per record: ref, url, file, sections | **portable** |
| `<root>/local/<slug>.json` | the session registry | conversation id, `cwd`, tmux target, status, and the item's pull requests with their own sessions | **local** |
| `<root>/logs/events.jsonl` | every ingress, and `sessions` | one JSON object per decision | **local** |
| `<root>/logs/poller.out` | a daemonized poller | its stdout and stderr, appended | **local** |
| `<root>/gh-webhook.pid` | the receiver | the receiver's pid — and its single-instance lock (issue-228) | **local** |
| `<root>/poll.pid` | the poller | the poller's pid — and the lock proving it is the only one | **local** |
| `<root>/poll-status.json` | the poller, after every cycle | the heartbeat `the-loop status` reads: `startedAt`, `lastCycleAt`, last cycle's counters — and no pid, which is `poll.pid`'s to name | **local** |
| `<root>/self-diagnosis.json` | self-diagnosis (issue-242, opt-in) | which failure fingerprints this machine already reported (with the issue URL), abandoned or is retrying, and when it last posted | **local** |
| `<root>/channels/<channel>.json` | the channels reader/writer (issue-245, opt-in) | per channel type: which Slack thread carries which work item's conversation, and the last reply this deployment mirrored and delivered | **local** |

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
`github-octo-repo-15.json`), with two independent sections and, since
[issue-130](https://github.com/MadaraUchiha-314/the-loop/issues/130), a link to the work
item itself.

```json
{
  "ref": "github:octo/repo#15",
  "url": "https://github.com/octo/repo/issues/15",
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
  },
  "graph": {
    "loop": "pdlc-work-item-loop",
    "workItem": "issue-15",
    "sessionPerPr": "cross-repository",
    "nodes": [
      {"id": "design", "phase": "design", "skipped": true, "selectable": true},
      {"id": "design-critic-review", "phase": "", "skipped": true, "selectable": true, "optIn": true},
      {"id": "verification", "phase": "verification", "skipped": false, "selectable": false}
    ]
  }
}
```

### `ref` and `url` — which work item this is about

`ref` is the identity: it is what the daemon parses, what the file name is derived from,
and what the pre-issue-128 shim keys on. `url` is the same fact in the form you can click,
added beside it rather than replacing it, because these files are tracked and therefore
read by people.

The URL is **derived, never guessed**: only `github` refs resolve, to the host the ref
names — `github.com` unless it says otherwise — and only when the host, owner and repo are
the shapes GitHub accepts. Anything else, such as a `jira:` ref, has no `url` field at
all, because a link somewhere other than the work item is worse than no link. When the
number belongs to a pull request, GitHub redirects `…/issues/<n>` to `…/pull/<n>`, so one
form serves both.

::: tip GitHub Enterprise
A work item that does not live on github.com carries its host in the ref
(`github:ghe.corp.example/octo/repo#15`), and therefore in its file name
(`github-ghe.corp.example-octo-repo-15.json`) and its URL. Nothing has to be configured:
the receiver reads the host from the repository's `html_url` and the poller from the
item's own. Two work items with the same owner/repo/number on different hosts are
different work items, and get different records.

If you were already running the-loop against a GitHub Enterprise host, its work items
are **re-identified** by this change — a new file name, so the poll ledger re-baselines
the thread once and any session for it should be re-registered
(`the-loop sessions register`). github.com work items are untouched.
:::

### `control` — what an authorized user asked for

| Field | Meaning |
|---|---|
| `command` | the **last** command recorded: `start`, `stop`, `pause`, `resume` or `cleanup` |
| `source` | `comment` (a keyword on the ticket) or `cli` (`the-loop sessions …`) |
| `actor` | the GitHub login that asked |
| `requestedAt` | when |

Written when a control keyword is accepted (from either ingress) or a
`sessions start|stop|pause|resume|cleanup` runs; cleared when the work item ends. It answers one
question — *did an authorized user ask for this work item to be running?* — which is what
makes a start survive a daemon restart, and what lets a `stop` durably disarm a labelled
item so it does not quietly re-spawn on the next event.

**If you delete it:** an armed item is disarmed. A labelled work item stops being worked
with no error anywhere — the daemon is behaving exactly as configured, on a record that is
no longer there. This is the state you most want to carry, and the one nothing upstream
can rebuild.

### `graph` — the phases this work item was frozen to walk

| Field | Meaning |
|---|---|
| `loop` | which shipped loop was frozen (`pdlc-work-item-loop`) |
| `workItem` | the spec-folder id the graph was resolved for |
| `sessionPerPr` | how many tmux+claude sessions this work item's pull requests get — `never`, `cross-repository` or `always`, chosen on the same checklist and frozen by the same reply ([issue-260](https://github.com/MadaraUchiha-314/the-loop/issues/260)). Absent on a record written before the question existed, which reads as "route by the operator's `routing.tmux.sessionPerPr`" |
| `nodes` | every node in declaration order: `skipped` (routed around), `selectable` (was it ever the user's to choose) and `optIn` (off unless selected — so `skipped: true` here means *nobody asked for it*, not *somebody removed it*) |

Written once, when an authorized user answers the
[`phase-selection`](/capabilities/process-graph) gate with the execute keyword
([issue-177](https://github.com/MadaraUchiha-314/the-loop/issues/177)). It is here rather
than in the session record for the same reason `control` is: *which phases this work item
needs* is true on any machine, so it travels with the work item and not with the session
handle. It is also the answer to "what did we agree this item would do?" without a
checkout and without re-reading a comment thread anyone can still edit.

**If you delete it:** the loop keeps walking exactly the same phases —
`docs/specs/<id>/graph-state.json` in the repository is the authoritative copy of those.
You lose the portable, checkout-free view of the item's agreed shape, and `sessionPerPr`
with it: this file is the **only** copy the daemon reads, so the item's pull requests fall
back to routing by the operator's configured default.

### `poll` — what the poller has already seen

| Field | Meaning |
|---|---|
| `seenComments` | comment ids already baselined or delivered — capped, and pruned each cycle to what still exists upstream |
| `commentAttempts` | in-flight delivery attempts per comment, against [`maxRetries`](/config/cli/polling-options#maxretries) — **only deliveries that may still be retried** |
| `spawn` | the presence/spawn retry ledger: attempts, whether it gave up, the in-flight delivery id |
| `lastPolledAt` | the last cycle that saw the item |

An item is *baselined* on first sight — the whole existing thread is marked seen, because
the spawned session reads it itself — and the section is dropped when the item ends, so a
reopened item is first-sight again rather than skipped forever.

A comment the daemon **refused on purpose** is baselined too, not left pending: while a work
item is unstarted (`requireStartCommand`) or its session is paused, events are suppressed and
**never replayed**, so counting retries against them would be counting a delivery nobody is
attempting. Such a comment leaves `commentAttempts` empty and is recorded once as
`poll.comment_settled` (with the reason). The same holds for a comment that carried a control
keyword: it was executed, not delivered. Nothing is lost — a spawned session is told to read
the item's whole thread, which is where those comments still are.

**If you delete it:** every watched thread is first-sight again. Nothing breaks, but the
poller re-baselines them, and an item that had been given up on gets a fresh spawn budget.

::: tip Why one file, two writers
Control comes from a keyword a human typed; the poll section from what the poller saw. They
are written by different components, and grouping by *writer* is what used to spread this
across three stores. Writes are read-modify-write per section, so a poll cycle can never
clobber a control command recorded a moment earlier by the other ingress.
:::

## Work-item index — `<root>/portable/index.json`

One file listing the records beside it, so the directory answers *"what is the-loop
tracking?"* without opening every record ([issue-130](https://github.com/MadaraUchiha-314/the-loop/issues/130)).

```json
{
  "workItems": [
    {
      "ref": "github:octo/repo#15",
      "url": "https://github.com/octo/repo/issues/15",
      "file": "github-octo-repo-15.json",
      "sections": ["control", "poll"]
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `ref` / `url` | the work item, and its page — same rule as the record above (`url` is absent when none can be derived) |
| `file` | the record's name inside `portable/` |
| `sections` | which of `control` / `poll` that record actually holds |
| `sealed` | present only on an [upgrade tombstone](#upgrading-from-the-pre-issue-128-layout), which is why it has no sections |

**Lifecycle.** Rewritten after every record write and every removal, by scanning the
directory — never maintained incrementally. Entries are ordered by `ref`, so an unchanged
directory produces an identical file and a diff shows only what changed. When the last
record goes, the index goes with it.

**Nothing reads it.** Not the daemon, not any command. That is deliberate
([decision-047](/decisions/decision-047)): an index that gated behaviour would be a second
source of truth for what the directory already states, and a stale second source is worse
than none.

**If you delete it:** nothing happens, and the next record write puts it back. The same is
true if it is stale, hand-edited, or arrives from someone else's pull request.

::: tip Conflicts on it are safe
This is the one file both machines write even when they worked *different* work items —
the property [decision-046](/decisions/decision-046) otherwise gives you. Because it is
derived, resolving is not a judgement call: **take either side** (or delete the file), and
the next write rebuilds it from the directory.
:::

## Session record — `<root>/local/<slug>.json`

One file per work item that has a session — and, since
[issue-172](https://github.com/MadaraUchiha-314/the-loop/issues/172), everything about
that work item's sessions: the item's own, plus one entry per **pull request** delivering
it.

A pull request entry is a durable **binding** — which pull requests deliver this work item —
and only sometimes a second conversation. Which of them get one is the work item's own choice, frozen at `phase-selection` into
the `graph` section's `sessionPerPr` (above) and falling back
to [`routing.tmux.sessionPerPr`](/config/cli/routing-options#tmux-sessionperpr)
([issue-260](https://github.com/MadaraUchiha-314/the-loop/issues/260)): under
`cross-repository`, a pull request in the work item's **own repository** has no
session of its own — it is the work item's delivery, on the work item's branch and in the
work item's checkout, so its `tmuxTarget` and `harnessSessionId` stay empty and its events
go to the record's session ([issue-253](https://github.com/MadaraUchiha-314/the-loop/issues/253)) —
while a pull request in **another** repository gets its own tmux session and harness
conversation, in a checkout of that repository. `always` makes the same-repository entry a
candidate too, and `never` makes none of them one
([issue-258](https://github.com/MadaraUchiha-314/the-loop/issues/258)). An entry whose
session was declined for want of a checkout of its own keeps the empty fields, exactly as a
collapsed one does — the record says what was *bound*, and the event log says what was
*spawned*.

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
  "tmuxTarget": "loop-github-octo-repo-15",
  "recentDeliveries": ["8f2c…"],
  "pullRequests": [
    {
      "workItem": {"ref": "github:octo/repo#16", "…": "…"},
      "harness": "claude",
      "harnessSessionId": "77ab…",
      "status": "active",
      "tmuxTarget": "loop-github-octo-repo-16",
      "recentDeliveries": ["91d0…"]
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `harness` / `harnessSessionId` | which harness, and the conversation to resume |
| `cwd` | where a resume must run (the work item's checkout) |
| `status` | `active`, `paused` (suppressed, not gone) or `closed` |
| `tmuxTarget` | the tmux session to attach to; `""` until one is spawned (issue-156) |
| `recentDeliveries` | the last 50 delivery ids, so a restart does not re-deliver |
| `pullRequests` | the PRs delivering this work item, each a session of its own — same fields, one level deep, absent until a PR event routes here |

**Why the PRs are in here.** Which work item a PR delivers used to be recomputed from
`gh`'s `closingIssuesReferences` on every single event — so unlinking the PR in GitHub's
Development panel, editing out the closing keyword, or one transient GraphQL failure
silently re-pointed routing at the PR itself, past a session that was still running. The
record is now the answer: everything about a work item — every PR delivering it and every
conversation involved — is one file. A PR entry is added when its first event routes,
gets its own tmux session lazily from the first event that needs one, and is closed (that
entry alone) when the PR merges or closes; the work item's session runs on, because a
work item may be delivered by several PRs
([issue-101](https://github.com/MadaraUchiha-314/the-loop/issues/101)). An entry that has
been hand-edited into something unreadable degrades to "that PR is unrecorded" — it never
takes the work item's own session down.

**Lifecycle.** Written on spawn or `sessions register`; updated on every delivered event;
flipped to `closed` when the work item itself ends. Closed records are kept — that is what
makes a finished tmux session still attachable.

**If you delete it:** the daemon forgets the work item has a session and spawns a fresh
one on the next event — a new conversation with no memory of the old one, in the same
checkout. The PR list goes with it, and is re-recorded as PR events arrive. Recoverable,
at the cost of context.

**Never carry it to another machine.** See [what must never be
carried](#what-must-never-be-carried).

## Event log — `<root>/logs/events.jsonl`

Append-only JSONL: one object per decision, from both ingresses and the `sessions`
command. This is how you answer *"why did nothing happen?"* — drops carry a
machine-readable `reason`. Query it with [`the-loop events`](/cli/commands/events), or with
`jq`. See [observability](/config/cli/observability-options#eventlog-path).

**If you delete it:** you lose the audit trail, and nothing else. No behaviour reads it.

## Receiver pidfile — `<root>/gh-webhook.pid`

Written by the receiver (started by [`the-loop start`](/cli/commands/start) or
`python -m the_loop.daemon_entry gh-webhook`), removed when it exits. Since issue-228 it
is also the receiver's **single-instance lock**, exactly as `poll.pid` is the poller's
below. A stale file after a crash is harmless: it is unlocked, so the next start takes
it, and [`the-loop stop`](/cli/commands/stop) reports the process is gone.

## Poller pidfile — `<root>/poll.pid`

Written by the poller (started by [`the-loop start`](/cli/commands/start) or
`python -m the_loop.daemon_entry poller`), removed when it exits. It is also the
poller's **single-instance lock**: the poller holds an exclusive advisory lock on it for the
whole run, so a second poller against the same state root refuses rather than sharing the
ledger, and [`the-loop stop`](/cli/commands/stop) uses the same lock to tell a live poller from a pid left behind by a
crash. Being one file rather than two is the point — "who is running" and "how do I signal
them" cannot then disagree. It is the **only** place either question is answered: the
heartbeat below deliberately carries no pid, and
[why they stay separate files](#why-this-is-a-second-file-and-not-part-of-the-pidfile) is
written up there.

**If you delete it while a poller is running:** the running poller keeps its lock (the lock
lives on the open file, not the name), but a second start will no longer see it and can
start alongside. Don't. **A stale file after a crash is harmless:** it is unlocked, so the
next start reports it, removes it and takes a fresh one, and `the-loop stop` removes it.

## Poller heartbeat — `<root>/poll-status.json`

Rewritten by the poller after every cycle, and read by
[`the-loop status`](/cli/commands/status). It carries what a lock cannot: when this poller
started, when it last finished a cycle, and what that cycle did.

```json
{
  "startedAt": "2026-08-10T09:58:03Z",
  "lastCycleAt": "2026-08-10T10:42:00Z",
  "intervalSeconds": 60,
  "lastCycle": {
    "itemsSeen": 5, "spawns": 1, "commentsForwarded": 0,
    "closures": 0, "failures": 0, "errors": 0, "interrupted": false
  }
}
```

::: warning It is never the answer to "is the poller running?"
That answer is the lock on `poll.pid`, and only the lock — the one formulation immune to
pid reuse, and the one nobody can forge by writing a file. A recent `lastCycleAt` beside a
lock nobody holds means the poller *stopped* after that cycle, and `the-loop status` says
exactly that.
:::

It is deliberately **not** removed when the poller exits, so `the-loop status` can still tell
you when the last cycle ran. **If you delete it:** `the-loop status` keeps reporting liveness
and pid and loses the progress lines, until the next cycle writes a new one.

The file carried a `pid` until [issue-205](https://github.com/MadaraUchiha-314/the-loop/issues/205);
nothing read it, and it is gone. A heartbeat written by an older poller still reads — the
leftover pid is dropped rather than reported.

### Why this is a second file, and not part of the pidfile

It is a fair question, and the answer is three things pulling in opposite directions
([decision-076](/decisions/decision-076)):

| | `poll.pid` | `poll-status.json` |
|---|---|---|
| Answers | is one running, and how do I signal it? | is it making progress? |
| Written | once, at startup, under the lock | after every cycle |
| How | in place, into the locked file | `tempfile` + `os.replace` — a **new inode** each time |
| On exit | removed | kept, on purpose |
| If the write fails | the start aborts — a daemon that cannot prove exclusivity must not run | warn once, carry on — observability must never break ingress |

The first row of *how* is the one that settles it. An advisory lock lives on the inode the
daemon opened, not on the name; replacing the file at that path leaves the poller holding a
lock on an orphan while the path goes free. Merged, the poller would unlock itself on its
own first cycle, and the next poller start would happily run a **second poller against the
same ledger** — the bug the lock exists to prevent. Writing the heartbeat in place instead
would trade that for a `the-loop status` that can read a half-written document, and would still
leave the last two rows contradictory.

## Poller log — `<root>/logs/poller.out`

Where a poller started detached — by [`the-loop start`](/cli/commands/start) or the control
plane — sends its stdout and stderr. Plain text, appended to, and **never rotated**: point
`logrotate` (or your platform's equivalent) at it on a long-lived host. the-loop does not
rotate it itself, because a daemon that truncates its own log while another process is
tailing it is a worse problem than a large file.

**If you delete it:** a running daemon keeps writing to the deleted inode until it is
restarted — the usual reason to have `logrotate` use `copytruncate` or to restart the
poller after rotating.

## Self-diagnosis ledger — `<root>/self-diagnosis.json`

What [self-diagnosis](/config/cli/self-diagnosis-options) — opt-in, off by default — has
already done with this machine's event log: each failure fingerprint it reported (with
the created issue's URL), abandoned after repeated agent failures, or is still retrying,
plus the timestamps behind the rolling daily cap. A sibling `self-diagnosis.json.lock`
holds the flock that keeps two processes from scanning at once; the `.gitignore` pattern
covers both (and the atomic writer's temporaries) with one `self-diagnosis.json*`.

**If you delete it:** every failure still in the event log becomes "new" again on the
next scan, so already-filed issues can be filed a second time. Delete it only together
with (or after) the event log it summarises.

## Channel conversation state — `<root>/channels/<channel>.json`

What the [channels](/config/cli/channels-options) surface — opt-in, off by default —
remembers about its conversations, one file per channel type (today: `slack.json`).
Two maps: `threads` binds a Slack thread to the work item whose question started it,
and `cursors` records the last reply in each thread this deployment already mirrored
and delivered. Bounded (the oldest binding is dropped past a cap), rewritten
atomically, and **local**: the cursors are a ledger of what *this* machine processed,
and the thread and member ids name conversations in the operator's own workspace —
neither belongs in a repository.

**If you delete it:** the bot forgets its open conversations. Replies in old threads
stop being read (an unbound thread is dropped as `unmapped`), and the next `the-loop
ask` starts a fresh thread instead of continuing the old one. Nothing is
double-processed — the bindings are how replies are *found*, not how they are deduped
against the ticket.

## Wiping one work item — `sessions reset`

Backing state up is one question; getting rid of it is the other, and it has a command:
[`the-loop sessions reset`](/cli/commands/sessions#reset). It exists for the case where the
memory is the problem — you fixed a bug in the-loop's own CLI, released it, and the item in
flight is still holding a conversation the old code started.

| Path | What a reset does to it |
|---|---|
| `<root>/local/<slug>.json` | deleted (the session is closed through the normal close path first) |
| `<root>/portable/<slug>.json` | `control` and `poll` cleared — the file is removed, or left `sealed` while a pre-issue-128 tree still holds something for that item |
| `<root>/portable/index.json` | rewritten to match, on the same write |
| `<root>/logs/events.jsonl` | **appended to** — one `session.reset` line. Never rewritten: a command that could erase its own trail is not auditable |
| `<root>/gh-webhook.pid` | untouched. Reset does not stop the daemon — it warns when one is running, because a daemon holds poll state in memory and can write it back |
| the workspace checkout | removed unless [`workspace.keepCheckoutOnClose`](/config/cli/routing-options#workspace-keepcheckoutonclose) |

Nothing in your **repository** is touched: `docs/specs/<id>/graph-state.json` is checked in
on the work item's branch and re-derived from the artifacts, so wiping local state never
rewrites the record of the work itself.

`--dry-run` prints the same list without doing any of it. Reaching for `rm` instead is the
one thing to avoid — deleting `portable/<slug>.json` by hand can *resurrect* a pre-issue-128
record through the legacy readers, which is exactly what the `sealed` marker below prevents.

## Releasing a finished work item — `sessions cleanup`

The other remover, and it answers a different question:
[`the-loop sessions cleanup`](/cli/commands/sessions#cleanup) — or the `the-loop cleanup`
keyword, or a closure by an authorized user — is for a work item that is **over**, not one
that needs to start again.

| Path | What a cleanup does to it |
|---|---|
| `<root>/local/<slug>.json` | deleted, and every endpoint's tmux session killed with it (harness ended first) |
| `<root>/portable/<slug>.json` | **untouched** — `control` (rewritten to `cleanup`, which disarms the item), `poll` and `graph` all stay. This is the whole difference from a reset: persistence and tracking are what outlive the machine |
| `<root>/portable/index.json` | untouched |
| `<root>/logs/events.jsonl` | **appended to** — one `session.cleaned` line naming the actor, the source and the pieces |
| the workspace checkout | removed **regardless** of [`workspace.keepCheckoutOnClose`](/config/cli/routing-options#workspace-keepcheckoutonclose) — uncommitted work in it is gone |
| the shared per-repository clone | untouched: it serves every work item on that repo |
| anything remote | untouched: no branch, pull request, issue or label |

It runs with or without a live session and with or without a record — a checkout stranded
by a crash is located from the work-item ref alone — so it is also the way to reclaim
state an older version left behind.

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
.the-loop/poll-status.json
.the-loop/self-diagnosis.json*
.the-loop/channels/
.the-loop/portable/*.tmp
```

The one non-obvious line is the last: `portable/*.tmp` re-excludes the atomic writer's
temporaries — a crash between `mkstemp` and `os.replace` leaves one behind.

### The hand-off

The daemon never commits anything. Carrying state is a deliberate moment:

```bash
# on the machine you are stopping
the-loop stop
git add .the-loop/portable
git commit -m "chore: hand off the-loop state"
git push

# on the machine you are starting
git pull
the-loop sessions list              # empty — sessions are local, and that is correct
the-loop start
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

An existing `portable/` directory gains its `index.json` (and each record its `url`) the
first time anything is written — a poll cycle, or an accepted control keyword. There is no
migration step, and nothing is lost by not having them yet.

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

The `pullRequests` entries inside it are local for the same reason twice over: each one
is a conversation id and tmux target of its own. They disclose nothing beyond what the
record already does, and the daemon re-records a PR from the first event that routes.

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
