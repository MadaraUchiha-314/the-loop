# Report: work-item status labels & how they feed a dashboard

> Requested in [issue #73](https://github.com/MadaraUchiha-314/the-loop/issues/73):
> *the-loop already defines labels but I don't see them being used on issues/PRs; how
> does this integrate with a GitHub Projects kanban view, and do I need to build a
> separate dashboard or can I use GitHub's inherent features?* Audited at the current
> `main` (post-v0.13.0). This is a point-in-time report, not a living capability doc.

## TL;DR

- the-loop already defines **two independent label families** — the per-phase
  **loop labels** (`loop:not-started` … `loop:complete`) and the CLI's
  **auto-execute label** (`the-loop: auto-execute`). They are real labels in this repo,
  created by `/the-loop:init`, but they are **not applied to any issue or PR today**, and
  they carry no colour or description, so they are invisible on a board.
- Phase labels answer *where in the loop* an item is. The "what needs my input / what's
  blocked" bucket the issue asks for is **already `loop:needs-review`** — the phase where
  automated reviews are done and the item is waiting on a human. No new label is needed;
  "blocked" collapses into the same "waiting on a human" meaning
  ([PR #75 discussion](https://github.com/MadaraUchiha-314/the-loop/pull/75)).
- **You do not need to build a separate dashboard.** GitHub's native features cover the
  ask completely: saved **label filters** for a zero-setup view, and a **GitHub Project
  (v2)** board when you want a kanban with columns, insights and automation. A bespoke
  dashboard would only earn its keep well beyond a single-operator, single-repo setup.

## Scope and method

Audit of every label the-loop *defines* and *touches*, and how those labels can drive a
status dashboard. Method: repo-wide search for label definitions and label writes across
`.the-loop/`, `skills/`, `commands/`, `cli/`, plus a live check of the labels and their
usage on `MadaraUchiha-314/the-loop` via the GitHub API.

## The labels the-loop defines today

### 1. Phase labels — `loop:<phase>`

The workflow's phase state machine. One label per `workflow.phases`, prefixed with
`workflow.phaseLabelPrefix` (default `loop:`), created by `/the-loop:init`
([`commands/init.md`](../../commands/init.md) step 4) and kept in sync by the workflow
commands as an item advances:

```text
not-started → brainstorming → requirements-definition → design → tasks-breakdown
            → implementation → needs-review → complete
```

| Label | Set by | Means |
|---|---|---|
| `loop:not-started` | `init` (default) | Ticket exists, loop hasn't begun. |
| `loop:brainstorming` | `/the-loop:brainstorm` | Optional Phase 0 — free-form `brainstorm.md`. |
| `loop:requirements-definition` | `/the-loop:create-ticket` | Requirements being iterated/locked. |
| `loop:design` | `/the-loop:create-design` | Design being iterated/locked. |
| `loop:tasks-breakdown` | `/the-loop:create-tasks-plan` | Task DAG being built. |
| `loop:implementation` | `/the-loop:execute-tasks` | Tasks being executed. |
| `loop:needs-review` | `/the-loop:execute-tasks` | Self/critic review + human review pending. |
| `loop:complete` | `/the-loop:finish-tasks` | Shipped; ticket closed. |

The label is the *ticket-visible* mirror of the phase that also lives in each work item's
`docs/specs/<id>/execution-log.md` front-matter — single source of truth is the spec, the
label is the at-a-glance projection (SKILL.md "Reference, don't duplicate").

### 2. The auto-execute label — `the-loop: auto-execute`

A different axis entirely: the CLI's **routing gate**
(`routing.autoExecuteLabel`, [`reference/automation.md`](../../skills/the-loop/reference/automation.md)).
Applying it to an issue/PR opts that item into autonomous execution — the poller/webhook
receiver spawns a session that runs `/the-loop:work-on` and routes the item's later
activity back to that session. It is a *control* label, not a *status* label, and is
deliberately outside the `loop:` namespace.

## Current state: defined, but unused

Verified live against this repo:

- Every `loop:<phase>` label and `the-loop: auto-execute` **exists** as a repository
  label (so `init` did its job).
- **Zero** open or closed issues/PRs carry any of them — e.g. `label:loop:complete` and
  `label:"the-loop: auto-execute"` both return 0 results.
- The labels were created with GitHub's default grey (`ededed`) and **empty
  descriptions**, so even once applied they read as undifferentiated dots on a board.

This matches the issue's observation exactly. Two things close the gap: (a) giving the
labels colour + description so they're legible, and (b) actually applying them — which is
what the workflow commands do the moment a real item is driven through `/the-loop:work-on`
rather than merged as a plain PR (as most work in this repo has been so far).

## The four buckets map onto the phases as-is

The issue asks for four buckets — *being worked on*, *needs the user's input*,
*completed*, *blocked*. All four are already answered by the phase labels; no new label is
needed:

| Bucket the issue asks for | Answered by |
|---|---|
| What's being worked on | any of `loop:requirements-definition` … `loop:implementation` |
| What needs the user's input | `loop:needs-review` |
| What's blocked | `loop:needs-review` — see below |
| What's completed | `loop:complete` |

**"Needs input" and "blocked" are the same thing: the item is waiting on a human.**
`loop:needs-review` already carries that meaning — it is the phase where the harness has
finished its self/critic reviews and can't advance without a person (a review, an approval,
an answer). A separate `loop:blocked` label would only restate it, so it is deliberately
**not** added ([PR #75 discussion](https://github.com/MadaraUchiha-314/the-loop/pull/75)).

The one thing `loop:needs-review` does *not* capture is a human question raised *before* the
review gate — e.g. a clarification needed mid-`design`. the-loop already handles that
without a label: the harness posts the question as a **ticket comment and notifies** via the
configured messaging channel (the paper-trail + escalation rules in
[`reference/reviewing.md`](../../skills/the-loop/reference/reviewing.md)). That is a
transient conversation, not a durable status — so it stays a comment, not a phase. If a
durable "waiting on a human at any phase" signal is ever wanted, the right shape is an
**orthogonal flag** that coexists with the phase (a phase can't sit mid-`design`), added
through the normal spec flow — but YAGNI until a real board proves the gap.

## Recommended label set (colours + descriptions)

Legible labels are what make a board readable. Colour by role — a hue ramp for the phase
progression (the `loop:needs-review` gate flagged in alert-yellow since it's the
"waiting on you" bucket), and a neutral for the control label:

```bash
# Phase labels — cool ramp, not-started → complete
gh label create "loop:not-started"             -c ededed -d "the-loop: ticket exists, loop not started"        -f
gh label create "loop:brainstorming"           -c c5def5 -d "the-loop: Phase 0 — brainstorm.md"               -f
gh label create "loop:requirements-definition" -c bfdadc -d "the-loop: requirements being locked"             -f
gh label create "loop:design"                  -c 5319e7 -d "the-loop: design being locked"                    -f
gh label create "loop:tasks-breakdown"         -c 1d76db -d "the-loop: task DAG being built"                   -f
gh label create "loop:implementation"          -c 0e8a16 -d "the-loop: tasks being executed"                   -f
gh label create "loop:needs-review"            -c fbca04 -d "the-loop: waiting on a human (review/approval/answer)" -f
gh label create "loop:complete"                -c 0e4429 -d "the-loop: shipped and closed"                      -f

# Control label — CLI auto-execution gate
gh label create "the-loop: auto-execute"       -c 5319e7 -d "the-loop: opt this item into autonomous execution" -f
```

`-f` upserts, so this is safe to re-run over the already-created (grey) labels. The same
colours/descriptions should be baked into `/the-loop:init`'s label-creation step so new
projects get legible labels from day one.

## GitHub Projects (kanban) integration

Yes — this maps cleanly onto **GitHub Projects (v2)**, and the phase labels are exactly
the field a board wants. There are two levels, pick by appetite:

### Level 0 — labels only, no project (zero setup)

The phase labels *are* a dashboard on their own. Saved searches give you each bucket:

```text
is:open  label:loop:implementation                 # what's being worked on
is:open  label:loop:needs-review                   # what needs the user's input / is blocked
is:issue label:loop:complete                        # what's done
```

Pin these as the repo's saved views (Issues → *Save*). No project, no automation, and it
answers the issue's four questions immediately.

### Level 1 — a Projects board (the kanban)

Add a Project when you want columns, cross-repo rollup, and Insights charts.

- **Board columns need a single-select field.** In Projects v2 a board's columns are
  driven by one single-select field (the built-in **Status**, or a custom one). **Labels
  are multi-valued and cannot be the column field**, so a label-per-column board isn't a
  drag-and-drop default. Two ways to get the kanban:
  - **Table view, grouped by Labels** — Layout → Table → *Group by → Labels*. Instant
    swimlanes keyed on `loop:*` with zero automation. Best if you want the label to stay
    the single source of truth.
  - **A `Status` single-select whose options mirror the phases** (`Not started`,
    `Requirements`, `Design`, `Tasks`, `Implementation`, `Needs review`, `Complete`) for a
    real drag-and-drop board. Keep it in sync with the phase label via the Action below.
- **Built-in workflows do most of the wiring** (Project → *Workflows*):
  - **Auto-add to project** — filter on a label (e.g. `the-loop: auto-execute`, or any
    `loop:*`) so labelled items land on the board automatically.
  - **Item closed / Pull request merged → set Status = Complete.**
  - **Item reopened → set Status.**
- **Label → Status is not a built-in**, so if you go the Status-field route, mirror the
  phase label onto the field with a tiny Action (the harness keeps the *label* current;
  this just projects it onto the board field):

  ```yaml
  # .github/workflows/loop-project-sync.yml
  name: loop project sync
  on:
    issues:
      types: [labeled, unlabeled]
  jobs:
    sync:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/github-script@v7
          with:
            script: |
              // map the loop:<phase> label on this issue to the project's Status
              // single-select via the Projects v2 GraphQL API (updateProjectV2ItemFieldValue).
              // Left as a stub: fill in PROJECT_ID + STATUS_FIELD_ID for your board.
  ```

  If you'd rather not run an Action, stay in **Table-view-grouped-by-Labels** (Level 1a) —
  the label remains the only source of truth and there's nothing to keep in sync.

## Do I need to build a separate dashboard?

**No.** For a single operator and one repo, GitHub's inherent features are enough and
strictly better than a bespoke tool (no infra, no auth, no drift):

- **Saved label searches** (Level 0) answer *being worked on / needs input / blocked /
  done* today.
- **A Projects board** (Level 1) adds the kanban, cross-repo rollup, and **Insights**
  (built-in burn-up / status-over-time charts) — the reporting a custom dashboard would
  reinvent.
- The-loop's own CLI already provides the *operational* view (which sessions are live);
  the labels + Project cover the *status* view. There's no third thing to build.

You'd only outgrow this at: many repos with a shared board and heavy per-phase SLAs,
metrics GitHub Insights can't express (e.g. time-in-phase distributions), or a
non-GitHub audience that needs an embedded read-only view. None apply at v0. If that day
comes, the labels defined here are already the clean data source to build it on — the
dashboard question is answered by *applying* the taxonomy, not by writing new software.

## Pointers

- Phase labels & prefix: `workflow.phases` / `workflow.phaseLabelPrefix` in
  [`.the-loop/config.yaml`](../../.the-loop/config.yaml),
  [`.the-loop/config.schema.json`](../../.the-loop/config.schema.json)
- Label creation: [`commands/init.md`](../../commands/init.md) step 4
- Phase sync per command: [`commands/`](../../commands/) (`create-ticket`, `create-design`,
  `create-tasks-plan`, `execute-tasks`, `finish-tasks`, `work-on`)
- Auto-execute (control) label: [`reference/automation.md`](../../skills/the-loop/reference/automation.md)
- Related read-query report: [GitHub queries](./gh-queries.md)
