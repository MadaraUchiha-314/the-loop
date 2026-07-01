---
type: requirements
phase: requirements-definition
workItem: issue-1
status: approved
approvedBy: ["@MadaraUchiha-314 (issue author intent)"]
collaborators: [product-manager, architect, engineer]
overrides: {}
---

# Requirements: the-loop (create itself)

> **Source of truth:** GitHub [issue #1](https://github.com/MadaraUchiha-314/the-loop/issues/1)
> is the canonical requirements input for this work item. This file distills it into
> reviewable, testable requirements following the Kiro spec model. Where the issue is a
> forward-looking vision, requirements are marked **[v0]** (delivered now) or
> **[deferred]** (planned — see `decision-003`). Design and the task DAG live in
> `design.md` and `tasks.md`.

## Introduction

the-loop is an opinionated product-development-lifecycle (PDLC) harness, shipped as a
Claude plugin, that lets an agent harness deliver a work item end-to-end with minimal/no
human intervention. The first work item is for the-loop to create itself.

## Requirements

### R1 — Work-item ticketing **[v0]**

**User story:** As a maintainer, I want every worked item to have a ticket, so that work
is traceable.
1. WHEN a project is configured THEN the-loop SHALL support `github` (Issues/Projects)
   or `jira` as the ticketing system.
2. The harness SHALL refuse to work an item that has no ticket.
3. The-loop SHALL provide fill-in templates for **Epics**, **Stories** and **Bugs**.

### R2 — Tooling contract **[v0 config; integrations deferred]**

**User story:** As the harness, I want declared, validated tooling, so that I can do
maximum work and validate against acceptance criteria.
1. The config SHALL declare, per language, the package manager, unit + integration test
   runners, linter, type checker, and release target (python/js/ts; go as proposed
   defaults). _Defaults:_ uv, bun, pytest, vitest, playwright, ruff, oxlint, pyright,
   tsc, npm, pypi, ghcr.
2. The-loop SHALL support monorepo (default Nx; pnpm/yarn/bun) **and** non-monorepo
   layouts; scripts run from the project root.
3. Linting SHALL cover ALL files, including markdown.
4. Multi-entity testing SHALL support locally-linkable packages, services via `podman`,
   and per-service local-vs-remote selection.
5. Pre-commit/pre-push hooks SHALL run lint/typecheck/unit-test, and CI SHALL run the
   SAME tooling (no environment drift).

### R3 — Observability **[v0 config; integrations deferred]**

1. Logging SHALL be identical at dev-time and runtime; the only dev advantage is
   breakpoints.
2. Levels SHALL be configurable (dev: debug+, runtime: info+).
3. Browser logs SHALL be observable by the harness (default mechanism:
   chrome-devtools MCP).

### R4 — The loop: 3-phase spec workflow **[v0 process; automation deferred]**

**User story:** As a collaborator, I want phased, reviewable specs, so that I approve
requirements, design and tasks before implementation.
1. Each work item SHALL be specified as `requirements.md` (or `bugfix.md`) → `design.md`
   → `tasks.md` (a DAG), stored in `docs/specs/<id>/`.
2. A human review SHALL be required at the end of each phase.
3. The work item phase SHALL be tracked on the ticket via labels across
   `not-started → requirements-definition → design → tasks-breakdown → implementation →
   needs-review → complete`.
4. Once a spec doc is established, the work item SHALL be updated with a **reference**
   (link) to the checked-in artifact (single source of truth); subsequent changes SHALL
   be **edits to the doc, not new comments**.
5. `tasks.md` checkmarks SHALL be kept current as tasks complete.
6. The-loop SHALL self-check (run tests at checkpoints) and maintain a checked-in
   `execution-log.md`.
7. The-loop SHALL run X self-reviews and X critic reviews (default 3, configurable) via
   PR/ticket comments before escalating to a human, and present validated evidence at
   completion.
8. The-loop SHALL be resumable from any phase using the checked-in specs + log.

### R5 — Multi-party collaboration **[v0]**

1. Available collaborators (individuals or groups, multi-role) SHALL be defined up-front
   in the repo.
2. Each work item SHALL identify required collaborators up-front; not all tasks need all
   personas.
3. All collaboration SHALL happen via ticket/PR comments (paper trail); notifications
   via configured messaging channels.

### R6 — Documentation, decisions, learnings **[v0]**

1. Docs SHALL live under `docs/`, with `docs/architecture/architecture.md` as an index.
2. Decisions SHALL be logged under `docs/decisions/` (`decisions.md` + `decision-<nnn>.md`).
3. Learnings (user + system feedback) SHALL be captured under `learnings/`.

### R7 — Distribution, footprint & lifecycle **[v0]**

1. the-loop SHALL be installable as a Claude plugin directly from GitHub (no bespoke
   marketplace). (Cursor support **[deferred]**.)
2. Every managed file SHALL be tracked in `.the-loop/manifest.yaml`; meta files live
   under `.the-loop/`.
3. The-loop SHALL expose `init`, `work-on` and `upgrade-the-loop`; config SHALL be
   schema-validated and per-task overridable.

### R8 — Automation & the dream **[receiver v0; routing deferred]**

1. Webhooks (GitHub PR comments, Actions results) SHALL be able to trigger the harness.
   The **receiver** is delivered by the CLI (R9); routing events to the harness is
   deferred.
2. Creating a ticket SHALL be able to auto-trigger the-loop in a remote workspace,
   notifying humans only for decisions. **[deferred]**
3. The-loop SHALL orchestrate a project-wide DAG of work items (depends-on/blocked-by).
   **[deferred]**

### R9 — CLI companion **[v0]**

**User story:** As the the-loop plugin, I want a lightweight CLI for quality-of-life
commands, so that I can do things outside the harness (e.g. receive webhooks).
1. the-loop SHALL ship a Python CLI named `the-loop`, lightweight (zero required runtime
   deps) and **extensible** (easy to add commands).
2. The CLI SHALL provide `the-loop gh-webhook start|stop` — a GitHub webhook receiver
   that verifies the `X-Hub-Signature-256` HMAC and is configurable via
   `webhooks.ghWebhook`.
3. The CLI SHALL be written in Python (to allow future ML/self-learning SDKs).

### R10 — User-interaction principles **[v0 process]**

**User story:** As a human reviewing AI-authored work, I want enough context, focus and
education, so that I can make good calls on large PRs I didn't write.
1. WHEN the-loop requests any user input THEN it SHALL provide enough context for the
   user to make the right judgement call.
2. WHEN the-loop opens or updates a PR THEN the PR description SHALL present a
   **condensed, prioritized** summary telling the reviewer **where to focus** (and in
   what order), and SHALL document the insights from spec→implementation and the
   low-level decisions the harness made.
3. All diagrams (PR summaries, design docs, education) SHALL be authored in **mermaid**.
4. the-loop SHALL **intentionally and mandatorily educate** the user on low-level design
   decisions as their familiarity with the codebase decreases — this is not optional.
5. These behaviours SHALL be driven by `config.userInteraction`
   (`diagramFormat: mermaid`, `prSummary.*`, `educateUser: true`).

## Non-functional requirements

- All JSON parses; configs validate against `.the-loop/config.schema.json`.
- The file tree matches `.the-loop/manifest.yaml`.

## Out of scope (this work item)

Concrete language-tool integrations, webhook/remote automation, DAG execution across
items, messaging integrations and Cursor packaging are **[deferred]** to follow-up work
items (R2/R3/R8) per `decision-003`.

## Open questions (carried from issue #1)

Scripts-from-root scaling; chrome-devtools MCP for browser logs; predictability via
hooks vs custom code; how to _enforce_ mandatory user-education (R10.4) — config flag
today, a mechanism (hook/checklist) deferred; Cursor marketplace equivalent; GitHub
depends-on/blocked-by; Go tooling defaults. Tracked in
`reference/automation-and-roadmap.md`.
