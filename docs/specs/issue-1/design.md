---
type: design
phase: design
workItem: issue-1
status: approved
approvedBy: ["@MadaraUchiha-314 (issue author intent)"]
overrides: {}
---

# Design: The Loop — bootstrap the-loop

> Phase 2. Derives from `requirements.md`. See `docs/architecture/architecture.md` for
> the living architecture.

## Overview
Ship the-loop as a Claude plugin whose repository simultaneously serves as: (a) the
distributable plugin, and (b) a reference project that has the-loop initialized in it.
Encode every rule from issue #1 as concrete files/contracts, deferring runtime
automation (decision-003).

## Architecture
Five components (detailed in `docs/architecture/architecture.md`):
1. Distribution — `.claude-plugin/{plugin,marketplace}.json`.
2. Project footprint — `.the-loop/` (config + schema + manifest + templates + registries).
3. The loop — the 3-phase spec workflow + phase state machine (decision-004),
   realized as `commands/` + `skills/the-loop` + `hooks/`.
4. Knowledge & feedback — `docs/{architecture,decisions,specs}/`, `learnings/`.
5. Collaboration & ticketing — GitHub/Jira, comments as the paper trail.

## Components & interfaces
- **config.schema.json** — JSON Schema (draft 2020-12); the contract `/init` and
  `/upgrade-the-loop` validate/migrate against. Key sections: `ticketing`,
  `repository`, `workflow`, `tooling`, `reviews`, `personas`, `messaging`.
- **manifest.yaml** — enumerates managed files, templates, per-work-item artifacts and
  knowledge files; the source of truth for init/upgrade reconciliation.
- **Commands** — markdown with front-matter (`description`, `argument-hint`,
  `allowed-tools`): `init`, `work-on`, `upgrade-the-loop`.
- **Skill** — `skills/the-loop/SKILL.md` encodes the operating model.

## Data models
- `.the-loop/config.yaml` ⟷ `config.schema.json`.
- Per-work-item specs in `docs/specs/<id>/` with YAML front-matter carrying `phase`,
  `status`, `approvedBy`, `overrides`.

## Error handling
- `/init` and `/upgrade-the-loop` are idempotent and never clobber user-owned files
  (`managed: false`); they diff and suggest instead.
- Config validation surfaces gaps (empty personas, missing owner) rather than failing
  silently.

## Testing strategy
- Static validation: all JSON parses; both config files validate against the schema.
- Structural validation: the file tree matches `.the-loop/manifest.yaml`.
- Acceptance: each issue #1 section maps to a file/contract or a recorded deferral.

## Trade-offs & decisions
- Plugin vs standalone CLI → plugin (decision-001).
- Manifest + schema for reconciliation (decision-002).
- v0 skeleton, defer automation (decision-003).
- Kiro 3-phase specs with per-phase review (decision-004).
