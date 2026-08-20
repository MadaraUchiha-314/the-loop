# Decision 098: the component that opens a pull request is the one that records what it delivers

- **Status:** proposed
- **Date:** 2026-08-20
- **Work item:** [issue-274](https://github.com/MadaraUchiha-314/the-loop/issues/274)
- **Deciders:** MadaraUchiha-314 (owner — "Let's go with (1)" on the ticket), the-loop (proposal)
- **Refines:** [decision-064](decision-064.md) (one record, every PR that delivers the work
  item), [decision-095](decision-095.md) (the record answers before GitHub is asked),
  [decision-097](decision-097.md) (a refused delivery is settled, not pending — which is why
  this bug is permanent rather than merely intermittent)

## Context

The router answers "which work item does this pull request deliver?" from four sources, in
order: GitHub's own `closingIssuesReferences`, the `issue-<n>` head-branch convention, a
closing keyword in the pull request body, and — since issue-172 — the durable
`session.pr_linked` binding on the work item's session record.

A spec pull request **the-loop's own session opens** satisfies none of them. It carries no
closing keyword on purpose (merging Phase 1 must not close the ticket), so GitHub records no
link and the Development panel stays empty; its branch is `loop/<id>-…`, which is the-loop's
convention, not the router's; and the fourth source was written by exactly one caller —
`Dispatcher._record_pr_binding`, which runs *when a routing decision is made*, and therefore
only once the linkage is already derivable. Circular.

So a human review comment on that pull request resolved to the pull request as a work item of
its own, which nobody armed, and was refused as `awaiting-start`. Since decision-097 that
refusal is *settled*: the comment is baselined and never re-evaluated, so repairing the
linkage afterwards recovers nothing. The phase gate the-loop itself posts — *"review the
requirements on the spec PR; comments there route back to this session"* — was a dead letter.

The-loop **knew** the answer. Its execution log and its own gate comment both say which pull
request it opened for which work item. Nothing recorded that knowledge where the router
reads it.

## Decision

| Sub-decision | What was chosen | Why |
|---|---|---|
| D1 | **Fix 1 of the ticket's three: author linkable pull requests.** The session that opens a pull request records the binding in the same step | The owner's call. It is also the only one of the three that removes the guesswork rather than adding to it: the authoring component holds the fact with certainty, and every other source is an inference about what somebody else wrote. |
| D2 | The operation is `link_pull_request` in `core.sessions`, surfaced on the CLI (`sessions link-pr`), the HTTP API (`POST /api/v1/sessions/link-pr`) and MCP (`link_pull_request`) — plus the SDK namespace that mirrors core | The layering rule (decision-056 / issue-161): core owns the logic, surfaces render it. A session may be an agent with MCP, a command in a terminal, or an embedder; all three must reach one implementation or they will drift. |
| D3 | **Idempotent, and idempotence stays a property of the store** | The authoring step is re-run — a retried command, a resumed session, a second `link-pr` in a stacked series. `SessionRegistry.link_pull_request` already returns `None` for "already listed"; re-deciding that in the new function would be a second place to be wrong. |
| D4 | **No session record, no write** (exit 1) | Recording an endpoint for a record that does not exist would invent a work item — the failure mode issue-269 spent a whole work item removing. The operation binds a pull request to a session that exists; it never creates one. |
| D5 | A bare pull-request number is resolved in the **work item's** repository; another repository is named by a full ref | A bare number is what a session that has just run `gh pr create` has to hand, and the work item's coordinates are the ones this call is certain of. The multi-repo shape (issue-183) states its repository explicitly, which is the only way it can be right. |
| D6 | Fix 2 (teach the router the `loop/<id>-…` branch convention) is **declined** | It adds a fifth inference where the defect is that inference was relied on at all. A branch name says nothing about which repository a work item lives in — the reason issue-269 had to add an existence check — and two conventions is two places to be wrong. |
| D7 | Fix 3 (make `awaiting-start` / `session-paused` settles retryable) is **out of scope**, not rejected | It is a real defect about *suppression*, not about linkage, and it is decision-097's judgement to revisit. With D1 the comment in this reproduction is never suppressed, so this bug closes without it. |
| D8 | Linking the issue in GitHub's **Development panel** with a non-closing reference is **not attempted** | GitHub populates `closingIssuesReferences` from closing keywords or from the web UI; there is no API for a non-closing link. A closing keyword on a spec PR would close the ticket at Phase 1 — the thing the spec PR must not do. |
| D9 | The rule is stated in **four** workflow places, beside the labelling rule it is the twin of | An operation nothing calls fixes nothing, and this one is called by an agent following prose. It lands where "label every PR you open" already lands: the automation reference, `work-on`, `execute-tasks`, and the execution-log template. |
| D10 | Recording the binding is **best-effort** for the session, exactly as registration is | The binding is how events *find* the session; it is not a precondition for doing the work. A failure is reported and the session carries on. |
| D11 | **No `unlink` verb** | Nothing in the reproduction needs one, and `sessions reset` already removes this machine's record for a work item. Adding a remover to fix a bug about a missing writer is scope the change has not earned. |

## Consequences

**Good.** A review comment on a the-loop-authored pull request reaches the session that
opened it, off a binding that is written rather than inferred — so it survives the things
inference does not: an emptied PR body, an unlinked Development panel, a `gh` too old for
`closingIssuesReferences`, a branch convention the router never taught itself. Nothing in the
router or the dispatcher changed, so every existing linkage keeps working exactly as it did;
this only adds an earlier writer for the source the router already prefers.

**Costs, accepted.** The agent has to run the step, and an agent that skips it gets today's
behaviour. That is the honest price of D1 over D6: certainty from the component that knows,
rather than a guess that always fires. D9 is the mitigation — the rule sits in every place
the labelling rule does — and the capability doc says plainly what happens without it.

**Out of scope, deliberately.** The router's inference sources (unchanged), the suppression
semantics of decision-097 (D7), and the companion bug in which the phase-selection gate never
runs, which is why the graph never froze the pull request as an endpoint either.

## Alternatives considered

| Alternative | Why not |
|-------------|---------|
| Teach the router `loop/<id>-…` (the ticket's fix 2) | D6: a fifth inference, resting on the weakest evidence there is. |
| Have the dispatcher detect PRs the-loop authored and bind them | The same inference wearing a different hat — "authored by the-loop" is a guess about a login, and it still needs a work item to guess at. |
| A flag on `sessions register` | The two facts are recorded at different moments: the pull request does not exist when the session registers. Linking would mean re-registering, which the one-active-session invariant makes awkward and `--force` makes dangerous. |
| Write the binding from the gate comment the-loop posts announcing the PR | It is the-loop's own comment, marked self-authored, and is never read back — deliberately, because reading own comments back is how loops are built. |
| Make the spec PR carry `Closes #N` | It would close the ticket when Phase 1 merges. |
