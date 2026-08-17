# Decision 092: how many sessions a work item's pull requests get is the operator's choice — the tree is not

- **Status:** proposed
- **Date:** 2026-08-17
- **Work item:** [issue-258](https://github.com/MadaraUchiha-314/the-loop/issues/258)
- **Deciders:** maintainer (via ticket); harness (proposal)
- **Refines:** [decision-088](decision-088.md) — specifically **D1** ("same repository, same
  session", stated as a rule) and **D4** ("`sessionPerPr` keeps its name and its default",
  boolean). D2, D3 and D5 stand unchanged and are, in fact, what makes this decision
  affordable. Through 088 it also refines [decision-064](decision-064.md) D3.

## Context

Decision-088 D1 collapsed a same-repository pull request onto the work item's session
**whatever `sessionPerPr` said**, and wrote the reason down plainly: *"a knob for it would be
a documented way to reproduce the bug."* That was correct about the bug. It was also the
removal of a choice, and the option table it left behind offers two rows that agree on the
case an operator most often asks about:

| `sessionPerPr` | same-repository pull request | pull request in another repository |
|---|---|---|
| `true` (default) | work item's session — **forced** | its own session |
| `false` | work item's session | work item's session |

The ticket's author — the same person who accepted 088 the day before — asked for the choice
back: *"users should have an option to choose whether all the PR related sessions are
individual tmux+claude sessions or one single tmux+claude session."*

The question this decision has to answer is therefore **not** "should the collapse be
optional?" — that has been answered by the person whose call it is. It is: *what has to be
true for the option to be safe, and what is the honest thing to tell an operator who turns it
on?*

Re-reading 088 with that framing, D1 conflated two claims:

1. **Two harness conversations must never share a working tree.** True in every
   configuration, not negotiable, and already enforced at a seam of its own (D2,
   `_endpoint_cwd`).
2. **A same-repository pull request can never have a tree of its own.** Asserted, and only
   *nearly* true — 088's own Alternatives section names why ("a second worktree on one branch
   is a git error"), which is a fact about `strategy: worktree`, not about the case.

Claim 1 is the invariant. Claim 2 was a property of one strategy promoted to a rule.

## Decision

**`routing.tmux.sessionPerPr` becomes three named modes; decision-088 D2 becomes the thing
that makes the widest of them safe.**

| Sub-decision | What was chosen | Why |
|---|---|---|
| **D1 — three values, not two** | `never` · `cross-repository` (default) · `always` | The ticket asks for a choice between "individual" and "one single", and the default sits between them. Three names say what three behaviours are; a second boolean beside the first would give four states, one of them meaningless. |
| **D2 — the booleans keep parsing** | `true` → `cross-repository`, `false` → `never` | Every config file in existence carries one. A key that silently changes meaning on upgrade is a worse release note than a key that grew names. |
| **D3 — an unrecognised value resolves to `cross-repository`, with a warning** | fail closed to the shipped default | Same shape as `routing.interaction.mode`. A typo must never land on the widest choice, and must never be silent. |
| **D4 — decision-088 D2 is not relaxed, it is *extended*** | a same-repository endpoint's checkout must also **hold the pull request's head branch** (`Workspace.prepare(require_branch=True)`) | This is the whole safety argument. Without it, `git worktree add -B` fails because the work item's session holds that branch, `ensure_worktree` falls back to a **detached default-branch** tree, and that tree has a *distinct path* — so 088's `_same_path` guard passes and the-loop announces a session for pull request #N sitting on `main`. Wrong tree is worse than no session. |
| **D5 — `always` is served by `strategy: clone`, and says so** | documented obligation, enforced by the decline | An independent clone has no sibling worktree to conflict with. Under `worktree` the endpoint declines and the event lands in the work item's session — the pre-issue-258 behaviour, reached by the safe path rather than by a rule. |
| **D6 — the requirement is narrow** | `require_branch` is passed for a **same-repository** endpoint only | A cross-repository endpoint's fallback is a tree in the *right repository* on its default branch — imperfect, and deliberately tolerated by issue-183 for a head ref origin has not seen yet. Making the raise unconditional would change behaviour nobody reported. |

Nothing else moves. No new event name, no new `reason` value, no change to `pullRequests[]`,
no state migration, and the default behaviour is byte-for-byte what it was.

## Consequences

- **An operator can now get what the ticket asked for**, and the-loop tells them what it
  costs: a workspace root, `strategy: clone`, and one harness conversation per pull request
  to pay for.
- **`always` under `strategy: worktree` is a no-op that reports itself.** Not silently: the
  decline is `session.pr_session_declined` with the git error naming the branch and the
  worktree already holding it. "Why is there only one session?" stays answerable from
  `the-loop events`, which was 088 D5's whole point.
- **The wrong-tree failure mode is now impossible in *both* directions.** Before this change
  a same-repository endpoint could not exist; after it, one can exist only on the pull
  request's own branch. The intermediate state — an endpoint on the default branch — was
  reachable in neither, and is now explicitly refused rather than merely unreachable.
- **Inner loops (`pdlc-pr-loop`) apply to same-repository pull requests again under
  `always`.** That is the pre-issue-253 behaviour, and it is what an operator choosing
  `always` is choosing. Under the default it stays what 088 made it: a cross-repository
  contribution's loop.
- **Risk moved up a tier.** 088 D4 kept the boolean partly to stay at tier 3; this changes a
  config schema (`autonomy.sensitivePaths` matches `**/*schema*`), so it is tier 4 —
  human approves the pull request, with a security review recorded.
- **Two different work items still share `spawnWorkdir` by default.** Out of scope here as
  it was in 088; unchanged in either direction.

## Alternatives considered

- **Leave 088 D1 alone and close the ticket.** Not available: the person who accepted D1
  asked for the option, which is the one input a "rule, not a setting" argument cannot
  outrank.
- **A second boolean, `sameRepositorySessionPerPr`.** Four states from two keys, one of
  which (`sessionPerPr: false` + `sameRepository: true`) has no meaning and would have to be
  documented away. A key whose valid values depend on another key's is a key nobody reads
  correctly.
- **`always` without the branch requirement.** The cheapest change and the one that
  reproduces #253's *symptom* in a new form: a second session, silently on the wrong code.
  088's warning was right about this; the answer is the requirement, not the refusal.
- **Teach `Workspace` to give a same-repository endpoint a detached worktree at the pull
  request's head.** It would be on the right *commit*, and unable to commit back — the branch
  name is taken by the sibling worktree. An agent that cannot push is not a session.
- **Make `require_branch` unconditional for every endpoint.** Tidier, and it silently
  removes the degradation issue-183 relies on for a fork or unpushed head ref. Rejected as
  scope the ticket did not ask for; recorded here so a future reader knows it was weighed.
- **A per-work-item override in the spec front matter.** The ticket says *users*, meaning the
  operator and their deployment. A per-item override is a different question, and nobody has
  asked it.
