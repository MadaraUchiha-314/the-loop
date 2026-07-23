# How it works

- **Configuration** lives in `.the-loop/config.yaml`, validated against
  `.the-loop/config.schema.json`. A subset of keys can be overridden per work item via
  the markdown front-matter. The CLI companion's own daemon config (webhook receiver /
  poller) is independent and not tied to a repo — see the
  [CLI reference](/cli/#two-independent-config-files-decision-032).
- **Everything the-loop manages** is tracked in `.the-loop/manifest.yaml`.
- **Templates** for epics, stories, bugs, the optional `brainstorm` root artifact and
  the 3-phase spec artifacts (`requirements`/`bugfix`, `design`, `tasks`,
  `execution-log`) are **internal to the-loop** — they ship with the plugin under
  `skills/the-loop/templates/` and are read from there when an artifact is authored,
  rather than being copied into every project.
- **The operating model** is captured in the `the-loop` skill, with the full detail in
  its [reference docs](/developer/operating-model/) — workflow, design-artifacts,
  reviewing, tooling, testing, minimalism, collaboration, observability, and
  automation.

## Repository layout

```text
.claude-plugin/     plugin.json, marketplace.json (Claude Code)
.cursor-plugin/      plugin.json, marketplace.json (Cursor)
.the-loop/            config schema, default config, manifest, templates, registries
commands/              init, work-on, upgrade-the-loop
skills/the-loop/         operating-model skill (+ reference/ docs), Agent Skills standard
rules/                     the-loop.mdc (Cursor always-applied reminder rule)
hooks/                       hooks.json (Claude Code SessionStart reminder)
cli/                            the-loop Python CLI (the_loop package; gh-webhook receiver)
docs/
  architecture/                  architecture.md (index)
  capabilities/                    capabilities.md (index) + <capability>.md
  decisions/                          decisions.md + decision-<nnn>.md
  specs/<id>/                            brainstorm.md (optional), requirements.md|bugfix.md,
                                          design.md, design/ (optional UI/UX artifacts),
                                          tasks.md, execution-log.md
learnings/                               learnings.md + learning-<nnn>.md
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
runs the very same pre-commit hooks — no local-vs-CI drift. See
[decision-006](/developer/decisions/decision-006).

## Roadmap

Deferred work and open questions from the founding issue live in the
[roadmap](/developer/roadmap).
