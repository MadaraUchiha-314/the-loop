# Decision 128: an attribute belongs to a party — the repository, the operator, or the machine

- **Status:** proposed
- **Date:** 2026-09-15
- **Deciders:** the-loop (architect, engineer), asked for and corrected by @MadaraUchiha-314 on PR #369
- **Work item:** [issue-368](https://github.com/MadaraUchiha-314/the-loop/issues/368)
- **Supersedes the scope of:** [decision-046](decision-046.md), which classified *files*
  by portability. That rule stands and is still what the `.gitignore` recipe implements;
  it simply never answered the question one level down.

## Context

[Issue #368](https://github.com/MadaraUchiha-314/the-loop/issues/368): *"various
attributes that are tracked by the-loop for a work item are scattered across many
different files and folders — some listed as portable, some as private — and there's no
principle-driven approach to this."*

The audit in `docs/specs/issue-368/requirements.md` confirmed it and found eight defects.
Four are the argument for this decision:

- **A work item's pull requests were recorded only in a file that never travels.**
  `local/<slug>.json`'s `pullRequests[]` was the only record that PR #7 in `octo/lib`
  delivered `#15`. After a hand-off the new machine re-derived that from `gh`'s closing
  references — the inference [issue-172](https://github.com/MadaraUchiha-314/the-loop/issues/172)
  stopped trusting — or lost it entirely for a pull request the-loop opened itself.
- **The Slack thread was recorded only in a machine-wide file.** On the next machine the
  next event opened a second root, and replies in the first were dropped as `unmapped`.
- **A machine handle was checked into the repository.** `work-item-state.json` carried a
  `session` block: a resumable harness conversation id, in a file that is public and
  proposable by anyone who can open a pull request.
- **One work item produced N+1 portable records.** The poller lists a labelled pull
  request as an item of its own and baselined each into its own file; the control plane
  then reconciled the two identities client-side
  ([issue-302](https://github.com/MadaraUchiha-314/the-loop/issues/302)).

Decision-046 could not have prevented any of them. It answers *does this file travel?*
Nothing answered *where does this attribute go?*, so each new attribute landed wherever
its writer already had a file open.

## Decision

**Every attribute of a work item belongs to one of three parties, and the party decides
the file — because who may write a file decides what may be in it.**

| Party | File | What it holds |
|---|---|---|
| the **repository** | `docs/specs/<id>/work-item-state.json` (on the work item's branch) | the pointer; every choice a human froze; the pull requests delivering it |
| the **operator** | `<state.root>/portable/<slug>.json` | what an authorized human told this deployment; what it has already seen; the channel thread it opened |
| the **machine** | `<state.root>/local/<slug>.json` | one session per ref it serves; what it has already mirrored |

Every attribute is written **once**. Any other file that needs it carries an identity — a
ref, a thread ts — never a second copy of the record. The classification is data
(`the_loop.state.ATTRIBUTES`), and a test fails the build when a file grows a key no entry
claims, when a kind sits in a file its rule forbids, or when `docs/cli/state.md` and the
declaration disagree.

Concretely: `sessionPerPr`, `model`, `effort` and `pullRequests[]` move into the
repository's file; the portable `graph` section is retired; the `session` block leaves the
repository and `session: inherit` resolves through the machine's session registry; a pull
request's poll ledger is keyed under its owner's record so one work item is one portable
record; the channel binding moves to the operator's record and the read cursor to the
machine's.

## Why not the ticket's literal proposal — everything in `work-item-state.json`

The ticket proposed one file for the work item and one for local tracking, and named
`work-item-state.json` for the first. It **is** the right file for everything the
repository may know, and this change moves four more things into it. Three attributes
cannot follow, for the same reason:

- `control` decides whether an unattended agent runs;
- `collaborators` decides whose comments it reads;
- `ended` decides whether the item is over.

On the work item's branch each is proposable by any pull-request author and editable by
the agent whose behaviour it governs. And after `the-loop cleanup` the checkout is gone,
while the daemon and any control plane still need all three. The Slack thread cannot
follow either: a channel id, a member id and a workspace permalink are the operator's, not
the repository's.

So the ticket's principle — *a remote entity created for a work item is tracked in a file
related to that work item* — is honoured for both kinds of entity. A pull request is an
object of the **repository**, and goes in the repository's file. A thread is an object of
the **operator's workspace**, and goes in the operator's file, which is also a file
related to the work item.

## Consequences

- A hand-off now carries what a hand-off should: the branch says which pull requests
  deliver the item and what it runs on; the operator's one record says it is armed, who
  may speak to it, what has been seen on the item and on each of its pull requests, and
  which thread carries it. The new machine's `local/` is empty, which is correct.
- The daemon reads one state file from a checkout it already resolved to answer
  "how many sessions do this item's pull requests get, and what does it run on?". That
  file is agent-writable, so every value is re-validated on the way in — a model only
  ever resolves to one the operator declared and this machine accepts, a mode only to one
  of three. `repos`, which decides where an unattended agent opens pull requests, has
  lived in that file since issue-365.
- A work item upgraded mid-flight inherits its session once less: the `session` block is
  ignored from the first run on the new release, and the registry does not yet hold a
  binding for a gate entered in that window.
- Every old shape is read and rewritten on its next save. Nothing migrates in bulk and
  nothing is deleted — including the portable records a pull request was given before
  this change, which is why the control plane's client-side join stays.

## Alternatives rejected

- **Leave the files alone and document the drift.** The audit is the documentation, and
  it does not stop the next attribute landing in the wrong file. A rule nothing enforces
  is a convention, and conventions are what produced the four defects above.
- **One file per work item, full stop.** The ticket's reading, and the three attributes
  above are why it cannot be. Rejected on authorization and on lifetime, not on tidiness.
- **Keep a derived copy of the frozen choices in the portable record** so a reader with no
  checkout can see them. That is the duplication the ticket objects to, and the only
  reader that wanted it — the control plane — already calls `the-loop check`.
