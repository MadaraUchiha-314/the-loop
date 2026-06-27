---
type: delivery-plan
workItem: issue-1
status: approved
approvedBy: ["@MadaraUchiha-314 (issue author intent)"]
overrides: {}
---

# Delivery Plan: The Loop — bootstrap the-loop (create itself)

> the-loop uses the-loop. This plan delivers the v0 foundation requested by issue #1.

## Context
[Issue #1](https://github.com/MadaraUchiha-314/the-loop/issues/1) describes the full
vision for the-loop and directs that its first task is to create itself. See
decision-003 for the v0-vs-deferred scoping.

## Collaborators required
| Role | Handle | Needed for |
|------|--------|------------|
| Product owner / approver | @MadaraUchiha-314 | Vision, scope sign-off |
| Engineer (harness) | the-loop | Scaffolding the plugin |

## Approach
Establish the distributable plugin skeleton and the project contracts (config schema,
manifest, templates, commands, skill, docs) that encode every rule in the issue, while
deferring runtime automation to follow-up work items. This keeps the change reviewable
and immediately installable.

## Step-by-step plan
1. Plugin distribution: `plugin.json`, `marketplace.json`.
2. Project footprint: `config.schema.json`, default `config.yaml`, `manifest.yaml`,
   `external-tools.md`, `collaborators.yaml`.
3. Templates: epic, story, bug, delivery-plan, execution-log, decision, learning.
4. Commands: `init`, `work-on`, `upgrade-the-loop`.
5. Skill: `the-loop` operating model. Hook: SessionStart reminder.
6. Knowledge: architecture index, decision log (001–003), learnings (001).
7. Self-referential plan + execution log for issue #1.
8. README rewrite documenting install & usage.
9. Validate JSON/structure; commit; push.

## Checkpoints & self-checks
- [x] All JSON files parse (plugin.json, marketplace.json, config.schema.json, hooks.json).
- [x] Directory structure matches `.the-loop/manifest.yaml`.
- [x] Commands and skill have valid front-matter.

## Risks & open questions
- Exact scope of v0 vs deferred — resolved in decision-003; open to the user reshaping.
- Cursor packaging equivalent — TODO, tracked as future work.

## Definition of done
A reviewable, installable v0 plugin whose structure embodies the issue's rules, with
the scoping decision and learnings recorded, pushed to the feature branch.

## Approvals
Scope reflects the issue author's stated intent. Final approval requested on the PR.
