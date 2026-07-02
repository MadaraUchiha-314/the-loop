---
name: the-loop
description: The operating model for delivering product work items end-to-end with an agent harness. Use whenever working a ticket/issue under the-loop — to write the 3-phase spec (requirements/design/tasks), execute the task DAG, self/critic-review, escalate, present evidence, and record decisions and learnings under the project's PDLC rules and tooling.
---

# the-loop

"the-loop" is an opinionated product-development-lifecycle (PDLC) harness, shipped as a
plugin for Claude Code and Cursor. Once a work item's 3-phase spec (requirements →
design → tasks) is approved, the harness executes it end-to-end with MINIMAL or NO human
intervention, escalating only when a decision/opinion is genuinely required.

> **Read the relevant reference file before acting** — they carry the full detail so the
> essence is not lost:
> - `reference/workflow.md` — the loop, phases, TDD, reviews, autonomy, DAG, resumability.
> - `reference/reviewing.md` — the self/critic review procedure the review counts drive.
> - `reference/tooling.md` — repo management, per-language tooling matrix, hooks, CI parity.
> - `reference/testing.md` — Gherkin scenario docstrings on integration tests, the queryable scenario view, OpenAPI/GraphQL contract conventions.
> - `reference/minimalism.md` — generation-time decision ladder to counter code bloat.
> - `reference/collaboration.md` — personas/roles, paper trail, conflict log, messaging, MCP.
> - `reference/observability.md` — dev==runtime logging, levels, browser logging.
> - `reference/automation.md` — distribution, the CLI, webhooks, predictability, learnings lifecycle.

## The 3-phase spec workflow (Kiro-style)

