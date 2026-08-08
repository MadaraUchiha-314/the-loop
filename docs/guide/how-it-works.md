# How it works

## The process is data

Both loops are **declared, not coded**: `pdlc-work-item-loop.yaml` (outer) and
`pdlc-pr-loop.yaml` (inner) ship as package data inside the CLI, under
`cli/the_loop/graph/`, and the runtime executes that declaration rather than re-deriving
the process from prose. A node is one step, with an ordered entry hook chain and an ordered
exit hook chain; it is **complete** when the exit chain passes, **waiting** when a hook
returns `wait`, and **blocked** when one returns `block`. Edges route on hook *outcomes*
only — there is no expression language, which is what lets judgement (the agent produces
facts) and determinism (declared edges route on them) coexist.

Consequences worth knowing before you read anything else:

- The graph is **internal to the-loop**. A consuming repository does not define or override
  it; a repo-local `.the-loop/graph.yaml` is ignored with a warning.
- Gates read **checked-in artifacts**, never prose or chat. `the-loop check --recompute`
  ignores stored state and re-derives every verdict from the artifacts, which is what makes
  the CI gate meaningful.
- A **forced transition** (`the-loop graph force --to <node> --reason <why>`) moves the
  pointer and never forges a verdict: the bypassed gate keeps its real result.
- The graph **assigns** as well as judges — entering a node pushes that node's assignment
  into the session bound to that loop.

Inspect it with [`the-loop graph`](/cli/commands/graph) and read the full behaviour in the
[process-graph capability](/capabilities/process-graph).

## Configuration, templates and the operating model

- **Configuration** lives in `.the-loop/harness-config.yaml`, validated against
  `.the-loop/harness-config.schema.json`. A subset of keys can be overridden per work item
  via the markdown front-matter. The CLI daemon's own config (webhook receiver / poller) is
  independent and not tied to a repo — see the [configuration reference](/config/).
- **Everything the-loop manages** is tracked in `.the-loop/manifest.yaml`.
- **Templates** for epics, stories, bugs, the optional `brainstorm` root artifact and the
  spec artifacts (`requirements`/`bugfix`, `design`, `testing-plan`, `tasks`,
  `execution-log`) are **internal to the-loop** — they ship with the plugin under
  `skills/the-loop/templates/` and are read from there when an artifact is authored, rather
  than being copied into every project.
- **The operating model** is captured in the `the-loop` skill, with the full detail in its
  [reference docs](/operating-model/) — workflow, context, onboarding, instructions,
  design-artifacts, reviewing, security, tooling, testing, minimalism, token economy,
  collaboration, observability, and automation.
- **How the artifacts read** is a second bundled skill, `the-loop:writing`: a four-part
  spine (what was broken → what we did → what it costs → what to check), *draw it rather
  than describe it*, and a carve-out keeping EARS criteria and API contracts formal.

## Repository layout

```text
.claude-plugin/    plugin.json, marketplace.json (Claude Code)
.cursor-plugin/    plugin.json, marketplace.json (Cursor)
.the-loop/         config schema, default config, manifest, registries
commands/          init, work-on, upgrade-the-loop, and the granular commands
skills/the-loop/   operating-model skill (+ reference/ and templates/)
skills/writing/    the-loop:writing — how the artifacts a human reads are written
rules/             the-loop.mdc (Cursor always-applied reminder rule)
hooks/             hooks.json (Claude Code SessionStart reminder)
cli/               the-loop Python CLI (the_loop package)
  the_loop/graph/    pdlc-work-item-loop.yaml, pdlc-pr-loop.yaml, runtime, hooks
docs/
  api-specs/         the-loop's own control-plane API contract (OpenAPI)
  architecture/      architecture.md (index)
  capabilities/      capabilities.md (index) + <capability>.md
  decisions/         decisions.md + decision-<nnn>.md
  specs/<id>/        brainstorm.md (optional), requirements.md|bugfix.md, design.md,
                     design/ (optional UI/UX artifacts), testing-plan.md, tasks.md,
                     execution-log.md, evidence/
learnings/         learnings.md + learning-<nnn>.md
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
**markdownlint** for all docs, and **schema validation** for `.the-loop` config. CI runs the
very same pre-commit hooks — no local-vs-CI drift. See
[decision-006](/decisions/decision-006).

## What's next

Forward-looking work is tracked as GitHub issues and in the
[decision log](/decisions/decisions); the per-work-item history lives under
[specs](/specs/).
