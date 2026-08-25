# What is the-loop?

**the-loop** is an opinionated product-development lifecycle (PDLC), shipped as an
**executable process graph** and a daemon that runs it. Nodes are the steps, hooks are the
checks and side effects at their boundaries, and declared edges route on hook outcomes.
Prose describes a process; here the graph *is* the process.

The `the-loop` CLI turns ticket and pull-request activity into agent sessions and drives
each of them through that graph. Plugins for [Claude Code](https://claude.com/claude-code)
and Cursor are how an agent picks up the operating model — one delivery surface, not the
product. Once a plan is approved, the harness delivers a work item end-to-end with minimal
or no human intervention, escalating only when a decision is genuinely needed.

## Five loops

The PDLC is **five** graphs, all shipped as package data inside the CLI:

- **`pdlc-work-item-loop`** — the **outer** loop: one *work item*, from a fuzzy idea to a
  closed ticket.
- **`pdlc-pr-loop`** — the **inner** loop: one *pull request* delivering that work item,
  running in its own session, through the component-scoped subset. Everything before
  implementation is skipped — those steps are the work item's, decided once at the outer
  level, and a pull request re-deciding them would fork the spec.
- **`pdlc-contribution-loop`** — the **contribution** loop: the-loop invited *into* an
  existing, in-progress issue or PR as a contributor (comment `the-loop contribute`
  instead of `the-loop start`). It cannot begin until an authorized human states a
  **goal and success criteria**; it plans in one lightweight `contribution.md` instead
  of the four-file spec chain; and its verification gate holds until every stated
  criterion is met. Phases are selectable as ever, so a small contained instruction can
  run as little as implementation + verification.
- **`pdlc-adhoc-loop`** — the **ad-hoc** loop, and the smallest of them: a tactical task
  that runs **no PDLC process at all** (comment `the-loop do`). Three nodes —
  `work → review → complete` — with no spec chain, no phase-selection gate, no artifact
  gates and no review chain. The ticket is the instruction, any reply that is not a "we're
  done" is more work, and the item ends when you say so or close it. See the
  [quickstart](/guide/quickstart#ad-hoc-tasks) for the
  exact comment.
- **`pdlc-review-loop`** — the **review** loop: the-loop as a pull request's
  **reviewer**, never its author (comment `the-loop review` on the PR — it binds to the
  PR itself, linked ticket or not — or on the work item, for one review across every PR
  delivering it). It cannot begin until an authorized reviewer states a **brief** —
  questions to answer, angles to examine, validations to run; the-loop posts the
  fill-in template if the arming comment didn't carry one, asking on a work item which
  PRs are in scope with the detected ones pre-filled — then it reviews round after
  round until the reviewer says done, changing **no code** along the way.

The first two meet at exactly **one seam**: the outer `implementation` node waits at
`await-inner-loops` until every inner loop that was started reaches `complete`, after which
verification runs across all the pull requests. A work item delivered by a single session
starts no inner loops and passes that gate vacuously — it behaves exactly as it did before
the split.

![the-loop's two loops. A ticket is opened, then the spec chain — optional
brainstorm.md, requirements.md or bugfix.md, design.md, testing-plan.md, tasks.md — is
iterated with feedback at its human approval gate, which locks each artifact on the human's one approval. Below it the
outer pdlc-work-item-loop runs implementation, verification across all PRs, the review
chain (self, critic and security review, evidence, capability docs, reviewer briefing), a
human approval, then complete and learn. Below that the inner pdlc-pr-loop runs one per
pull request in its own session, column-aligned with the outer loop and starting at
implementation: implementation, verification of this component, self, critic and security
review with the reviewer briefing, the PR's human review, then complete. Two dashed arrows
join them — the outer implementation starts one inner loop per PR, and await-inner-loops
holds the work item there until every inner loop it started reaches
complete](../assets/the-loop-workflow.svg)

*The same diagram the [README](https://github.com/MadaraUchiha-314/the-loop#two-loops)
carries — one drawing, one source. Drawn with [Excalidraw](https://excalidraw.com); both
the SVG (which embeds the scene) and the `.excalidraw` source under `docs/assets/` re-open
on excalidraw.com to edit.*

A work item's position in the outer loop is tracked on the ticket by a `loop:<phase>` label
and mirrored in its execution log:

```text
not-started → brainstorming (optional) → requirements-definition → design
  → test-planning → tasks-breakdown → implementation → verification → needs-review
  → complete
```

Full detail: [the process-graph capability](/capabilities/process-graph).

## The artifact chain

A work item is a chain of documents, each derived from the one before it. An artifact
with a human approval gate is **iterated with the feedback that gate records, and the
gate locks it** (`status: approved`, written with the approver on the human's one
approval) — only then is the next one written and the phase advanced. Artifacts with
no gate (the brainstorm, the task DAG) advance on shape alone, with no human stop. They live under `docs/specs/<id>/`, in the
[Kiro](https://kiro.dev/docs/specs/) spirit:

| Artifact | What it settles |
|----------|-----------------|
| `brainstorm.md` *(optional)* | A free-form scratchpad for a fuzzy idea: problem, options, open questions. A well-defined work item starts at requirements |
| `requirements.md` (or `bugfix.md` for bugs) | User stories and **EARS** acceptance criteria, plus a threat-model-lite **Security considerations** section |
| `design.md` | Architecture, components, data models, error handling, and a **Security design** section enforcing every boundary the requirements raised |
| `testing-plan.md` | **How the work item will be proved**: which kinds of testing apply and which are `n/a` *with a reason*, the verification environment, the evidence to capture, and the activities checklist |
| `tasks.md` | A DAG of small, verifiable tasks; each names the requirement it satisfies and the testing-plan row that proves it |

`testing-plan.md` is worth its own note. It is authored at the `test-planning` node —
*before* the task DAG that references its rows — and reviewed together with the design, so
it gets human review without a stop of its own. It is then **completed** at the
`verification` node: the same file is written once as a plan and once as a record, so
intent and outcome sit in one diff. Evidence is committed under
`docs/specs/<id>/evidence/`; a link to a CI run that expires is not evidence. See the
[testing reference](/operating-model/reference/testing).

## Rules the loop enforces

- Every work item has a ticket. Its spec chain is **reviewed and approved per phase before
  execution**.
- Collaborators are identified up-front; not every task needs every persona.
- Every human decision leaves a **paper trail** on the ticket or pull request.
- Self-checks run tests at logical checkpoints; progress is logged for visibility.
- Configured self-reviews and critic reviews run **before** escalating to a human, and a
  work item may **opt in** to one more: a critic reading the completed `design.md` before
  the testing plan and the task DAG are derived from it, so a structural finding costs
  an edit rather than a rewrite. Off unless it is ticked at `phase-selection`.
- **Testing is planned, then executed**: `test-planning` decides which kinds of testing
  apply and records `n/a` *with a reason* for the rest; `verification` runs the plan and
  ticks an activity only once it has actually run.
- **Security is gated, not bolted on**: a threat-model-lite in the requirements, enforcing
  mechanisms in the design, and a security review that is its own node with its own gate —
  never something an agent can quietly declare unnecessary. (Since issue-179 an
  *authorized human* may select it away up front, on the record, along with any other
  phase; the one thing no one can skip is being asked.)
- The same tooling runs locally and in CI; logging is identical at dev-time and runtime.
- Integration tests document their scenario in **Gherkin** docstrings, queryable as a table
  via `the-loop scenarios`.
- APIs are **contract-first**: REST specs in OpenAPI, GraphQL SDL; docs are generated from
  the contracts, never hand-written.
- **Capability docs are the organized view of specs**: per-work-item specs are the
  historical record; living docs under [`developer/capabilities`](/capabilities/capabilities)
  are the single source of truth for each capability's *current* behaviour, updated in the
  same pull request as the work item.
- **The user-facing docs ship with the change too**: the README, this site and the
  operating-model skill are updated in the same pull request as the change that made them
  wrong, recorded in the execution log's `## Documentation` section — which the
  `capability-docs` node gates.
- **UI/UX design is a first-class artifact**: for user-facing work the design phase tracks
  Figma links and/or self-contained HTML+CSS+JS prototypes, iterated with the designer
  on the rendered output until the designer signs off.
- All commits follow **Conventional Commits**.
- Pull requests are written **for the reviewer**: a condensed, prioritized summary,
  **mermaid** diagrams, and documented low-level decisions — and the loop educates the user
  on those decisions (mandatory, not optional).

Next: [install the-loop](/guide/installation) or jump straight to the
[quickstart](/guide/quickstart).
