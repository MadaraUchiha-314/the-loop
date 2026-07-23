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
> - `reference/context.md` — context-window management: clearing vs compaction, the checkpoint-then-reset protocol, per-harness mechanics.
> - `reference/onboarding.md` — the guided, schema-driven config onboarding `/init` runs (groups, ask levels, sensible-defaults precedence).
> - `reference/instructions.md` — user-provided custom instruction docs (`customInstructions`): when to read them, precedence, what they can and cannot override.
> - `reference/design-artifacts.md` — UI/UX design artifacts (Figma / HTML prototypes) in the design phase and the designer iteration loop.
> - `reference/reviewing.md` — the self/critic review procedure the review counts drive.
> - `reference/security.md` — the security lens on every phase gate: threat-model-lite, security design, the security-review gate, human sign-off tiers.
> - `reference/tooling.md` — repo management, per-language tooling matrix, hooks, CI parity.
> - `reference/testing.md` — Gherkin scenario docstrings on integration tests, the queryable scenario view, OpenAPI/GraphQL contract conventions.
> - `reference/minimalism.md` — generation-time decision ladder to counter code bloat.
> - `reference/token-economy.md` — token/cost levers (model routing, verbosity, disclosure, sub-agents, telemetry); advisory, never at the expense of rigor.
> - `reference/collaboration.md` — personas/roles, paper trail, conflict log, messaging, MCP.
> - `reference/observability.md` — dev==runtime logging, levels, browser logging.
> - `reference/automation.md` — distribution, the CLI, webhooks, predictability, learnings lifecycle.

## The artifact chain (optional brainstorm → 3-phase spec, Kiro-style)

Every work item is a chain of artifacts, each **derived from and iterated after** the one
before it. The rule holds at every link: an artifact is refined with human feedback until
it is **locked** (`status: approved`), and only then is the next one derived. Specs live in
`docs/specs/<id>/`:

0. **`brainstorm.md`** *(optional, the root artifact)* — a free-form scratchpad to explore
   a fuzzy idea before committing to requirements: problem, options, open questions,
   working hypothesis. Created by `/the-loop:brainstorm`; converted to requirements once
   locked. Phase: `brainstorming`. Skip it when the work is already clear.
1. **`requirements.md`** (or **`bugfix.md`** for bugs) — user stories + EARS acceptance
   criteria (`WHEN <event> THEN the system SHALL <response>`). Phase: `requirements-definition`.
2. **`design.md`** — architecture, components/interfaces, data models, error handling,
   testing strategy. Phase: `design`. For a **user-facing** work item the design phase also
   tracks **UI/UX design artifacts** (Figma links / self-contained HTML prototypes under
   `docs/specs/<id>/design/`), iterated-until-locked with the designer
   (`reference/design-artifacts.md`).
3. **`tasks.md`** — a **DAG** of small, verifiable tasks referencing requirements.
   Phase: `tasks-breakdown`.

The work item's **phase** is tracked on the ticket via a label
(`<workflow.phaseLabelPrefix><phase>`) and mirrored in the execution log (`brainstorming`
is optional):

```
not-started → brainstorming → requirements-definition → design → tasks-breakdown
            → implementation → needs-review → complete
```

See `reference/workflow.md` for what each phase contains, the review gates, the
self/critic-review counts, evidence, resumability and DAG orchestration.

## Operating principles (rules)

- **Every work item has a ticket.** Nothing the harness works on lacks a GH issue (or
  Jira) ticket.
- **Spec before execution.** Create the 3-phase spec and get each phase
  reviewed/approved by the required collaborators before writing code.
- **Iterate each artifact until locked, then advance.** Starting from the optional
  `brainstorm.md` root, every artifact is refined with human feedback until it is **locked**
  (`status: approved`); only then is the next artifact derived and the phase advanced.
  Never write a downstream artifact against an unlocked upstream one. Brainstorming is
  optional — a well-defined work item starts at requirements.
- **Human review per phase** (`workflow.requireHumanReviewPerPhase`, default true).
- **Reference, don't duplicate (single source of truth).** Once requirements/design/
  tasks exist, update the ticket with a **link** to each checked-in artifact. Subsequent
  changes are **edits to those files, not new comments**.
