# Architecture — the-loop

This is the top-level architecture index. Sub-component architectures are linked from
here as they are added (`docs/architecture/<component>.md`).

## What the-loop is

A distributable harness (shipped as a plugin for **Claude Code and Cursor**) that
encodes a predictable product-development-lifecycle. Given an approved plan, an
agent harness delivers a work item end-to-end, escalating to humans only for decisions.

## Components

### 1. Distribution (plugin + marketplace)

- `.claude-plugin/plugin.json` — Claude Code plugin manifest (commands, skills, hooks).
- `.cursor-plugin/plugin.json` — Cursor plugin manifest over the SAME `skills/` (Agent
  Skills standard) and `commands/`; `rules/the-loop.mdc` replaces the SessionStart hook.
- `.claude-plugin/marketplace.json` + `.cursor-plugin/marketplace.json` — installable
  directly from GitHub in both harnesses; no bespoke marketplace. See `decision-015`.
- `skills/the-loop/templates/` — work-item (epic/story/bug) and process
  (plan/log/decision/learning) templates. **Internal to the plugin** (`manifest.templatesDir`):
  read from `${CLAUDE_PLUGIN_ROOT}` when an artifact is authored, never copied into a
  project (issue-36).

### 2. Project footprint (`.the-loop/`)

Everything the-loop creates/maintains is tracked in `.the-loop/manifest.yaml`.
- `config.yaml` (+ `config.schema.json`) — per-project **plugin** configuration; per-task
  overrides via work-item front-matter. The CLI daemon's own `cli-config.yaml`
  (`webhooks`, `polling`, `eventLog`; `cli-config.schema.json`) is independent and NOT
  required to be per-project — `--config`/`-c`, else `$THE_LOOP_CLI_CONFIG`, else
  `./.the-loop/cli-config.yaml`, else `~/.the-loop/cli-config.yaml`, so the daemon is
  not tied to a single repo (decision-032).
- `collaborators.yaml` — user-owned registry (external tools now live inline in
  `config.externalTools`, issue-37).

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
- `docs/capabilities/` — living capability docs, the **organized view of the specs**:
  one doc per capability (product-feature and architecture shaped), the single source
  of truth for its *current* behaviour, with history rows linking the raw specs and
  decisions that produced it. Updated in the same PR as the work item (ready-to-ship
  gate item). See `docs/decisions/decision-020.md`.

### 5. Collaboration & ticketing

- GitHub Issues/Projects (default) or Jira. All collaboration via ticket/PR comments;
  notifications/escalations via configured messaging channels.

### 6. CLI companion (`the-loop`, Python)

A lightweight, extensible Python CLI under `cli/` (package `the_loop`) for
quality-of-life commands the plugin itself can use. Zero runtime deps (stdlib only);
Python is chosen to leave room for future self-learning/ML SDKs. Extensible command
registry. Commands: `gh-webhook start|stop` (HMAC-verified GitHub webhook receiver
with `--route`), `sessions register|list|close` (work item ↔ session registry), and
`scenarios` (queryable integration-test scenario table). See
`docs/decisions/decision-005.md`.

Published to PyPI as the distribution **`the-loopy-one`** (the base name was taken; the
import package `the_loop` and the `the-loop` console script are unchanged) via
`.github/workflows/release.yml`, using GitHub Actions **Trusted Publishing (OIDC)** — no
stored token. Releases are **automatic and semantic**: on merge to `main`, `cz bump`
(commitizen) derives the version from the Conventional Commits / PR titles since the last
tag, tags it, and — gated by the `pypi` environment — builds the member with `uv` and
publishes. See `docs/specs/issue-21/design.md` and `docs/decisions/decision-019.md`.

### 7. Triggers

- **Webhook → session routing (shipped, issue #15).** PR/issue comments and GitHub
  Actions results reach the harness session working that item: the `gh-webhook`
  receiver routes verified events through a session registry
  (`.the-loop/sessions/*.json`, managed by `the-loop sessions`) and resumes the
  matched session via its official CLI (`claude -p --resume` /
  `cursor-agent -p --resume`), serialized per session and parallel across sessions.
  See `docs/specs/issue-15/design.md` and `docs/decisions/decision-016.md`.
- The "dream" (future): creating a ticket spins up the-loop in a remote workspace and
  delivers the work, notifying humans only when a decision is needed.
- DAG orchestration across work items using depends-on / blocked-by relationships
  (future).

## Status

v0 establishes the plugin skeleton, configuration contract, templates, commands,
skill, and documentation/knowledge structure. Runtime automation (webhooks, remote
execution, DAG orchestration, language-specific tooling integrations) is future work,
tracked in `docs/roadmap.md` (kept out of the published skill) and the decision log.
