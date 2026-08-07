# Decision 064: One session record per work item carries its pull requests — each PR an endpoint with its own session

- **Status:** proposed
- **Date:** 2026-08-07 (revised the same day — see § How this decision changed)
- **Deciders:** @MadaraUchiha-314 (issue #172, PR #173 review)
- **Work item:** issue-172
- **Spec:** `docs/specs/issue-172/`
- **Refines:** [decision-036](decision-036.md) (an event on a PR resolves the PR's linked
  issues first), [decision-039](decision-039.md) (a work item may be delivered by several
  PRs, so only the object that closed is ended) and [decision-046](decision-046.md)
  (generated state is grouped by whether it travels). Nothing in any of them is reversed:
  this persists decision-036's *outcome* instead of recomputing it, expresses
  decision-039's close rule in the data model, and adds no new generated path for
  decision-046 to classify.

## Context

[Issue #172](https://github.com/MadaraUchiha-314/the-loop/issues/172). Since decision-036,
an event on a PR routes to the issue the PR is linked to. The decision is correct. What was
missing is that it was never written down — it existed only as the return value of
`linked_issue_numbers()`, recomputed from `gh`'s `closingIssuesReferences` on every single
event. Unlinking the PR in GitHub's Development panel, editing out the closing keyword, a
`gh` too old for the field, or one transient GraphQL error re-pointed routing at the PR
itself — past a session that was still running — and the event was dropped or answered
with a duplicate session.

A second fact, latent until now: the-loop had **one conversation per work item**, however
many PRs delivered it. A spec PR and an implementation PR — decision-039's own scenario —
interleaved their events into a single session.

## Decision

**The work item's session record is the single source of truth for everything about its
sessions.** One file per work item, carrying the item's own session *and* a
`pullRequests[]` list — one entry per PR delivering it, each an **endpoint**: its own
tmux session and its own harness conversation, recorded the moment the routing decision
is made.

```json
{
  "workItem": {"ref": "github:octo/repo#15", "…": "…"},
  "harnessSessionId": "0f1c…", "tmuxTarget": "loop-github-octo-repo-15",
  "pullRequests": [
    {"workItem": {"ref": "github:octo/repo#16"}, "harnessSessionId": "77ab…",
     "tmuxTarget": "loop-github-octo-repo-16", "status": "active"}
  ]
}
```

| Sub-decision | What was chosen | Why |
|---|---|---|
| **D1 — the PRs live on the work item's record** | `pullRequests[]`, one file per work item | Owner decision (PR #173 review). Everything about a work item — every PR delivering it, every tmux session and conversation involved — is answerable by reading one record. The reverse-scan cost this repo's first draft avoided is real but small: it is paid only by a ref with no record of its own, over the handful of live work items on one machine — never anything that grows with history. |
| **D2 — each PR is an endpoint, one type** | a PR entry is a `Session` whose `work_item` is the PR's ref | Record and endpoint share one type, so the whole dispatch path — deliver, respawn, resume, close — operates on either without knowing which it has. Nesting is one level and stays that way: a PR does not have pull requests, and a hand-edited tree is flattened on read. |
| **D3 — per-PR sessions are configured, on by default** | `routing.tmux.sessionPerPr: true` | Owner decision. A work item with two PRs has three tmux sessions: its own (which receives issue events) and one per PR, spawned lazily by the first event that needs it. `false` collapses every PR's events into the work item's single session — the pre-issue-172 behaviour, kept as a choice rather than discarded. |
| **D4 — recorded where the decision is made** | on dispatch into a matched record, and on spawn (after registration) | The binding is established by the same act that establishes the session, never re-derived from `gh` afterwards. A close event records nothing — it has nothing to bind. |
| **D5 — a PR closing ends its endpoint only** | `close_endpoint`: the entry flips to `closed`, its tmux session is torn down per the existing retention rules, the record stays live | decision-039's rule falling out of the model instead of being special-cased. A late event on a closed-endpoint PR falls back to the work item's session — the work item still owns the work. |
| **D6 — additive resolution** | a ref's own record first; the scan only where there is none | A recorded PR never suppresses a work item the derived linkage still finds, so a deliberate re-link delivers to both records — loud and recoverable, where the failure it replaces was silent. |
| **D7 — degradation is per-entry** | an unreadable `pullRequests` entry is skipped, never fatal | A hand-edited entry reads as "that PR is unrecorded" (the pre-issue-172 state for that PR); the work item's own session survives. Both ends of every entry re-parse through `WorkItemRef.parse`, so nothing unparsed reaches a lookup. |

### Known edge, stated rather than hidden

Two records can both claim one PR (a re-linked PR whose old and new work items both
match). Their endpoints would contend for the PR's one deterministic `loop-<slug>` tmux
name; the loser's spawn fails and that record's copy of events falls back to its work-item
session. Loud, bounded, and inherent in D6's both-deliver choice.

## The direction this sets: inner and outer loops

The owner's review names where this model goes
([PR #173](https://github.com/MadaraUchiha-314/the-loop/pull/173)): the **outer loop** is
the work item's process graph — the PDLC the-loop already executes
([decision-041](decision-041.md)). The **inner loop** is a PR's own, smaller graph — in
service of delivering the work item, with a subset of the nodes (testing and review
certainly; requirements definition certainly not). The endpoint model built here is the
substrate: an inner loop needs a per-PR conversation to run in, and that is exactly what a
`pullRequests[]` entry is. Defining the inner-loop graph — its nodes, its artifacts, and
how it reports into the outer loop — is follow-up work with its own work item and spec;
**in this change a PR endpoint deliberately has no graph**, so a PR cannot advance, or
open, a second graph on the work item's spec directory.

## How this decision changed

The first version of this record chose a **separate link file per PR**
(`<slug>.link.json`) over a list on the session record, on two grounds: the reverse scan,
and a read-modify-write race between the two ingresses. The owner rejected it in review,
and the grounds did not survive re-examination: the scan is over live work items only
(small, bounded), and the race is real but is a locking concern — not a reason to shape
the data model around it — with the worst same-PR outcome being the same entry written
twice through an atomic replace. The single-record model also answers a question the link
files never could: *everything* about a work item's sessions in one place. This is the
paper trail of that reversal, kept rather than rewritten.

## Alternatives considered

- **A separate link record per PR** (`<slug>.link.json`) — this record's own first
  version. Rejected in owner review; see § How this decision changed.
- **`linkedRefs` as bare strings on the record** — the ticket's original sketch. Subsumed:
  once each PR can carry its own session, the entry must hold more than a ref, and a
  `Session`-shaped entry is what lets one dispatch path serve both.
- **Cache the derivation rather than the decision** — store `closingIssuesReferences` per
  PR and reuse it when `gh` fails. Rejected: it caches the *input*, so it still needs
  invalidation, and it answers nothing when the panel link is deliberately removed — the
  ticket's own reproduction.
- **Eager per-PR spawn** — give a PR its session when it is recorded, not on first use.
  Rejected: a PR that is merely linked would cost a tmux session and a harness process
  before anything happens on it.
- **Reap PR entries when their endpoint closes** — rejected: a closed endpoint is the
  record that the PR delivered this work item, and the fallback target for late events on
  it. The entry goes when the record goes.
