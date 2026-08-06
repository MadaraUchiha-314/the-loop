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

![the-loop workflow: a ticket is opened, then the spec artifacts (optional
brainstorm.md, requirements.md, design.md, tasks.md) are each iterated with feedback
until locked, gated by human review; then implement + self-check, self/critic review
and evidence run autonomously, ending in complete and learn](docs/assets/the-loop-workflow.svg)

*Drawn with [Excalidraw](https://excalidraw.com). Both the
[SVG](docs/assets/the-loop-workflow.svg) (which embeds the scene) and the
[`.excalidraw` source](docs/assets/the-loop-workflow.excalidraw) can be dropped into
excalidraw.com to edit.*

A work item is a chain of artifacts, each derived from the one before it and **iterated
with feedback until it is locked** before the loop advances. Optionally it starts with a
free-form `brainstorm.md` scratchpad (the root artifact); then it is specified with a
[Kiro-style](https://kiro.dev/docs/specs/) 3-phase spec (`requirements.md` → `design.md` →
`tasks.md`), each gated by a human review, then executed autonomously. Each work item's
phase is tracked on the ticket via labels: `not-started → brainstorming (optional) →
requirements-definition → design → test-planning → tasks-breakdown → implementation →
verification → needs-review →
complete`.

## Install

the-loop is installable directly from GitHub via each harness's marketplace construct —
no bespoke marketplace publishing. One repo, one set of skills/commands/templates,
two plugin manifests (`.claude-plugin/` and `.cursor-plugin/`).

### From a terminal (Claude Code)

With [the CLI](#cli-companion-the-loop) installed, one command installs the plugin without
opening a session — at user scope, or for one project only:

```bash
pip install the-loopy-one                                  # once
the-loop install                                           # CLI + the Claude Code plugin
the-loop install claude --scope project --project-dir .    # this repository only
the-loop upgrade                                           # when a release lands
```

It drives Claude Code's own plugin installer, prints every command before running it
(`--dry-run` previews), and says what it skipped and why. Cursor is not covered yet
([#157](https://github.com/MadaraUchiha-314/the-loop/issues/157)). The in-session routes
below are unchanged, and are the shortest path if you would rather not install the CLI.

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
| `/the-loop:work-on <ticket>` | Run the whole loop (requirements → design → testing plan → tasks → execute → verify) on a GitHub issue / Jira id. Resumable per phase. **Superset of the granular commands below.** |
| `/the-loop:upgrade-the-loop` | Reconcile a project's the-loop files with the installed plugin version. |

Granular commands run the same flow one step at a time:

| Command | What it does |
|---------|--------------|
| `/the-loop:brainstorm <title>` | *(Optional Phase 0)* Draft a free-form `brainstorm.md` scratchpad (the root artifact) for a fuzzy idea; iterate, then convert to requirements. |
| `/the-loop:new-requirement <title>` | Draft a `requirements.md` in a temporary `docs/specs/draft-<slug>/` folder **before a ticket exists** (converts a sibling `brainstorm.md` if present). |
| `/the-loop:create-ticket <path>` | Create the ticket from a `requirements.md`; promote `draft-<slug>/` → `docs/specs/<id>/`. |
| `/the-loop:create-design <id>` | Create `design.md` from the approved requirements (Phase 2). |
| `/the-loop:create-testing-plan <id>` | Create `testing-plan.md` from requirements + design — which kinds of testing apply, the verification environment, the evidence to capture. |
| `/the-loop:create-tasks-plan <id>` | Create the `tasks.md` DAG from requirements + design + testing plan. |
| `/the-loop:execute-tasks <id>` | Implement the task DAG; verify against the testing plan; self-check; self/critic-review; present evidence. |
| `/the-loop:verify-work <id>` | Execute the testing plan after implementation: run the planned activities, record results, commit the evidence. |
| `/the-loop:finish-tasks <id>` | Cleanup after all tasks complete (close the ticket; extensible). |
| `/the-loop:work-status <id>` | Read-only status from the specs, task checkmarks and execution log. |

## How it works

- **Configuration** lives in [`.the-loop/harness-config.yaml`](skills/the-loop/templates/harness-config.yaml),
  validated against [`.the-loop/harness-config.schema.json`](.the-loop/harness-config.schema.json). A
  subset of keys can be overridden per work item via the markdown front-matter. The CLI
  companion's own daemon config (webhook receiver / poller) is independent and not tied
  to a repo — see the [configuration reference](https://madarauchiha-314.github.io/the-loop/config/).
- **Everything the-loop manages** is tracked in
  [`.the-loop/manifest.yaml`](.the-loop/manifest.yaml).
- **Templates** for epics, stories, bugs, the optional `brainstorm` root artifact and the
  spec artifacts (`requirements`/`bugfix`, `design`, `testing-plan`, `tasks`,
  `execution-log`) are
  **internal to the-loop** — they ship with the plugin under
  [`skills/the-loop/templates/`](skills/the-loop/templates/) and are read from there when
  an artifact is authored, rather than being copied into every project.
- **Your project's own rules are read too.** Register your existing convention docs —
  `CONTRIBUTING.md`, a house style guide, a company-wide policy file living outside the
  repo — under `customInstructions.docs`, and the loop reads every one of them, in order,
  before it starts a work item. `the-loop instructions` reports which ones actually
  resolve, so a mistyped path is a signal rather than silence. See the
  [instructions reference](skills/the-loop/reference/instructions.md).
- **The operating model** is captured in the
  [`the-loop` skill](skills/the-loop/SKILL.md), with the full detail in its
  [reference docs](skills/the-loop/reference/) — `workflow`, `context`, `onboarding`,
  `instructions`, `design-artifacts`, `reviewing`, `security`, `tooling`, `testing`,
  `minimalism`, `token-economy`, `collaboration`, `observability`, and `automation`.
- **How the artifacts read** is a second bundled skill,
  [`the-loop:writing`](skills/writing/SKILL.md): the four-part spine, a per-artifact
  **prose budget** each template declares in a `<!-- writing: budget=N -->` marker
  (`userInteraction.writingStyle`), *draw it rather than describe it*, and a carve-out
  keeping EARS criteria and API contracts formal. Budgets are advisory — over budget is a
  review comment, never a blocked phase.

## CLI companion (`the-loop`)

Besides the plugin, the-loop ships a lightweight, **extensible Python CLI** (in
[`cli/`](cli/), package `the_loop`, one runtime dependency — PyYAML, since its config
is YAML) for quality-of-life commands the plugin can use. Python is intentional — it leaves room for future self-learning/ML
capabilities (mostly Python SDKs). It turns ticket activity into agent runs and tells you
what happened:

```bash
the-loop gh-webhook start   # HMAC-verified GitHub webhook receiver; routes events to sessions
the-loop poll start         # pull-based ingress, for hosts a webhook can't reach
the-loop sessions list      # the work-item ↔ harness-session registry
the-loop events --follow    # the structured trail of every routing/dispatch decision
the-loop check <work-item>  # evaluate a work item's nodes against its artifacts (pure; CI-safe)
the-loop graph status <id>  # where a work item sits in the process graph
the-loop critic run <name> --prompt-file <path>   # one critic round; prints a JSON envelope
the-loop scenarios          # every Gherkin scenario the integration tests cover
the-loop instructions       # the project's registered instruction docs, and whether they resolve
the-loop install            # install the-loop itself: this CLI + the Claude Code plugin
the-loop upgrade            # move both to the current release (user or project scope)
```

Full documentation: **[the-loop CLI](https://madarauchiha-314.github.io/the-loop/cli/)** — overview,
[installation](https://madarauchiha-314.github.io/the-loop/cli/installation),
[getting started](https://madarauchiha-314.github.io/the-loop/cli/getting-started),
[concepts](https://madarauchiha-314.github.io/the-loop/cli/concepts),
[every command](https://madarauchiha-314.github.io/the-loop/cli/commands/) and
[every config option](https://madarauchiha-314.github.io/the-loop/config/cli/).

## Rules the loop enforces

- Every work item has a ticket. Its spec is **reviewed and approved per phase
  before execution**.
- Collaborators are identified up-front; not every task needs every persona.
- Every human decision leaves a **paper trail** on the ticket or PR.
- Self-checks run tests at logical checkpoints; progress is logged for visibility.
- Configured self-reviews and critic reviews run **before** escalating to a human. A critic
  is a *runnable* config entry — `reviews.critics[]` names the harness (or the executable
  and its args), and `the-loop critic run` spawns it and hands its output back.
- The project's **own** conventions are honoured: every doc registered in
  `customInstructions.docs` is read before work starts, and the loop's own gates —
  security, paper trail, reviews — are the one thing an instruction doc cannot weaken.
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
skills/writing/        the-loop:writing — how the artifacts a human reads are written
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
