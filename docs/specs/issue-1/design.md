---
type: design
phase: design
workItem: issue-1
status: approved
approvedBy: ["@MadaraUchiha-314 (issue author intent)"]
overrides: {}
---

# Design: the-loop (create itself)

> Phase 2. Derives from `requirements.md` (which distills issue #1). See
> `docs/architecture/architecture.md` for the living architecture and the `the-loop`
> skill's `reference/` files for the full operating detail.

## Overview

Ship the-loop as a Claude plugin whose repository simultaneously is (a) the
distributable plugin and (b) a reference project that has the-loop initialized in it.
Encode every rule from issue #1 as concrete, validated files/contracts, realize the
behaviour as commands + a skill (with reference docs) + hooks, and defer runtime
automation to follow-up work items (`decision-003`).

## Architecture

Six components. Each requirement maps to one or more.

| Component | Realized by | Satisfies |
|-----------|-------------|-----------|
| Distribution | `.claude-plugin/{plugin,marketplace}.json` | R7 |
| Project footprint | `.the-loop/` (config, schema, manifest, templates, registries) | R1, R2, R3, R5, R7 |
| The loop (behaviour) | `commands/`, `skills/the-loop/` (+ `reference/`), `hooks/` | R4, and operationalizes R1–R6 |
| Knowledge & feedback | `docs/{architecture,decisions,specs}/`, `learnings/` | R4, R6 |
| Collaboration & ticketing | GitHub/Jira; comments as paper trail; `collaborators.yaml`, `messaging` | R1, R5 |
| CLI companion | `cli/` Python package `the_loop` (`gh-webhook` receiver) | R9, R8 (receiver) |
| Automation (future) | remote exec, DAG orchestration, event→harness routing | R8 [deferred] |

## Components & interfaces

### Config & schema (R2/R3/R5/R7)

- `config.schema.json` (JSON Schema draft 2020-12) is the contract. Sections:
  `ticketing`, `repository`, `workflow`, `tooling`, `localOrchestration`, `hooks`,
  `observability`, `reviews`, `personas`, `messaging`, `externalTools`.
- `config.yaml` is validated against it; a subset of keys is overridable per work item
  via spec front-matter `overrides`.

### Manifest (R7)

- `manifest.yaml` enumerates managed meta files, templates, per-work-item artifacts and
  knowledge files — the single source of truth `init` and `upgrade-the-loop` reconcile
  against.

### Commands (R4/R7)

- `init` — detect project, scaffold footprint + docs, create phase labels, wire local
  hooks/CI parity, validate config.
- `work-on` — drive the 3-phase loop (requirements → design → tasks → implement →
  review → complete), keeping phase labels in sync; resumable per phase.
- `upgrade-the-loop` — reconcile files and migrate the schema across versions.

### Skill + reference (R2–R6)

- `skills/the-loop/SKILL.md` is the operating manual; `reference/{workflow,tooling,
  collaboration,observability,automation-and-roadmap}.md` carry the full detail so the
  essence of issue #1 is preserved for the harness at runtime.

### Hooks (predictability)

- `hooks/hooks.json` ships a SessionStart reminder in v0; the predictability mechanism
  (hooks vs custom code/scripts) for forcing PDLC steps is an open question — the CLI is
  a natural home for scripted guarantees.

### CLI companion (R9)

- `cli/` is a Python package `the_loop` with the `the-loop` entry point and an
  extensible command registry (`Command` + `@register`). Core is stdlib-only.
- `gh-webhook start|stop` runs a threaded `http.server` receiver that HMAC-verifies
  GitHub deliveries (secret from env), serves `GET /health`, logs events, and exposes an
  `on_event` seam for future harness routing. Config: `webhooks.ghWebhook`.

## Data models

- `.the-loop/config.yaml` ⟷ `config.schema.json`.
- Per-work-item specs in `docs/specs/<id>/` with front-matter (`phase`, `status`,
  `approvedBy`, `collaborators`, `overrides`).
- Phase state machine: 7 phases ⟷ ticket labels `<phaseLabelPrefix><phase>`.

## Error handling

- `init`/`upgrade-the-loop` are idempotent and never clobber user-owned files
  (`managed: false`) — they diff and suggest.
- Config validation surfaces gaps (empty personas, missing owner) rather than failing
  silently.
- Missing ticket → refuse to proceed (R1).

## Testing strategy

- Static: all JSON parses; both configs validate against the schema.
- Structural: the file tree matches `manifest.yaml`.
- Acceptance: every requirement maps to a delivered file/contract **[v0]** or a recorded
  deferral **[deferred]**; evidence recorded in `execution-log.md`.

## Trade-offs & decisions

- Plugin vs standalone CLI → plugin (`decision-001`).
- Manifest + schema for reconciliation (`decision-002`).
- v0 skeleton, defer automation (`decision-003`).
- Kiro 3-phase specs with per-phase review (`decision-004`).
