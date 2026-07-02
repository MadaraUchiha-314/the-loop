# the-loop

**The loop for everything!** — an opinionated product-development-lifecycle (PDLC)
harness, shipped as a Claude Code plugin. Once a plan is approved, an agent harness
delivers a work item end-to-end with minimal or no human intervention, escalating to
humans only when a decision is genuinely needed.

> Status: **v0 foundation.** This release establishes the plugin skeleton, the
> configuration contract, templates, commands, the operating skill, and the
> documentation/knowledge structure. Runtime automation (webhooks, remote execution,
> DAG orchestration, language-specific tooling) is tracked as follow-up work. See
> [`docs/decisions/decision-003.md`](docs/decisions/decision-003.md).

## The loop, in one line

`requirements → design → tasks (each human-reviewed) → implement (+self-check) → self/critic review → evidence → complete → learn`

Work items are specified with a [Kiro-style](https://kiro.dev/docs/specs/) 3-phase
spec (`requirements.md` → `design.md` → `tasks.md`), each gated by a human review, then
executed autonomously. Each work item's phase is tracked on the ticket via labels:
`not-started → requirements-definition → design → tasks-breakdown → implementation →
needs-review → complete`.

## Install (Claude Code)

the-loop is installable directly from GitHub via the marketplace construct — no
bespoke marketplace publishing.

```
/plugin marketplace add MadaraUchiha-314/the-loop
/plugin install the-loop@the-loop
```

## Commands

| Command | What it does |
|---------|--------------|
| `/the-loop:init` | Scaffold the-loop into the current repo (config, docs, templates). Idempotent. |
| `/the-loop:work-on <ticket>` | Run the whole 3-phase spec workflow (requirements → design → tasks → execute) on a GitHub issue / Jira id. Resumable per phase. **Superset of the granular commands below.** |
| `/the-loop:upgrade-the-loop` | Reconcile a project's the-loop files with the installed plugin version. |

Granular commands run the same flow one step at a time:

| Command | What it does |
|---------|--------------|
| `/the-loop:new-requirement <title>` | Draft a `requirements.md` in a temporary `docs/specs/draft-<slug>/` folder **before a ticket exists**. |
| `/the-loop:create-ticket <path>` | Create the ticket from a `requirements.md`; promote `draft-<slug>/` → `docs/specs/<id>/`. |
| `/the-loop:create-design <id>` | Create `design.md` from the approved requirements (Phase 2). |
| `/the-loop:create-tasks-plan <id>` | Create the `tasks.md` DAG from requirements + design (Phase 3). |
| `/the-loop:execute-tasks <id>` | Implement the task DAG; self-check; self/critic-review; present evidence. |
| `/the-loop:finish-tasks <id>` | Cleanup after all tasks complete (close the ticket; extensible). |
| `/the-loop:work-status <id>` | Read-only status from the specs, task checkmarks and execution log. |

## How it works

- **Configuration** lives in [`.the-loop/config.yaml`](.the-loop/templates/config.yaml),
  validated against [`.the-loop/config.schema.json`](.the-loop/config.schema.json). A
  subset of keys can be overridden per work item via the markdown front-matter.
- **Everything the-loop manages** is tracked in
  [`.the-loop/manifest.yaml`](.the-loop/manifest.yaml).
- **Templates** for epics, stories, bugs and the 3-phase spec artifacts
  (`requirements`/`bugfix`, `design`, `tasks`, `execution-log`) live under
  [`.the-loop/templates/`](.the-loop/templates/).
- **The operating model** is captured in the
  [`the-loop` skill](skills/the-loop/SKILL.md), with the full detail in its
  [reference docs](skills/the-loop/reference/) — `workflow`, `reviewing`, `tooling`,
  `testing`, `minimalism`, `collaboration`, `observability`, and `automation`.

## CLI companion (`the-loop`)

Besides the plugin, the-loop ships a lightweight, **extensible Python CLI** (in
[`cli/`](cli/), package `the_loop`, zero runtime deps) for quality-of-life commands the
plugin can use. Python is intentional — it leaves room for future self-learning/ML
capabilities (mostly Python SDKs). First command is a GitHub webhook receiver:

```bash
the-loop gh-webhook start   # HMAC-verified receiver; GET /health; logs events
the-loop gh-webhook stop
the-loop scenarios          # tabular view of every Gherkin scenario the integration tests cover
```

See [`cli/README.md`](cli/README.md) for install and how to add commands.

## Rules the loop enforces

- Every work item has a ticket. Its 3-phase spec is **reviewed and approved per phase
  before execution**.
- Collaborators are identified up-front; not every task needs every persona.
- Every human decision leaves a **paper trail** on the ticket or PR.
- Self-checks run tests at logical checkpoints; progress is logged for visibility.
- Configured self-reviews and critic reviews run **before** escalating to a human.
- The same tooling runs locally and in CI; logging is identical at dev-time and runtime.
- Integration tests document their scenario in **Gherkin** docstrings (linked to the
  spec's `requirements.md`), queryable as a table via `the-loop scenarios`.
- APIs are **contract-first**: REST specs in `specs/openapi/` (OpenAPI), GraphQL SDL in
  `specs/graphql/`; docs are generated from the contracts, never hand-written.
- All commits follow **Conventional Commits**.
- PRs are written **for the reviewer**: a condensed, prioritized summary of where to
  focus, **mermaid** diagrams, and documented low-level decisions — and the loop
  **educates the user** on those decisions (mandatory, not optional).

## Repository layout

```
.claude-plugin/        plugin.json, marketplace.json
.the-loop/             config schema, default config, manifest, templates, registries
commands/              init, work-on, upgrade-the-loop
skills/the-loop/       operating-model skill (+ reference/ docs)
hooks/                 hooks.json (SessionStart reminder)
cli/                   the-loop Python CLI (the_loop package; gh-webhook receiver)
docs/
  architecture/        architecture.md (index)
  decisions/           decisions.md + decision-<nnn>.md
  specs/<id>/          requirements.md|bugfix.md, design.md, tasks.md, execution-log.md
learnings/             learnings.md + learning-<nnn>.md
```

## Development (the-loop's own quality gates)

the-loop dogfoods its own rules: the same checks run locally (pre-commit) and in CI.

```bash
make install-dev     # ruff, pyright, pytest, pre-commit, jsonschema, pyyaml, the CLI
pre-commit install   # run the gates on every commit
make check           # ruff (lint+format) · pyright · schema validation · pytest
pre-commit run --all-files   # exactly what CI runs
```

Gates: **ruff** (lint+format) and **pyright** for `cli/`, **pytest** for the CLI,
**markdownlint** for all docs, and **schema validation** for `.the-loop` config. CI
([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs the very same pre-commit
hooks — no local-vs-CI drift. See [`docs/decisions/decision-006.md`](docs/decisions/decision-006.md).

## Roadmap (deferred from v0)

- Webhook triggers (PR review comments, GitHub Actions results).
- Remote-workspace execution ("the dream").
- DAG orchestration across work items (depends-on / blocked-by).
- Concrete per-language tooling integrations (uv, bun, nx, pytest, vitest, playwright,
  oxlint, ruff, pyright, …) and messaging integrations.
- Cursor packaging.

## Feedback

All feedback for the-loop is provided through GitHub issues on this repository. And —
fittingly — the-loop uses the-loop to improve itself.

## License

MIT — see [LICENSE](LICENSE).
