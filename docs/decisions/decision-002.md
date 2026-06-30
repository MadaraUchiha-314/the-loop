# Decision 002: Track the-loop's footprint via manifest + config schema

- **Status:** accepted
- **Date:** 2026-06-27
- **Deciders:** @MadaraUchiha-314 (via issue #1)
- **Work item:** issue-1

## Context
the-loop creates and maintains many files in a project and must be able to initialize,
validate and upgrade them reliably across versions. Configuration is opinionated but
must be overridable globally and per task.

## Decision
- All files the-loop creates/maintains are enumerated in `.the-loop/manifest.yaml`;
  all meta files live under `.the-loop/`.
- Configuration lives in `.the-loop/config.yaml`, validated against a versioned
  `.the-loop/config.schema.json` that the plugin owns and exposes.
- A subset of config keys is overridable per work item via the YAML front-matter
  `overrides` of the work-item / spec markdown.

## Consequences
- `/init` and `/upgrade-the-loop` have a single source of truth to reconcile against.
- Config changes are validatable and migratable.
- Front-matter overrides keep task-level customization close to the work.

## Alternatives considered
- Discovering files implicitly — rejected: not reliably upgradable.
- Free-form config without schema — rejected: no validation guarantees.