- **Capability docs are the organized view of specs.** Raw specs under
  `docs/specs/<id>/` are the per-work-item record (*deltas*); living capability docs
  under `workflow.capabilitiesDir` (default `docs/capabilities/`, indexed by
  `capabilities.md`) are the **single source of truth for a capability's *current*
  behaviour** (*state*), each behaviour traced by a history row to the specs/decisions
  that produced it. Update the affected capability docs **in the same PR** as the work
  item — a ready-to-ship gate item. Mint docs emergently (product-feature and
  architecture shaped both valid) and evolve the taxonomy through PR-review feedback.
  See `reference/workflow.md`.
- **Keep `tasks.md` checkmarks current** as tasks complete (`- [ ]` → `- [x]`).
- **Identify collaborators up-front.** Each work item names the personas it needs; not
  every task needs every persona (a bug fix needs the engineer; a content fix may not).
  More can be added later. See `reference/collaboration.md`.
- **Paper trail.** Every human decision/opinion is captured on the ticket or PR.
  Planning questions → ticket comments. PR & all reviews → PR/ticket comments.
  Notify via configured messaging channels when a human action is pending.
- **Self-check continuously.** Maintain `docs/specs/<id>/execution-log.md`; keep the
  phase label in sync; run tests at logical checkpoints; log progress for visibility.
- **Manage the context window deliberately (checkpoint, then reset).** Never reset
  context without first checkpointing (checkmarks, execution-log entry with a concrete
  next step, phase label, WIP committed/noted). Then: **clear** at phase boundaries
  (locked spec → fresh window for implementation, plan-mode style), **compact** after
  each completed task and mid-task (never clear mid-task), and isolate high-volume
  exploration in subagents. The checked-in artifacts are the memory that makes resets
  affordable (`contextManagement`). See `reference/context.md`.
- **Review before escalating.** Run `reviews.selfReviewCount` self-reviews then
  `reviews.criticReviewCount` critic reviews (a different harness/model), default 3
  each, BEFORE reaching out to a human. All reviews are comments. **Follow the defined
  procedure** in `reference/reviewing.md` (attribution prefix, reply-first-then-fix,
  stop on zero new findings, escalate on a repeated finding).
- **Security is gated, not bolted on** (`config.security`). Every phase gate also asks
  the security question: requirements carry a **Security considerations**
  threat-model-lite (untrusted actors, trust boundaries, abuse cases, fail-closed);
  design carries a **Security design** section enforcing those boundaries; the
  ready-to-ship gate includes a **security review** (built-in security-review skill or
  the-loop's checklist), with a named human sign-off at risk tier ≥
  `security.review.humanSignOffMinTier`. "No new attack surface" is written and
  justified, never implied. See `reference/security.md`.
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
- **UI/UX design is a first-class artifact.** For user-facing work, `design.md` (markdown +
  mermaid) is not enough — the **visual** design is tracked as artifacts under
  `docs/specs/<id>/design/` (`design.uiArtifacts`): Figma links and/or self-contained
  HTML+CSS+JS prototypes (Claude-artifact style). They are iterated-until-locked with the
  **designer** on the *rendered* output, referenced from the ticket, and become the visual
  contract implementation matches. Backend/CLI/infra work produces none. See
  `reference/design-artifacts.md`.
- **Minimalism.** Apply the `reference/minimalism.md` decision ladder (YAGNI → stdlib →
  native → existing dep → inline → new abstraction); justify every new dependency in
  `design.md`. Never trade away validation/error-handling/security/accessibility.
- **Token economy.** Apply the `reference/token-economy.md` levers (`config.tokenEconomy`):
  progressive/phase-scoped disclosure, dense prompts, model routing + thinking-effort by
  stage/risk tier, narration-only output compression (with its preservation list),
  sub-agent delegation for verbose work, compaction/filesystem-memory, and per-work-item
  token telemetry. **Advisory, never a gate** — cheaper never means sloppier; the rigor
  floor (validation/security/tests/paper-trail/review depth) is untouchable.
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
  post/update the **reviewer briefing** in the PR — produced from the-loop's internal
  `${CLAUDE_PLUGIN_ROOT}/skills/the-loop/templates/pr-briefing.md`: a **condensed,
  prioritized** summary (where to
  focus first), the spec→implementation insights and low-level decisions, and **mermaid**
  diagrams. This is a required item of the ready-to-ship gate
  (`userInteraction.prSummary.required`), so **mandatory user-education is triggered, not
  optional** — you cannot request review without it. See `reference/collaboration.md`.
- **Honor the user's custom instructions.** Read every doc registered in
  `customInstructions.docs` (in order) when starting work on an item, and follow it —
  these are the operator's conventions (developing/testing/coding styles, house rules)
  that the structured config does not model. The structured config wins where both
  speak, and no instruction doc can weaken the loop's gates (security, paper trail,
  reviews); a missing doc is handled per `customInstructions.onMissing`. See
  `reference/instructions.md`.
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
`tooling`, `customInstructions`, `testing`, `apiSpecs`, `localOrchestration`, `hooks`, `observability`,
`reviews`, `autonomy`, `security`, `tdd`,
`minimalism`, `selfImprovement`, `contextManagement`, `userInteraction`, `personas`,
`messaging`, `externalTools`, `webhooks`. A subset of keys can be overridden per work item via the
YAML front-matter `overrides` of the work-item / spec markdown. Managed files are listed
in `.the-loop/manifest.yaml`.

