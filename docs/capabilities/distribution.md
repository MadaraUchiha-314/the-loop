# Capability: distribution

> Shipping the-loop as an installable plugin for **Claude Code and Cursor**, and its
> control-plane service as a container image, from a single repository — no bespoke
> marketplace publishing.

## What it is

The packaging that makes the-loop installable in both harnesses: two thin plugin
manifests over one shared set of skills, commands and templates. The templates **and the
config schemas** are **internal** to the plugin — read from it when authoring artifacts or
validating a config, never copied into the projects the-loop is run on.

## Current behaviour

- the-loop SHALL be installable in Claude Code directly from GitHub
  (`/plugin marketplace add MadaraUchiha-314/the-loop` +
  `/plugin install the-loop@the-loop`) via `.claude-plugin/plugin.json` +
  `marketplace.json`.
- the-loop SHALL be installable in Cursor (≥ 2.5) from the same repo via
  `.cursor-plugin/plugin.json` + `marketplace.json`, or by cloning under
  `~/.cursor/plugins/local/`.
- The **Claude Code** plugin SHALL also be installable **non-interactively from a
  terminal** with `the-loop install claude [--scope user|project]` (and moved forward with
  `the-loop upgrade`), which drives `claude`'s own plugin CLI where it has one and
  otherwise falls back to the settings keys above. The **Cursor** plugin SHALL keep its
  documented in-editor routes until issue-157 establishes a terminal one — the CLI reports
  `cursor` as an unknown component rather than half-supporting it (owner decision on
  PR #153). See [cli](cli.md) and [decision-057](../decisions/decision-057.md); the
  in-session `/plugin` and `/add-plugin` routes remain exactly as documented.
- Both plugins SHALL reuse the SAME `skills/` (Agent Skills standard) and `commands/`;
  nothing is forked per harness.
- Plugin and marketplace manifest `version` fields SHALL carry the released version:
  `cz bump` rewrites them in lockstep on every release (see
  [release-publishing](release-publishing.md), decision-028).
- WHERE Claude Code uses the SessionStart hook (`hooks/hooks.json`) the Cursor package
  SHALL use the always-applied rule `rules/the-loop.mdc` instead.
- Work-item and process templates SHALL be internal to the plugin, shipped under
  `skills/the-loop/templates/` (`manifest.templatesDir`) and read from
  `${CLAUDE_PLUGIN_ROOT}` when an artifact is authored. `/the-loop:init` SHALL NOT copy
  them into a project; a project carries only its own generated artifacts.
- WHEN `/the-loop:upgrade-the-loop` runs on a project that an older version scaffolded a
  `.the-loop/templates/` folder into THEN it SHALL remove that folder (per
  `manifest.deprecated`), confirming first only if the user has added their own files
  under it.
- **Config schemas SHALL be internal to the plugin too** (issue-220,
  [decision-080](../decisions/decision-080.md)), shipped under
  `${CLAUDE_PLUGIN_ROOT}/.the-loop/` and declared once as `manifest.schemasDir` — the same
  shape `templatesDir` has. `/the-loop:init` SHALL NOT create
  `harness-config.schema.json`, `collaborators.schema.json` or `cli-config.schema.json` in
  a project, and the opt-in `.the-loop/cli-config.yaml` SHALL be scaffolded alone.
- WHEN init or upgrade validates a config, or drives the `x-onboarding` walkthrough, THEN
  it SHALL read the schema from `manifest.schemasDir` **on disk** — the absence of a
  project-local copy SHALL NOT weaken, skip, or move that validation onto the network.
- WHEN `/the-loop:upgrade-the-loop` runs on a project holding a schema copy an older
  version left behind THEN it SHALL delete it and report it under **removed
  (deprecated)**; WHERE that copy differs from the plugin's shipped schema the difference
  SHALL be surfaced first, and WHERE the file cannot be established as a the-loop copy it
  SHALL be left in place and reported under **needs-user**. Deletion is name-driven from
  `manifest.deprecated`; a path resolving outside the project's `.the-loop/` SHALL be
  refused.
- Every config the-loop scaffolds SHALL open, on its **first line**, with a
  `# yaml-language-server: $schema=<published url>` modeline, so an operator's editor
  validates the file with no local schema. It is a comment: the loop SHALL never read it,
  and SHALL never fetch a schema over the network.
- WHEN `/the-loop:init` scaffolds `.the-loop/harness-config.yaml` THEN it SHALL establish the
  config with the user via a guided onboarding driven by the schema's `x-onboarding`
  groups: related keys clubbed and decided together, each group explained, enum keys
  presented with ALL possibilities, free-form keys with schema `examples`, and
  sensible defaults resolved as existing answer → detected signal → schema default
  (see the skill's `reference/onboarding.md`).
- WHERE `--defaults` is passed init SHALL apply sensible defaults without interaction
  and report the remaining gaps under **needs-user**; WHEN init re-runs it SHALL
  raise only gaps, never re-asking established answers.
- WHEN `/the-loop:upgrade-the-loop` finds a removed schema key that still carries live
  operational settings (not just a stale default) THEN it SHALL migrate the data, not
  merely flag and drop it — e.g. a pre-decision-032 `.the-loop/harness-config.yaml` still
  carrying `webhooks`/`polling`/`observability.eventLog` SHALL have that block
  extracted, `eventLog`-renamed, and written to a CLI config (asking the same yes/no
  location question `/init` asks), both resulting files validated, and the migration
  reported as its own line — never silently dropped.
- WHEN a release adds a config key whose **default changes runtime behaviour** THEN
  upgrade SHALL surface it under **needs-user** rather than adding it silently — the
  add-with-defaults rule covers opt-in keys, not behaviour flips. The first instance is
  `routing.control.requireStartCommand` (issue-106): its default demotes the
  auto-execute label to *necessary but not sufficient*, so upgrade asks whether to keep
  the previous behaviour (`false`) or adopt the gate (`true`). Related state moves are
  offered, never performed silently: an older state layout (`.the-loop/poll-state.json`,
  then `<state.root>/sessions/`) may be tidied away, but the daemon keeps READING what is
  there until each work item has been written forward, because an empty ledger would
  re-forward every watched thread (issue-106, issue-128).
- The **control-plane service** SHALL also ship as a container image at
  `ghcr.io/madarauchiha-314/the-loop` (issue-236), published by the release workflow
  beside the PyPI distribution and gated on the same "a release happened" output, so an
  image tag and a PyPI version are always the same commit. It SHALL be built for
  `linux/amd64` and `linux/arm64`, tagged `latest`/`<major>`/`<major>.<minor>`/`<version>`,
  labelled with its OCI source and version, and accompanied by a build-provenance
  attestation pushed to the registry.
- The image SHALL host the **control plane and nothing else**: the API, its `/mcp`
  endpoint and the config surface, with no harness binary, `tmux` or `git` — so it drives
  no agent sessions. It SHALL run as a non-root user and SHALL open no ingress on its own:
  the receiver, the poller and standing sessions stay the opt-ins `the-loop start`
  already makes them.
- WHEN the container starts and its configured CLI config does not exist THEN the
  entrypoint SHALL seed it from the image's container defaults and say so; IF the file
  exists THEN it SHALL be left byte-identical, so an operator's edits — and the
  dashboard's writes — survive a restart and an image upgrade.
- The container's default config SHALL be a **checked-in, schema-validated file** whose
  only opinions are the state root (inside the `/data` volume) and the bind: everything
  else inherits the package default. Because a loopback bind inside a container's network
  namespace is reachable by nothing, it SHALL set `service.host: 0.0.0.0` with
  `service.exposed: true` — clearing the exposure guard **in configuration the operator
  can read and change**, never in code — and the entrypoint SHALL state on **every** start
  that the published port is now the boundary
  ([decision-102](../decisions/decision-102.md)).
- A CLI config that lives in the operator's **home directory** is outside upgrade's
  reach (it reconciles project files). Upgrade SHALL say so and print what to paste,
  and the runtime SHALL stay correct for an un-migrated config — every key added this
  way is optional and falls back to the same defaults.

## Design

[`docs/specs/issue-12/design.md`](../specs/issue-12/design.md) ·
[architecture § distribution](../architecture/architecture.md)

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-236 | The control-plane service ships as a container image on GHCR: a two-stage `Containerfile`, a seeded-once container config that moves the network boundary to the publish flag, a CI build-and-run gate on every pull request, and a `publish-container` release job with multi-arch build and provenance | [spec](../specs/issue-236/), [decision-102](../decisions/decision-102.md), [container](../cli/container.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/236) |
| issue-220 | Config schemas made internal to the plugin (`manifest.schemasDir`); init stops copying up to 118 KB of them into each project, upgrade deletes the copies already there, and scaffolded configs carry a `# yaml-language-server: $schema=` modeline instead | [spec](../specs/issue-220/), [decision-080](../decisions/decision-080.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/220) |
| issue-152 | The **Claude Code** plugin became installable and upgradable from the CLI (`the-loop install` / `upgrade`), at user or project scope, without opening a session — the terminal-side counterpart to the marketplace routes. Cursor stays in-editor-only, split out as issue-157 | [spec](../specs/issue-152/), [decision-057](../decisions/decision-057.md), [cli](cli.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/152) |
| issue-106 | A key whose default changes behaviour (`routing.control.requireStartCommand`) is reported as **needs-user**, not silently added; the `state`/`control` blocks are added with defaults and the poll-state move is offered, not forced | [spec](../specs/issue-106/), [decision-040](../decisions/decision-040.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/106) |
| issue-63 | `/upgrade` migrates (not just flags) removed schema keys with live data — the `webhooks`/`polling`/`observability.eventLog` → CLI config extraction | [spec](../specs/issue-63/), [decision-032](../decisions/decision-032.md) |
| issue-46 | Plugin/marketplace manifest versions bumped by the release engine (were frozen at 0.1.0) | [spec](../specs/issue-46/), [decision-028](../decisions/decision-028.md) |
| issue-49 | Guided, schema-driven config onboarding in `/init` (x-onboarding groups, ask levels, `--defaults` mode, examples on gap-prone keys) | [spec](../specs/issue-49/), [decision-024](../decisions/decision-024.md) |
| issue-36 | Templates made internal to the plugin (`skills/the-loop/templates/`); init no longer copies them into projects, and upgrade cleans up the deprecated `.the-loop/templates/` folder | [spec](../specs/issue-36/) |
| issue-12 | Added Cursor packaging (`.cursor-plugin/`, `rules/the-loop.mdc`) reusing the same skills/commands | [spec](../specs/issue-12/), [decision-015](../decisions/decision-015.md) |
| issue-1 | Shipped the Claude Code plugin + marketplace manifests (v0) | [spec](../specs/issue-1/), [decision-001](../decisions/decision-001.md) |
