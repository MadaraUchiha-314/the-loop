---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#307"
phase: needs-review
status: in-progress
---

# Execution Log: per-work-item collaborators

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-31 | — | Tier 4 (`human-approves-pr` **plus** a named human security sign-off, `security.review.humanSignOffMinTier: 4`): the change widens the prompt-injection boundary, and touches `**/*schema*`. Brainstorming skipped — the issue states the model and its three constraints |
| requirements-definition | 2026-08-31 | | [`requirements.md`](requirements.md) — six requirements, nine abuse cases. R3 is the whole permission model in one sentence |
| design | 2026-08-31 | | [`design.md`](design.md) — one store, two guarded seams, two words in an existing vocabulary; six alternatives recorded, including the two that were tried and put back |
| test-planning | 2026-08-31 | | [`testing-plan.md`](testing-plan.md) — sixteen rows, thirteen applicable |
| tasks-breakdown | 2026-08-31 | | [`tasks.md`](tasks.md) — eleven tasks |
| implementation | 2026-08-31 | | On `claude/github-issue-307-wuv951` |
| verification | 2026-08-31 | | [`evidence/verification.md`](evidence/verification.md) — 2771/2771, ruff, pyright, seven configs and 908 markdown files clean; [`evidence/security-review.md`](evidence/security-review.md) — nine abuse cases, eight closed and one accepted-unchanged |
| needs-review | 2026-08-31 | | PR raised; awaiting the owner **and** the named human security sign-off tier 4 requires |
| complete | | | |

## What was delivered

`routing.authorizedUsers` was the whole of the-loop's GitHub identity model, and it is
**global**: a login directs every work item the daemon watches, or none. The cost was not
that a domain expert had less power — it was that they were **invisible**. Both ingress
paths drop a non-authorized author's comment before anything reads it, so an agent that
asked a question and is waiting for the one person who knows the answer never heard the
reply, and the operator's only options were to hand that person the whole deployment or
to relay by hand.

A **work-item collaborator** is the missing middle, and its permission model is one
sentence: *a work-item collaborator supplies input on one work item; an authorized user
directs the loop.*

- **A roster per work item**, in a fourth section of its portable record beside `control`,
  `poll` and `graph` — because "an authorized user invited Dana onto this item" is true on
  any machine. Each entry records who granted it, when, through which surface, and the
  comment's URL. It is cleared when the item closes and by `sessions reset`; `cleanup`
  keeps it, as it keeps the control record.
- **Two new control keywords**, `the-loop add-collaborator @login` and
  `remove-collaborator` — the first commands in this vocabulary to take an argument. The
  narrowness the parser promises is kept by construction: the argument is matched against
  GitHub's login grammar and refused if it does not fit, and scanning stops at the first
  token after the keyword that is not an `@login`, so several people can be named and the
  prose after them stays prose.
- **Two ingress seams widened, and two action seams checked.** The router and the poller
  now let a granted login's comment through — and *only* through: the control path's
  named-and-allowlisted-actor re-check, which existed as belt-and-braces for actor-less
  poll comments, is now load-bearing and asserted directly, and the spawn seam gained one
  of its own (`collaborator-no-spawn`, settled rather than retried). The graph's human
  gates were not touched, which is the point — and is tested, because "we didn't change
  that file" is not evidence.
- **Two CLI verbs**, `the-loop add-collaborator @dana --work-item <ref>` and its sibling:
  local effect first, ticket comment after as a report, every login validated before any
  of them is written, and in-process for the reason `ask` is.

## Decisions and their paper trail

- [`decision-102`](../../decisions/decision-102.md) — a work-item collaborator is input,
  never authority; the grant is state on the work item rather than policy in the config;
  the argument is a login or nothing; both action seams are checked explicitly; membership
  is asked only about the refs the event named; the CLI verbs run in-process.
- **The spawn seam's condition was tried both ways.** The broader form ("any named actor
  outside `authorizedUsers` may not spawn") is stronger and was implemented first; it
  changed behaviour for sixteen existing tests that drive a dispatcher directly with an
  empty allow-list — a state the router makes unreachable in production. The narrower,
  two-part form states exactly what R3.2 asks for and leaves every existing path alone;
  the reasoning for writing both halves out rather than relying on the inference behind
  them is in `design.md` §3 and flagged for the reviewer in `evidence/security-review.md`.
- **`cleanup` does not clear the roster.** R1.6 said it did in the first draft; issue-186
  defines `cleanup` as local resources only, keeping the portable record, so the roster
  stays with the control record it sits beside. Corrected in the requirements before
  implementation, and the keyword's own documentation now lists the roster among what it
  keeps.
- **The word "collaborator" was kept, deliberately.** `.the-loop/collaborators.yaml`
  already means something else — a project's stewards and their roles, read by the plugin
  and never by the daemon. The ticket asked for `the-loop add-collaborator`, so the
  spelling stands and the code and docs say *work-item collaborator* in full wherever the
  two could be confused, rather than inventing a word nobody asked for.

## Open for the reviewer

1. **The named human security sign-off** tier 4 requires
   (`security.review.humanSignOffMinTier: 4`). The abuse-case table and its verdicts are
   in [`evidence/security-review.md`](evidence/security-review.md).
2. **The permission ceiling.** A collaborator cannot satisfy a human gate — not even to
   *request changes*. That is deliberate and recorded as deferred scope, not as
   impossible; if the intent behind the ticket was richer, the place to say so is
   decision-102 D1.