Every non-trivial work item is specified in three phases, each gated by a **human
review** (https://kiro.dev/docs/specs/). Specs live in `docs/specs/<id>/`:

1. **`requirements.md`** (or **`bugfix.md`** for bugs) — user stories + EARS acceptance
   criteria (`WHEN <event> THEN the system SHALL <response>`). Phase: `requirements-definition`.
2. **`design.md`** — architecture, components/interfaces, data models, error handling,
   testing strategy. Phase: `design`.
3. **`tasks.md`** — a **DAG** of small, verifiable tasks referencing requirements.
   Phase: `tasks-breakdown`.

The work item's **phase** is tracked on the ticket via a label
(`<workflow.phaseLabelPrefix><phase>`) and mirrored in the execution log:

```
not-started → requirements-definition → design → tasks-breakdown
            → implementation → needs-review → complete
```

See `reference/workflow.md` for what each phase contains, the review gates, the
self/critic-review counts, evidence, resumability and DAG orchestration.

## Operating principles (rules)

- **Every work item has a ticket.** Nothing the harness works on lacks a GH issue (or
  Jira) ticket.
- **Spec before execution.** Create the 3-phase spec and get each phase
  reviewed/approved by the required collaborators before writing code.
- **Human review per phase** (`workflow.requireHumanReviewPerPhase`, default true).
- **Reference, don't duplicate (single source of truth).** Once requirements/design/
  tasks exist, update the ticket with a **link** to each checked-in artifact. Subsequent
  changes are **edits to those files, not new comments**.
- **Keep `tasks.md` checkmarks current** as tasks complete (`- [ ]` → `- [x]`).
- **Identify collaborators up-front.** Each work item names the personas it needs; not
  every task needs every persona (a bug fix needs the engineer; a content fix may not).
  More can be added later. See `reference/collaboration.md`.
- **Paper trail.** Every human decision/opinion is captured on the ticket or PR.
  Planning questions → ticket comments. PR & all reviews → PR/ticket comments.
  Notify via configured messaging channels when a human action is pending.
- **Self-check continuously.** Maintain `docs/specs/<id>/execution-log.md`; keep the
  phase label in sync; run tests at logical checkpoints; log progress for visibility.
- **Review before escalating.** Run `reviews.selfReviewCount` self-reviews then
  `reviews.criticReviewCount` critic reviews (a different harness/model), default 3
  each, BEFORE reaching out to a human. All reviews are comments. **Follow the defined
  procedure** in `reference/reviewing.md` (attribution prefix, reply-first-then-fix,
  stop on zero new findings, escalate on a repeated finding).
- **Test-first.** `tdd.mode` (default `standard`): no production code without a failing
  test that motivates it; record the red→green transition as evidence.
- **Scenario-documented integration tests.** Every integration test carries a
  Gherkin-syntax docstring (`Feature:`/`Scenario:`/Given-When-Then) naming the scenario
  under test, with a `Requirement:` link when tied to a `requirements.md`
  (`config.testing`). The harness can query all covered scenarios as a table via
  `the-loop scenarios` (`--format table|markdown|json`). See `reference/testing.md`.
- **Contract-first APIs.** RESTful API specs are authored in `specs/openapi/` in the
  OpenAPI format; GraphQL schemas are SDL-first under `specs/graphql/`; documentation is
  generated from those contracts, never hand-written (`config.apiSpecs`). See
  `reference/testing.md`.
- **Minimalism.** Apply the `reference/minimalism.md` decision ladder (YAGNI → stdlib →
  native → existing dep → inline → new abstraction); justify every new dependency in
  `design.md`. Never trade away validation/error-handling/security/accessibility.
- **Risk-tiered autonomy.** Gate completion by the work item's risk tier
  (`config.autonomy`): low tiers may complete after the review loop; high tiers wait for
  a human. Only complete autonomously once the **ready-to-ship gate** holds (green
  checks, all threads resolved, evidence recorded).
- **Keep moving; log conflicts.** Resolvable ambiguity → assume a reasonable default and
  continue; genuine block → log to `docs/decisions/conflicts.md`, escalate once, move on.
- **Learnings lifecycle.** Capture → write-gate (rule-of-three) → consolidate (size cap)
  → inject a capped index (`config.selfImprovement`). See `reference/automation.md`.
- **Evidence at the end.** Present validated evidence that acceptance criteria are met.
- **Communicate for the reviewer (required gate).** Before requesting human review,
  post/update the **reviewer briefing** in the PR — produced from
  `.the-loop/templates/pr-briefing.md`: a **condensed, prioritized** summary (where to
  focus first), the spec→implementation insights and low-level decisions, and **mermaid**
  diagrams. This is a required item of the ready-to-ship gate
  (`userInteraction.prSummary.required`), so **mandatory user-education is triggered, not
  optional** — you cannot request review without it. See `reference/collaboration.md`.
- **Use the configured tooling.** Package managers, test runners, linters, type checkers
  and release tooling come from `.the-loop/config.yaml`; run scripts from the project
  root; lint ALL files including markdown. See `reference/tooling.md`.
- **Same tooling everywhere.** Pre-commit/pre-push hooks and CI run the SAME commands —
  no last-minute build surprises.
- **Conventional Commits.** All commits follow Conventional Commits v1.0.0
  (`<type>[scope][!]: <desc>`), enforced by a commit-msg hook running **commitizen**
  (`cz check`, not custom code) — `hooks.commitConvention`. See `reference/tooling.md`.
- **Identical observability.** Logging is the same at dev-time and runtime; the only dev
  advantage is breakpoints. See `reference/observability.md`.

## Configuration

Behaviour is driven by `.the-loop/config.yaml`, validated against
`.the-loop/config.schema.json`. Sections: `ticketing`, `repository`, `workflow`,
`tooling`, `testing`, `apiSpecs`, `localOrchestration`, `hooks`, `observability`,
`reviews`, `autonomy`, `tdd`,
`minimalism`, `selfImprovement`, `userInteraction`, `personas`, `messaging`,
`externalTools`, `webhooks`. A subset of keys can be overridden per work item via the
YAML front-matter `overrides` of the work-item / spec markdown. Managed files are listed
in `.the-loop/manifest.yaml`.

## Commands

- `/the-loop:init` — scaffold the-loop into a repo (config, docs, templates, phase labels).
- `/the-loop:work-on <ticket>` — run the whole loop on a work item (resumable per phase).
  **Superset** of the granular commands below.
- `/the-loop:upgrade-the-loop` — reconcile project files with the installed plugin version.

Granular commands (one step at a time; same flow `work-on` runs end-to-end):

- `/the-loop:new-requirement <title>` — draft `requirements.md` in a temporary
  `docs/specs/draft-<slug>/` folder **before a ticket exists**.
- `/the-loop:create-ticket <path>` — create the ticket from a `requirements.md` and
  promote `draft-<slug>/` → `docs/specs/<id>/`.
- `/the-loop:create-design <id>` — `requirements.md` → `design.md` (Phase 2).
- `/the-loop:create-tasks-plan <id>` — requirements + design → `tasks.md` DAG (Phase 3).
- `/the-loop:execute-tasks <id>` — implement the DAG, self-check, self/critic-review.
- `/the-loop:finish-tasks <id>` — cleanup after all tasks (close the ticket; extensible).
- `/the-loop:work-status <id>` — read-only status from the specs, tasks checkmarks and log.

## Knowledge the loop maintains

- `docs/architecture/architecture.md` — architecture index → sub-component docs.
- `docs/decisions/decisions.md` + `decision-<nnn>.md` — decision log (every durable
  decision is recorded).
- `docs/specs/<id>/` — the per-work-item 3-phase spec + execution log.
- `learnings/learnings.md` + `learning-<nnn>.md` — learnings from user & system
  feedback, checked in for review. See `reference/automation.md`.

## Interacting with other tools

the-loop may freely use the MCP servers, CLIs, skills and plugins registered in
`.the-loop/external-tools.md` (or `externalTools.notes`). Check that registry before
assuming a capability is available.
