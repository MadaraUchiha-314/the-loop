# Decision 003: Bootstrap a v0 skeleton first, defer runtime automation

- **Status:** accepted
- **Date:** 2026-06-27
- **Deciders:** @MadaraUchiha-314 (via issue #1), the-loop (self)
- **Work item:** issue-1

## Context

Issue #1 is a broad vision spanning ticketing, tooling, multi-party collaboration, the
execution loop, docs/decisions/learnings, self-improvement, distribution, webhooks and
remote execution. It cannot be delivered in a single pass, and the repo starts empty.
The issue's final directive: "the-loop's first task is to create itself."

## Decision

Deliver a coherent **v0 foundation** that establishes the structure and contracts of
the-loop, and defer runtime automation to follow-up work items:
- **In v0:** plugin + marketplace manifests; config schema + default config; manifest;
  epic/story/bug + plan/log/decision/learning templates; `init` / `work-on` /
  `upgrade-the-loop` commands; the `the-loop` skill; a SessionStart hook;
  docs (architecture, decisions), learnings, and the self-referential delivery
  plan + execution log for issue #1.
- **Deferred (future issues):** webhook triggers (PR comments, Actions),
  remote-workspace execution, DAG orchestration across work items, concrete
  language-specific tooling integrations (uv/bun/nx/pytest/vitest/playwright/oxlint/
  ruff/pyright), messaging integrations, and Cursor packaging.

## Consequences

- The user gets a reviewable, installable skeleton quickly, embodying every rule from
  the issue as documented structure.
- Each deferred capability becomes its own work item delivered through the-loop itself.

## Alternatives considered

- Attempt the whole vision at once — rejected: not deliverable or reviewable.
- Build only docs — rejected: leaves nothing installable/usable.
