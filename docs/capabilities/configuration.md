# Capability: configuration

> How the-loop is configured — split into a per-repo **plugin** config and a
> user/machine-level **CLI** config, each with its own schema.

## What it is

the-loop is configured through two independent files, reflecting its two lifecycles: a
plugin installed per repo, and a CLI companion that spans repos. See
[decision-021](../decisions/decision-021.md).

## Current behaviour

- The **plugin config** SHALL live at `.the-loop/config.yaml` in each repo, be checked
  in, and be validated against `.the-loop/config.schema.json`. It governs how the-loop
  drives the PDLC in *that* repo (ticketing, workflow, tooling, reviews, autonomy, …). A
  subset of keys MAY be overridden per work item via the spec markdown front-matter.
- The **CLI config** SHALL be a user/machine-level file, resolved as
  (1) `$THE_LOOP_CLI_CONFIG` if set, else
  (2) `$XDG_CONFIG_HOME/the-loop/config.yaml` (`XDG_CONFIG_HOME` defaults to `~/.config`).
  It SHALL be validated against `.the-loop/cli-config.schema.json` and holds settings the
  CLI uses across repos (currently `webhooks.ghWebhook`). It is scaffolded from
  `.the-loop/templates/cli-config.yaml`.
- The two configs SHALL be independent: the plugin config SHALL NOT carry CLI settings,
  and the CLI config SHALL NOT be required to drive the plugin.
- Per-repo facts that the CLI reads (e.g. `testing.integrationTestGlobs` for
  `the-loop scenarios`) SHALL remain in that repo's plugin config — ownership follows the
  setting's scope, not which binary reads it.
- For backward compatibility, WHEN no CLI config is present THEN the CLI SHALL still read
  a legacy `webhooks:` block from `.the-loop/config.yaml`, emitting a deprecation warning.
- Reading either YAML config SHALL require PyYAML (`the-loopy-one[config]`); without it
  the CLI SHALL fall back to built-in defaults (zero-runtime-dependency guarantee).

## Design

[`docs/specs/issue-63/design.md`](../specs/issue-63/design.md) ·
[`.the-loop/config.schema.json`](../../.the-loop/config.schema.json) ·
[`.the-loop/cli-config.schema.json`](../../.the-loop/cli-config.schema.json)

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-63 | Split config into per-repo plugin config + user-level CLI config (new `cli-config.schema.json`, `the_loop.config` loader, legacy fallback) | [spec](../specs/issue-63/), [decision-021](../decisions/decision-021.md) |
| issue-25 | Added `workflow.capabilitiesDir` (living capability docs) to the plugin config | [spec](../specs/issue-25/), [decision-020](../decisions/decision-020.md) |
| issue-1 | Established `.the-loop/config.yaml` + `config.schema.json` and the manifest | [spec](../specs/issue-1/), [decision-002](../decisions/decision-002.md) |