## Commands

- `/the-loop:init` — scaffold the-loop into a repo (config, docs, templates, phase labels).
- `/the-loop:work-on <ticket>` — run the whole loop on a work item (resumable per phase).
  **Superset** of the granular commands below.
- `/the-loop:upgrade-the-loop` — reconcile project files with the installed plugin version.

Granular commands (one step at a time; same flow `work-on` runs end-to-end):

- `/the-loop:brainstorm <title>` — *(optional Phase 0)* draft a free-form `brainstorm.md`
  scratchpad (the root artifact) in `docs/specs/draft-<slug>/` for a fuzzy idea; iterate,
  then convert to requirements.
- `/the-loop:new-requirement <title>` — draft `requirements.md` in a temporary
  `docs/specs/draft-<slug>/` folder **before a ticket exists** (converts a sibling
  `brainstorm.md` if one is present).
- `/the-loop:create-ticket <path>` — create the ticket from a `requirements.md` and
  promote `draft-<slug>/` → `docs/specs/<id>/`.
- `/the-loop:create-design <id>` — `requirements.md` → `design.md` (Phase 2).
- `/the-loop:create-tasks-plan <id>` — requirements + design → `tasks.md` DAG (Phase 3).
- `/the-loop:execute-tasks <id>` — implement the DAG, self-check, self/critic-review.
- `/the-loop:finish-tasks <id>` — cleanup after all tasks (close the ticket; extensible).
- `/the-loop:work-status <id>` — read-only status from the specs, tasks checkmarks and log.

## Knowledge the loop maintains

- `docs/specs/<id>/brainstorm.md` — *(optional)* the root scratchpad a work item was
  explored in before requirements.
- `docs/architecture/architecture.md` — architecture index → sub-component docs.
- `docs/capabilities/capabilities.md` + `<capability>.md` — living capability docs:
  the organized view of specs; current behaviour per capability with history links.
- `docs/decisions/decisions.md` + `decision-<nnn>.md` — decision log (every durable
  decision is recorded).
- `docs/specs/<id>/` — the per-work-item 3-phase spec + execution log.
- `learnings/learnings.md` + `learning-<nnn>.md` — learnings from user & system
  feedback, checked in for review. See `reference/automation.md`.

## Interacting with other tools

the-loop may freely use the MCP servers, CLIs, skills and plugins registered in
`config.externalTools` (the `externalTools.tools` list + `notes` in
`.the-loop/config.yaml`). Check that registry before assuming a capability is available.

## Custom instructions the loop honors

Supplementary to the external-tools registry, `config.customInstructions` registers
**guidance** rather than tools: user-provided readme/markdown docs (per installation,
configurable paths) the harness reads at the start of working an item and follows —
conventions and styles the structured config does not model. Precedence and limits:
`reference/instructions.md`.
