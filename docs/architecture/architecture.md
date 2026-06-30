# Architecture — the-loop

This is the top-level architecture index. Sub-component architectures are linked from
here as they are added (`docs/architecture/<component>.md`).

## What the-loop is

A distributable harness (shipped as a **Claude plugin**, with Cursor support planned)
that encodes a predictable product-development-lifecycle. Given an approved plan, an
agent harness delivers a work item end-to-end, escalating to humans only for decisions.

## Components

### 1. Distribution (plugin + marketplace)

- `.claude-plugin/plugin.json` — plugin manifest (commands, skills, hooks).
- `.claude-plugin/marketplace.json` — installable directly from GitHub; no bespoke
  marketplace. Cursor equivalent: TODO.

### 2. Project footprint (`.the-loop/`)

Everything the-loop creates/maintains is tracked in `.the-loop/manifest.yaml`.
- `config.yaml` (+ `config.schema.json`) — per-project configuration; per-task
  overrides via work-item front-matter.
- `templates/` — work-item (epic/story/bug) and process (plan/log/decision/learning)
  templates.
- `external-tools.md`, `collaborators.yaml` — user-owned registries.

### 3. The loop (runtime workflow)

A Kiro-style 3-phase spec workflow (https://kiro.dev/docs/specs/), each phase gated by
a human review, then autonomous execution:

`requirements/bugfix (+approve) → design (+approve) → tasks DAG (+approve) →
implementation (+self-check) → self-review → critic-review → needs-review → evidence →
complete → learn`.

The work item's phase is tracked on the ticket via labels and mirrored in the execution
log: `not-started → requirements-definition → design → tasks-breakdown → implementation
→ needs-review → complete`. Per-work-item specs live in `docs/specs/<id>/`. Implemented
as commands/skills today; hooks add predictability where a step must always run.

### 4. Knowledge & feedback

- `docs/architecture/`, `docs/decisions/`, `docs/specs/<id>/` (requirements/bugfix,
  design, tasks, execution-log), `learnings/`.

### 5. Collaboration & ticketing

- GitHub Issues/Projects (default) or Jira. All collaboration via ticket/PR comments;
  notifications/escalations via configured messaging channels.

### 6. CLI companion (`the-loop`, Python)

A lightweight, extensible Python CLI under `cli/` (package `the_loop`) for
quality-of-life commands the plugin itself can use. Zero runtime deps (stdlib only);
Python is chosen to leave room for future self-learning/ML SDKs. Extensible command
registry. First command: `the-loop gh-webhook start|stop` — a GitHub webhook receiver
(HMAC-verified) that is the on-ramp to the trigger automation below. See
`docs/decisions/decision-005.md`.

### 7. Triggers (future)

- Webhooks: PR review comments and GitHub Actions results auto-trigger the harness
  (received by the CLI's `gh-webhook` server).
- The "dream": creating a ticket spins up the-loop in a remote workspace and delivers
  the work, notifying humans only when a decision is needed.
- DAG orchestration across work items using depends-on / blocked-by relationships.

## Status

v0 establishes the plugin skeleton, configuration contract, templates, commands,
skill, and documentation/knowledge structure. Runtime automation (webhooks, remote
execution, DAG orchestration, language-specific tooling integrations) is future work
tracked via the decision log and follow-up issues.
