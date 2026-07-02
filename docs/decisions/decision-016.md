# Decision 016 — Route GitHub webhooks to harness sessions via the CLI receiver, not GitHub MCP

- **Status:** proposed (accepted when the issue-15 spec is approved)
- **Date:** 2026-07-02
- **Work item:** issue #15
- **Spec:** `docs/specs/issue-15/`

## Context

Issue #15 wants GitHub events (PR comments, CI results) to wake the right locally-run
Claude Code / Cursor session, the way Claude.ai/code does for hosted sessions. Two
approaches were named, with GitHub MCP event subscription preferred if it exists.

## Decision

Use the **webhook receiver + programmatic trigger** approach: the existing
`the-loop gh-webhook` receiver gains a router, a session registry
(`work item ↔ harness session id ↔ cwd`) and per-harness adapters that resume sessions
through the official CLIs (`claude -p --resume`, `cursor-agent -p --resume`) as
subprocesses.

## Rationale

- **GitHub MCP cannot subscribe to events today.** MCP transports (stdio, streamable
  HTTP) are client-initiated; the official `github/github-mcp-server` exposes
  request/response tools only. Claude.ai/code's `subscribe_pr_activity` is
  Anthropic-hosted webhook infrastructure, unavailable to locally-run harnesses — which
  are exactly issue #15's target.
- **CLIs are the shared official programmatic surface.** Cursor's official SDK is
  TypeScript-only (`@cursor/sdk`); Claude's Python Agent SDK exists but would be the
  CLI's first runtime dependency. Subprocessing the vendor CLIs keeps the
  zero-runtime-dependency guarantee (decision-005) and treats both harnesses uniformly;
  SDK adapters can be added later behind the same adapter contract.
- **Resume, don't respawn.** Routing to an *existing* session preserves its context —
  the point of linking events to sessions via registry metadata.

## Consequences

- New CLI surface: `the-loop sessions register|list|close`; new config
  `webhooks.ghWebhook.routing`; registry files under `.the-loop/sessions/`
  (git-ignored).
- GitHub redelivery is the retry mechanism (at-most-once local dispatch, delivery-id
  dedup).
- **Re-evaluation trigger:** if MCP gains a server→client event-push mechanism suitable
  for third-party webhooks (tracked in modelcontextprotocol discussions, e.g. #523) or
  the GitHub MCP server ships subscriptions, revisit — the router/registry/adapters
  remain; only the receiving edge would change.
