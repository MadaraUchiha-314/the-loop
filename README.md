# the-loop

**The loop for everything!** — an opinionated product-development-lifecycle (PDLC)
harness, shipped as a Claude Code **and Cursor** plugin. Once a plan is approved, an
agent harness delivers a work item end-to-end with minimal or no human intervention,
escalating to humans only when a decision is genuinely needed.

> Status: **v0 foundation.** This release establishes the plugin skeleton, the
> configuration contract, templates, commands, the operating skill, and the
> documentation/knowledge structure. Runtime automation (webhooks, remote execution,
> DAG orchestration, language-specific tooling) is tracked as follow-up work. See
> [`docs/decisions/decision-003.md`](docs/decisions/decision-003.md).

**[Read the full documentation](https://madarauchiha-314.github.io/the-loop/)** —
installation, quickstart, CLI reference, and developer docs.

## The loop, in one line

`(brainstorm) → requirements → design → tasks (each iterated until locked + human-reviewed) → implement (+self-check) → self/critic review → evidence → complete → learn`

A work item is a chain of artifacts, each derived from the one before it and **iterated
with feedback until it is locked** before the loop advances. Optionally it starts with a
free-form `brainstorm.md` scratchpad (the root artifact); then it is specified with a
[Kiro-style](https://kiro.dev/docs/specs/) 3-phase spec (`requirements.md` → `design.md` →
`tasks.md`), each gated by a human review, then executed autonomously. Each work item's
phase is tracked on the ticket via labels: `not-started → brainstorming (optional) →
requirements-definition → design → tasks-breakdown → implementation → needs-review →
complete`.

## Install

the-loop is installable directly from GitHub via each harness's marketplace construct —
no bespoke marketplace publishing. One repo, one set of skills/commands/templates,
two plugin manifests (`.claude-plugin/` and `.cursor-plugin/`).

### Claude Code

```
/plugin marketplace add MadaraUchiha-314/the-loop
/plugin install the-loop@the-loop
```

### Cursor

Cursor (≥ 2.5) resolves the plugin from this repo's `.cursor-plugin/` manifests. Install
it either way:

- **From the marketplace** — in the slash menu run `/add-plugin`, or open **Settings →
  Plugins → Add**, and point it at the repository URL:

  ```
  https://github.com/MadaraUchiha-314/the-loop
  ```

- **Locally** (for development) — check the repo out under Cursor's local plugins dir:

  ```
  git clone https://github.com/MadaraUchiha-314/the-loop \
    ~/.cursor/plugins/local/the-loop
  ```

Skills follow the [Agent Skills](https://agentskills.io) open standard, so the same
`SKILL.md` powers both harnesses; commands appear in Cursor's slash menu (by filename,
e.g. `/init`); the Claude Code SessionStart hook is replaced by the always-applied rule
`rules/the-loop.mdc`.

## Commands

Names below use Claude Code's `/the-loop:` prefix; in Cursor the same commands appear
in the slash menu by filename (e.g. `/init`, `/work-on`).

| Command | What it does |
|---------|--------------|
| `/the-loop:init` | Scaffold the-loop into the current repo (config, docs) via a guided, schema-driven onboarding with sensible defaults (`--defaults` skips the interaction). Idempotent. |
| `/the-loop:work-on <ticket>` | Run the whole 3-phase spec workflow (requirements → design → tasks → execute) on a GitHub issue / Jira id. Resumable per phase. **Superset of the granular commands below.** |
| `/the-loop:upgrade-the-loop` | Reconcile a project's the-loop files with the installed plugin version. |

Granular commands run the same flow one step at a time:

| Command | What it does |
|---------|--------------|
| `/the-loop:brainstorm <title>` | *(Optional Phase 0)* Draft a free-form `brainstorm.md` scratchpad (the root artifact) for a fuzzy idea; iterate, then convert to requirements. |
| `/the-loop:new-requirement <title>` | Draft a `requirements.md` in a temporary `docs/specs/draft-<slug>/` folder **before a ticket exists** (converts a sibling `brainstorm.md` if present). |
| `/the-loop:create-ticket <path>` | Create the ticket from a `requirements.md`; promote `draft-<slug>/` → `docs/specs/<id>/`. |
| `/the-loop:create-design <id>` | Create `design.md` from the approved requirements (Phase 2). |
| `/the-loop:create-tasks-plan <id>` | Create the `tasks.md` DAG from requirements + design (Phase 3). |
| `/the-loop:execute-tasks <id>` | Implement the task DAG; self-check; self/critic-review; present evidence. |
| `/the-loop:finish-tasks <id>` | Cleanup after all tasks complete (close the ticket; extensible). |
| `/the-loop:work-status <id>` | Read-only status from the specs, task checkmarks and execution log. |

## How it works

- **Configuration** lives in [`.the-loop/config.yaml`](skills/the-loop/templates/config.yaml),
  validated against [`.the-loop/config.schema.json`](.the-loop/config.schema.json). A
  subset of keys can be overridden per work item via the markdown front-matter. The CLI
  companion's own daemon config (webhook receiver / poller) is independent and not tied
  to a repo — see [`cli/README.md`](cli/README.md#two-independent-config-files-decision-032).
- **Everything the-loop manages** is tracked in
  [`.the-loop/manifest.yaml`](.the-loop/manifest.yaml).
- **Templates** for epics, stories, bugs, the optional `brainstorm` root artifact and the
  3-phase spec artifacts (`requirements`/`bugfix`, `design`, `tasks`, `execution-log`) are
  **internal to the-loop** — they ship with the plugin under
  [`skills/the-loop/templates/`](skills/the-loop/templates/) and are read from there when
  an artifact is authored, rather than being copied into every project.
- **The operating model** is captured in the
  [`the-loop` skill](skills/the-loop/SKILL.md), with the full detail in its
  [reference docs](skills/the-loop/reference/) — `workflow`, `design-artifacts`,
  `reviewing`, `tooling`, `testing`, `minimalism`, `collaboration`, `observability`, and
  `automation`.

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
- **Capability docs are the organized view of specs**: per-work-item specs are the
  historical record; living docs under `docs/capabilities/` are the single source of
  truth for each capability's *current* behaviour, updated **in the same PR** as the
  work item (a ready-to-ship gate item), with history links back to the specs.
- **UI/UX design is a first-class artifact**: for user-facing work the design phase tracks
  Figma links and/or self-contained HTML+CSS+JS prototypes under `docs/specs/<id>/design/`,
  iterated-until-locked with the designer — the visual contract implementation matches.
- All commits follow **Conventional Commits**.
- PRs are written **for the reviewer**: a condensed, prioritized summary of where to
  focus, **mermaid** diagrams, and documented low-level decisions — and the loop
  **educates the user** on those decisions (mandatory, not optional).

## Repository layout

```
.claude-plugin/        plugin.json, marketplace.json (Claude Code)
.cursor-plugin/        plugin.json, marketplace.json (Cursor)
.the-loop/             config schema, default config, manifest, templates, registries
commands/              init, work-on, upgrade-the-loop
skills/the-loop/       operating-model skill (+ reference/ docs), Agent Skills standard
rules/                 the-loop.mdc (Cursor always-applied reminder rule)
hooks/                 hooks.json (Claude Code SessionStart reminder)
cli/                   the-loop Python CLI (the_loop package; gh-webhook receiver)
docs/
  architecture/        architecture.md (index)
  capabilities/        capabilities.md (index) + <capability>.md (organized view of specs; current behaviour per capability)
  decisions/           decisions.md + decision-<nnn>.md
  specs/<id>/          brainstorm.md (optional), requirements.md|bugfix.md, design.md, design/ (UI/UX artifacts, optional), tasks.md, execution-log.md
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

## Feedback

All feedback for the-loop is provided through GitHub issues on this repository. And —
fittingly — the-loop uses the-loop to improve itself.

## License

MIT — see [LICENSE](LICENSE).
