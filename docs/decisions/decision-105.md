# Decision 105: a work item's Slack thread is rooted on the work item, opened once under a lock, and every event is a reply

- **Status:** proposed
- **Date:** 2026-09-02
- **Work item:** [issue-312](https://github.com/MadaraUchiha-314/the-loop/issues/312)
- **Deciders:** MadaraUchiha-314 (owner, via the ticket), the-loop (design)
- **Refines:** [decision-094](decision-094.md) (the Slack bot channel; thread bindings are
  local state), [decision-103](decision-103.md) (the bus is the only caller of a channel)

## Context

Issue-245 gave the Slack channel "one thread per work item" by making the first event's
message the thread root and reusing it afterwards. That left the root saying whatever
happened first, the binding found by a newest-wins scan, and four writers (the agent's
session, the two daemons, the poll watcher thread) doing unlocked read-modify-writes on
one file — so two first events within a second opened two threads, and a binding could be
lost under a racing cursor advance. The owner asked for a thread per work item, opened
lazily, with every message a reply in it, and for the channel/thread information to be
tracked per work item.

## Decision

| # | What was chosen | Why |
|---|-----------------|-----|
| D1 | **The root is the work item's, not the first event's.** A root message names the ref and links the work item; the event that opened the thread is its first reply, rendered like any other. | "Every message is a reply" is the ask, and it makes the thread findable by what it is rather than by what happened first. Cost: one `chat.postMessage` per work item, and the first event is no longer visible in the channel view — accepted, because every later event was already hidden there and Slack unfurls the root's link. |
| D2 | **Open-and-bind is exclusive per state file, under `flock` on a sibling `.lock`.** Every read-modify-write of the channel state goes through the same context manager; the reply is posted outside it. | A lock on the state file itself would be released by the atomic `os.replace` that writes it; a process-wide mutex would not reach the other three processes. The lock covers the decision (is there a thread?) and not the delivery, so a slow Slack call never stalls the watcher. |
| D3 | **The conversation is a per-work-item record in the same local file, listed by `the-loop channels threads`.** `conversations` (work item → channel, thread, opened, origin, permalink) sits beside the reader's thread-keyed map; a pre-existing file is backfilled on load. | The question "which thread is this work item in?" gets a keyed answer and a command, without moving a workspace-specific handle into the portable record (decision-094 kept it local, and a thread ts still means nothing on another workspace). |
| D4 | **A failed reply never opens a second thread.** Only "no binding" opens a root. | A transient Slack error splitting a conversation is the failure this work item exists to remove; an operator who really lost a thread deletes the state file, as documented. |

## Consequences

**Good.** One thread per work item by construction, under concurrency; a root a member
can read; a listing an operator can run; the kickoff and standing-session paths unchanged
in behaviour (their thread is the conversation).

**Costs, accepted.** One more API call per work item and one best-effort permalink call;
the scenarios that pinned `posted[0]` as the event are re-pointed; on a platform without
`flock` the exclusion degrades to today's behaviour with a debug line.

## Alternatives considered

| Alternative | Why not |
|-------------|---------|
| Keep the first event as the root; only add the lock | The root would still be an accident of ordering; the issue asks for replies, all of them |
| Store the thread in the portable work-item record | A thread ts is a handle into one workspace; the portable record is what is true on any machine (decision-046, decision-094) |
| Recover from a deleted thread by opening a new one on `thread_not_found` | Slack's error vocabulary for a missing parent is not stable enough to distinguish from a transient failure; splitting on a guess is the bug this fixes |
| A root carrying the issue title | Needs a ledger read from the channel; the unfurl shows it |
