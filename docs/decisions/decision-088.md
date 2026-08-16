# Decision 088: a work item's own pull request is the work item's session — an endpoint needs a tree, not a toggle

- **Status:** proposed
- **Date:** 2026-08-16
- **Work item:** [issue-253](https://github.com/MadaraUchiha-314/the-loop/issues/253)
- **Deciders:** maintainer (via ticket); harness (proposal)
- **Refines:** [decision-064](decision-064.md) — specifically **D3**, "per-PR sessions are
  configured, on by default". D1, D2 and D4–D7 stand unchanged: the record still carries
  `pullRequests[]`, an endpoint is still a `Session`, the binding is still recorded where
  the decision is made, a close still ends one endpoint, resolution is still additive and
  degradation is still per-entry.

  > **Decision 088 numbering.** [PR #244](https://github.com/MadaraUchiha-314/the-loop/pull/244)
  > is in flight and has claimed 087 on its branch. 088 is taken here to avoid the
  > collision that PR already had to resolve once; renumber if #244 is abandoned.

## Context

Decision-064 D3 said each pull request delivering a work item gets its own tmux session and
its own harness conversation. It did not say **where that session runs**, and the
implementation had only one answer available: `record.cwd`, the work item session's own
working tree.

`Workspace.prepare` keys both of its strategies on the **work-item slug**, so there was no
configuration — not `spawnWorkdir`, not a workspace root, not `worktree` or `clone` — under
which an endpoint got a checkout of its own. "Its own conversation" therefore always meant
"a second agent in the work item's tree, on the work item's branch, with no lock."

It went wrong the first time an item exercised it seriously. On
[issue-239](https://github.com/MadaraUchiha-314/the-loop/issues/239) the work item's session
and its pull request's session ran the same four verification activities against the same
tree, restarting each other's services, repointing the session registry mid-measurement and
committing under one another
([the write-up](https://github.com/MadaraUchiha-314/the-loop/pull/244#issuecomment-5309264856)).
The two results agreed, which was luck; the item's ticket meanwhile carried eight
`loop:<phase>` labels at once, because two walkers were advancing one item's state.

The aggravating case is not exotic. `outer-loop-on-pull-request` (issue-183) puts the outer
loop's artifacts and its human gates **on the pull request**, so the work item's own session
is already the conversation posting there. Splitting a second session onto it guarantees two
owners.

## Decision

**A work item's session owns the work item, its branch, its checkout and every pull request
it opens in its own repository. An endpoint gets a conversation only when it gets a working
tree.**

| Sub-decision | What was chosen | Why |
|---|---|---|
| **D1 — same repository, same session** | a pull request in the work item's own repository routes to the work item's session, whatever `sessionPerPr` says | It is the work item's own delivery, on the work item's branch, in the work item's checkout. There is nothing for a second conversation to own. Stated as a **rule**, not a setting: two owners in one tree has no correct configuration, and a knob for it would be a documented way to reproduce the bug. |
| **D2 — a session needs a tree** | an endpoint spawns in a checkout produced for **it** (keyed on the pull request's slug, in a clone of that pull request's repository), or it does not spawn | Makes D1 true at the spawn seam rather than assumed, and hands the cross-repository inner loop the thing it was always missing. Without `routing.workspace.root` there is no such checkout, so no session — the event goes to the work item's session and the refusal is recorded. |
| **D3 — the rule is checked before the endpoint lookup** | `_endpoint_for` tests the repository before `record.endpoint_for(pr)` | An endpoint spawned by an older the-loop is a second owner that *already exists*. Testing the repository first stops routing feeding it. Nothing is torn down: `the-loop cleanup` already ends a work item's endpoints, and killing a live conversation to enforce a routing rule would destroy in-flight work. |
| **D4 — `sessionPerPr` keeps its name and its default** | unchanged key, unchanged default, narrower meaning | It still means what it says for the case that still splits (another repository), and `false` still collapses everything. No schema change — which also keeps this at risk tier 3 instead of buying tier 4 for a knob nobody should turn. |
| **D5 — every refusal is an event** | `session.pr_session_declined` with `reason: no-separate-checkout \| workspace-failed` | A session that is *not* spawned is invisible otherwise, and "why is there only one session?" must be answerable from `the-loop events` rather than from this file. |

## Consequences

- **In the default configuration a work item has exactly one session again** — the
  pre-issue-172 shape, which `pdlc-work-item-loop.yaml` already describes as supported:
  "a work item with no inner loops — one agent, one session — passes `await-inner-loops`
  vacuously and behaves exactly as before."
- **The inner loop narrows to what it was actually built for.** `pdlc-pr-loop` and
  issue-183's `pr-loops/<owner>__<repo>/pr-<n>/` state now apply to cross-repository
  contributions, which is where a second session has a second tree to work in.
- **A same-repository pull request no longer walks an inner loop**, so its events advance
  the work item's own loop instead. This is the behaviour every work item in this
  repository has actually had in practice; the inner state was a second pointer nobody read.
- **Deployments with no workspace lose the cross-repository endpoint session** they
  nominally had. They never had a usable one: it ran in the wrong repository's checkout.
- **What is not solved:** two *different* work items still share `spawnWorkdir` by default.
  That is a wider question than this ticket, recorded as out of scope in
  [`docs/specs/issue-253/bugfix.md`](../specs/issue-253/bugfix.md).

## Alternatives considered

- **Give every pull request its own worktree, same-repo included.** More machinery, and it
  still leaves a single-pull-request work item with two owners — the complaint. A same-repo
  pull request is worked on the work item's branch, and a second worktree on one branch is
  a git error, not a design.
- **A machine-wide "one session per tree" lock.** The default `spawnWorkdir: "."` puts every
  work item in one directory, so this breaks the common deployment.
- **Read the frozen `outer-loop-on-pull-request` surface at dispatch.** Same verdict as the
  repository rule for every observed case, at the cost of a graph read on the dispatch path,
  and it would still let the `work-item` surface double up.
- **Set `sessionPerPr: false` in this repository and close the ticket.** Fixes one machine,
  leaves the default broken for everyone, and also disables the case that genuinely works.
