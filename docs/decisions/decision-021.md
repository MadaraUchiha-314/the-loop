# Decision 021: Split the-loop's config into a per-repo plugin config and a user-level CLI config

- **Status:** accepted
- **Date:** 2026-07-23
- **Deciders:** @MadaraUchiha-314 (issue #63)
- **Work item:** issue-63

## Context

the-loop had a single config file, `.the-loop/config.yaml`, that mixed two concerns:

- **Per-repo plugin settings** — how the-loop drives the PDLC in *this* repo
  (ticketing, workflow, tooling, reviews, autonomy, …). the-loop is installed as a
  Claude Code / Cursor plugin in each repo, so these are naturally checked in per repo.
- **CLI settings** — the `webhooks:` block read by the `the-loop` CLI's webhook
  receiver and event router. The CLI is a long-running companion that works **across
  many repos** and is not tied to any single one; carrying its config inside one repo's
  plugin config conflated the two lifecycles.

Issue #63 asked to split the config into two parts: one for the CLI (cross-repo,
repo-independent) and one for the per-repo Claude/Cursor plugin, with the plugin
settings independent of the CLI settings.

## Decision

Split into two configs with separate schemas and separate homes:

- **Plugin config** — `.the-loop/config.yaml`, per repo, checked in, validated against
  `.the-loop/config.schema.json`. Unchanged except that the `webhooks:` block is
  removed. This is what the plugin reads.
- **CLI config** — a **user/machine-level** file resolved as:
  1. `$THE_LOOP_CLI_CONFIG` (explicit path override), else
  2. `$XDG_CONFIG_HOME/the-loop/config.yaml` (`XDG_CONFIG_HOME` defaults to `~/.config`).

  It holds the `webhooks:` block (host/port/path/secret env, events, routing) and is
  validated against `.the-loop/cli-config.schema.json`. Scaffold it from
  `.the-loop/templates/cli-config.yaml`.

Per-repo data that the CLI happens to read stays in the plugin config: `the-loop
scenarios` reads `testing.integrationTestGlobs` from whichever repo it is run in. The
rule is about *ownership of the setting*, not which binary reads it — cross-repo CLI
behaviour lives in the CLI config; repo-specific facts live in that repo's plugin
config.

**Backward compatibility:** when no CLI config is present, the CLI still reads a legacy
`webhooks:` block from the repo's `.the-loop/config.yaml`, emitting a one-time
deprecation warning pointing at the new location. This keeps existing checkouts working
during migration.

## Consequences

- One webhook receiver configured once per machine serves every repo it routes to,
  instead of duplicating (and drifting) the same block across each repo's plugin config.
- The webhook secret env name and routing policy are no longer committed into every
  consuming repo.
- New surface area: a second schema (`cli-config.schema.json`), a template
  (`templates/cli-config.yaml`), and a config-resolution module (`the_loop.config`).
- A small, bounded migration path: the legacy-location fallback is deprecated and can be
  dropped in a future major version.

## Alternatives considered

- **Keep one file, namespace CLI keys under a `cli:` block** — rejected: the CLI is
  repo-independent, so its config should not live inside a repo at all; a shared block
  still ships the CLI's cross-repo settings into every repo.
- **Put the CLI config next to the CLI package (in-repo, e.g. `cli/the-loop.toml`)** —
  rejected: still repo-tied and not discoverable when the CLI runs outside a checkout.
- **A brand-new top-level dir for the CLI config schema** — rejected: keeping both
  schemas under `.the-loop/` (the versioned, shipped location) keeps discovery and
  `/upgrade-the-loop` reconciliation simple.
