# Decision 095: the weakest linkage source earns its place, and the record answers before GitHub is asked

- **Status:** proposed
- **Date:** 2026-08-18
- **Work item:** [issue-269](https://github.com/MadaraUchiha-314/the-loop/issues/269)
- **Deciders:** MadaraUchiha-314 (owner, via the ticket and its comment), the-loop (proposal)
- **Refines:** [decision-036](decision-036.md) (a PR event resolves its linked issues first),
  [decision-064](decision-064.md) (the routing decision is recorded, not recomputed),
  [decision-069](decision-069.md) (a work item's contributions may span repositories)

## Context

`issue-285` in a branch name became `org/lib#285` — a work item that does not exist — and
nothing between the regex and the tmux session asked whether it did. Of the three linkage
sources decision-036 established, two *state* the repository they mean (GitHub's own
`closingIssuesReferences`; a qualified closing keyword). The third, the-loop's own
`issue-<n>` branch convention, does not: decision-069 settled that it "stays local", which
is correct as far as it goes and is a **guess** about which repository — and no guess about
existence at all.

The guess was then promoted. Linked items are emitted before the entity's own number, so
the fabricated ref became `work_items[0]`, which is what `_spawn_refusal`, `_apply_control`,
`_on_unmatched` and `_record_graph_command` all read. The operator's `the-loop start` was
recorded against a ref that 404s, a full session spawned for it — clone, registry entry,
tmux session — and the announcement came back `gh: Not Found (HTTP 404)` seconds later,
which the daemon logged and ignored. The real work item, with its whole spec chain, sat in
the other repository.

The owner's direction on the ticket named the answer for the second half: *"whenever user
responds to a PR, the-loop should check what work item that PR is linked to — not through
GitHub, but through internal tracking mechanisms."*

## Decision

| Sub-decision | What was chosen | Why |
|---|---|---|
| D1 | The router records each ref's **provenance**; a ref resting on the branch convention **alone** is the only one ever checked | Provenance is what makes a targeted guard possible. Checking every ref would put a network call on the routing path for links GitHub itself stated, and would make decision-069's cross-repository routing depend on an API that can be down. A ref the branch *and* another source name is corroborated and is not weak. |
| D2 | Only a **definitive HTTP 404** drops a ref; every other answer keeps it | Fail-closed here would mean "route nothing while GitHub is unreachable" — a worse failure than the one being fixed, and one that would arrive silently. The guard exists to delete a fabrication, not to gate real work, so *unknown* restores exactly the prior behaviour. |
| D3 | The **record answers first**: a live session (its own ref, or a durable PR → work-item binding) is the target for control, the start test and the spawn — and where one exists, the check is not consulted at all | The owner's direction, and decision-064's model finally reaching the three call sites that were still reading a list index. It also makes the guard nearly free: an established work item's every comment would otherwise pay for a question whose answer changes nothing. |
| D4 | The ticket's second bullet — "a control command on a PR binds to the PR's own ref" — is satisfied **by D1**, not by binding to `pr_work_item()` | Binding to the pull request unconditionally would regress decision-036: `the-loop start` on a pull request that legitimately delivers issue #100 must still start #100. With the ghost dropped, the pull request *is* the first surviving ref in the ticket's scenario — the outcome asked for, without the regression. |
| D5 | The announcement's 404 is **reported and remembered**, never acted on by killing the session | GitHub answers 404 for repositories a credential cannot see, so the signal is ambiguous; ending a live agent's session and its checkout on it destroys work. The pre-spawn check is where a ghost is stopped. `session.work_item_missing` (error level) is the record, and it feeds the same cache, so the *next* event acts on the evidence. |
| D6 | A polled pull-request comment is a pull-request event | The poller synthesises the comment over the pull request's own payload and renames it `issue_comment`; the router read only `payload["issue"]` for that name, so on that ingress no binding was ever written from a comment and no endpoint was ever chosen for one — D3's "internal tracking" had nothing to track with. One fallback, unreachable from a real webhook. |
| D7 | No configuration key, and no schema change | Correctness, not preference: one cached call for the one ref shape that can be fabricated, degrading to a no-op where `gh` is absent. A key would also touch `cli-config.schema.json`, a declared sensitive path, for a choice nobody should have to make. |
| D8 | A small `the_loop/linkage.py` rather than reusing `poller.github.GhClient` | `poller.github` imports `webhook.router`, so importing it from the dispatcher closes an import cycle — the same reasoning that moved the `sessionPerPr` vocabulary down to `prsessions.py` in decision-093. |

## Consequences

**Good.** The fabrication that could reach a spawn is deleted at intake, before matching,
control or spawning can act on it; "what was started", "what is running" and "what a command
acts on" now come from one seam; the poll ingress gains the pull-request bindings and
endpoint routing it never had; and the daemon's own 404 evidence stops being decoration.
Nothing in the ingress, the arming gate or the authorization model moves — the guard is
strictly subtractive.

**Costs, accepted.** Routing gains a *bounded, conditional* network dependency: one `gh`
call per fabricated ref, cached, on the ingress thread with a 10s timeout — and none at all
for an event a live record already owns. A deployment without `gh` on PATH keeps the old
behaviour and is told so once. D2 means a work item deleted while its session runs is still
never noticed by this path (the closure reconciler's job, unchanged), and D5 means a
genuinely nonexistent work item named by a *closing keyword* still spawns once before
anything says so — loudly, now.

**Out of scope, deliberately.** Pre-start comments are still never replayed: a comment
dropped `awaiting-start` keeps its delivery id forever, which the ticket flags as "possibly
its own issue" ([#270](https://github.com/MadaraUchiha-314/the-loop/issues/270)) and which is
a product decision about replay semantics rather than linkage correctness.

## Alternatives considered

| Alternative | Why not |
|-------------|---------|
| Verify every linkage source | A network call on the routing path for links GitHub itself stated, and a network dependency for cross-repository routing that decision-069 deliberately made offline. |
| Demote branch-derived refs so they can never be `work_items[0]` | Breaks the single-repository main path, where the branch is routinely the *only* linkage the-loop has — the-loop's own branches are named that way on purpose. |
| Bind a pull request's control command to `pr_work_item()` | Regresses decision-036 (see D4): a start on a PR delivering issue #100 must start #100. |
| Abort the spawn on the announcement's 404 | 404 is what GitHub says about a repository a credential cannot see; killing a live agent's session on it destroys work over an ambiguous signal (D5). |
| A `routing.verifyBranchLinkage` toggle | An operator asked to choose between "routes ghosts" and "correct" has not been given a choice (D7), and the key would touch a sensitive-path schema file. |
| Carry provenance on `RoutedEvent` | Two ingresses build that object and a third caller builds one by hand; a pure function of `(event, payload)` cannot be forgotten by one of them. |
