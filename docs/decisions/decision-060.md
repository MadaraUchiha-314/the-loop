# Decision 060: Testing is planned and verified as two nodes; the plan is the record, and a skip is not a decision

- **Status:** proposed
- **Date:** 2026-08-06
- **Deciders:** @MadaraUchiha-314 (issue #163)
- **Work item:** issue-163
- **Spec:** `docs/specs/issue-163/`
- **Refines:** [decision-041](decision-041.md) (the PDLC is an executable graph) and
  [decision-014](decision-014.md) (Gherkin scenario docstrings and contract-first APIs).
  Nothing in either is reversed; this adds the step that decides *which* kinds of testing
  a work item gets, and the step that proves they ran.

## Context

[Issue #163](https://github.com/MadaraUchiha-314/the-loop/issues/163). the-loop can only
claim a work item is done if it can verify it, and verification was the least declared
part of the loop:

- `design.md` carried a one-paragraph **Testing strategy**.
- `tasks.md` carried a `_Test:_` line per task.
- The graph's `implementation` node ran `verify-tests` — a hook that is a **no-op unless
  the node declares a command**, and no shipped node declares one.
- Everything after implementation (`self-review` … `reviewer-briefing`) is about opinion,
  not about proof. The `evidence` node gates on an execution-log section, but the section
  is written by the same agent that decided what to test, at the moment it is writing the
  PR.

So *which* kinds of testing applied, whether they ran, and what the evidence was were all
left to judgement at review time. That is the same shape as
[decision-045](decision-045.md)'s defect (a gate reporting success without running) and
issue-148's (prose describing a process the graph did not execute).

The ticket also names two things the-loop must **not** do: own the complexity of testing a
multi-repository system, and pretend a single test command covers every work item.

## Decision

**Two nodes, one new artifact, no new runtime concepts.**

```text
design-approval → test-planning → tasks-breakdown → implementation → verification → self-review
```

1. **`test-planning`** produces `testing-plan.md`, locked, carrying **Test matrix**,
   **Verification environment**, **Evidence plan** and **Verification results**.
2. **`verification`** re-declares the *same* artifact and gates on
   `checkmarks: complete` plus a non-empty **Verification results**.

| Sub-decision | What was chosen | Why |
|---|---|---|
| **D1 — plan before tasks** | `test-planning` sits between `design-approval` and `tasks-breakdown` | Each task's `_Test:_` names a matrix row. Planning after the DAG would reverse-engineer the plan from the tasks it is meant to constrain. |
| **D2 — no approval node** | The plan is locked and reviewed on the PR, with no human gate of its own | `tasks-breakdown` has no gate either, and the plan is closer in kind to the task DAG than to the design. A sixth stop would cost an approval round on every work item. |
| **D3 — the plan is the record** | `verification` re-gates `testing-plan.md` rather than minting a `verification-report.md` | One artifact, one diff: a reviewer reads intent beside outcome. A second artifact would need its own template, manifest entry and parity coverage, and would duplicate both the plan and the execution log's Final validation evidence. It is the shape `implementation` already uses to re-gate `tasks.md`. |
| **D4 — real phases** | Both nodes carry a `phase:`, so both get `loop:` labels | A node the ticket cannot show is not a node in the PDLC. The nodes that share `needs-review` do so because they are review *rounds* on one state; test-planning and verification are distinct states. |
| **D5 — catalogue, not enum** | The testing types live in the bundled template and `reference/testing.md`; the schema gains nothing | An enum would have to be exhaustive to be useful, and adding "chaos testing" would become a schema migration. The gate checks the section exists and is non-empty; the reviewer judges the content — the same footing as "no new attack surface is written and justified". |
| **D6 — declare, don't manage** | The plan states repositories, services, fixtures, credentials-by-reference and the project's own commands | the-loop **facilitates** verification and owns no runner, orchestrator or environment manager. Where an operator has written the setup down, the plan links the registered `customInstructions` doc instead of restating it. |

### The matrix rule

Rows are candidate testing types — unit, integration, contract, end-to-end, UI/visual,
snapshot, performance, security/abuse-case, accessibility, migration/upgrade, manual
exploratory, plus whatever the work item needs. **No type is mandatory in itself**; the
matrix is work-item dependent. What is mandatory is the *decision*: a type that does not
apply is `n/a` **with a written reason**. An unexplained blank is not a decision.

### Evidence

Evidence is committed under `docs/specs/<id>/evidence/`. A link to a CI run that expires
is not evidence. UI verification captures screenshots of each verified state, and an
animated capture (GIF or equivalent) when the behaviour under test is a *flow*. Because
the directory is as public as the repository, captures are **redacted** before they are
committed; one that cannot be redacted is not committed, and the results row says so.
Credentials appear in the plan **by reference only** — a literal secret in a committed
plan is a leaked secret, to be rotated rather than edited out.

### A skip is not a decision (the defect found while implementing this)

`run_chain` short-circuited on the first result that was not `pass` — including `skip`.
Two consequences, one cause:

- Hooks *after* a skipping one never ran. `design`'s chain is
  `validate-artifacts, enforces-boundaries-from, lint-artifacts`, and the middle hook
  skips whenever the upstream artifact is absent — taking the lint gate down with it.
- A chain *ending* in a skip routed on the outcome `"skip"`, for which no edge is
  declared. `implementation`'s chain ends in `verify-tests`, which skips whenever no
  command is bound — so `implementation` parked at `no_edge` and escalated instead of
  advancing. The `implementation → verification` edge this decision introduces would have
  been unreachable.

**A hook that declines to run has said nothing about the node.** The chain now continues
past a `skip` and, if nothing objects, the node passes on the outcome `pass`. Blocking and
waiting are unchanged, and `NodeReport.satisfied` already treated skip as satisfied — this
makes the chain agree with it.

This is also why `verification` re-declares `produces`: `validate-artifacts` returns
*skipped* for a node that declares no artifacts, so a verification node without it would
have been a gate that reports success without ever running.

## Alternatives considered

- **Extend `design.md`'s Testing strategy instead of adding an artifact** — cheapest, no
  new node, no new template. Rejected: the artifact has a second life at `verification`,
  and a file edited after implementation cannot also be a design artifact locked before
  it. The two would drift, and the gate would have nothing to re-read.
- **A `verification-report.md` produced by the verification node** — clean separation of
  plan from result. Rejected as D3: it splits intent from outcome across two files and two
  diffs, and buys a template, a manifest entry and parity coverage for the privilege.
- **Bind a project's test command to `verify-tests` on the verification node** — makes the
  gate literally run the tests. Rejected for now: it re-introduces the-loop as a runner by
  the back door (whose command? which environment? which of eleven testing types?) and the
  hook is left in the chain as the declared seam for a future graph revision or a
  user-authored graph.
- **A `test-plan-approval` human node** — consistent with requirements and design.
  Rejected as D2.
- **Make specific testing types mandatory by risk tier** (e.g. tier ≥ 4 requires
  performance testing) — rejected. It would force work items to run kinds of testing their
  change cannot exercise, and the-loop's existing answer to "prove you considered it" is a
  written justification, not a forced activity.
- **Fold verification into `implementation`** — no new phase, no new label. Rejected: it
  is precisely the conflation issue-109 measured, where six distinct states hid behind one
  `needs-review` label and the drift piled up in the part nobody could see.
