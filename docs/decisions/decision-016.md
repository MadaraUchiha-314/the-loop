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

- **MCP notifications don't solve webhook delivery.** The MCP spec *does* define
  notifications (`resources/subscribe` → `notifications/resources/updated`,
  `listChanged`), but three gaps remain for this use case:
  1. Notifications flow only over an **established client↔server session** — a server
     cannot wake a harness that isn't connected, and an idle harness client doesn't turn
     unsolicited notifications into agent turns today (the well-known MCP client
     capability gap).
  2. The official `github/github-mcp-server` exposes request/response tools only; it
     declares no resource-subscription/event surface for PR/issue activity.
  3. Even with both in place, GitHub still delivers events by **webhook** (or polling) —
     an event-pushing MCP server would need its own webhook receiver; the receiver
     doesn't disappear, it moves. Claude.ai/code's `subscribe_pr_activity` is exactly
     that: Anthropic-hosted webhook infrastructure, unavailable to locally-run harnesses
     — which are issue #15's target.
- **CLIs are the shared official programmatic surface.** Cursor's official SDK is
  TypeScript-only (`@cursor/sdk`) — driving it from a Python CLI would require a Node
  sidecar process. Claude's Python Agent SDK (`claude-agent-sdk`) carries runtime
  dependencies (`anyio`, `mcp`, `sniffio`) and itself drives the bundled `claude` CLI
  over stdio — a per-event `resume` through it costs what a per-event CLI invocation
  costs. Subprocessing the vendor CLIs keeps the zero-runtime-dependency guarantee
  (decision-005) and treats both harnesses uniformly.
- **CLI-only for both harnesses (owner decision, PR #16).** An optional
  `claude-agent-sdk` adapter was considered and set aside: the extra control it adds
  (interrupting an in-flight run, message-level trace/hooks, streaming input) is not
  needed for v1, and the `HarnessAdapter` contract keeps SDK implementations possible
  later without redesign. Event *queueing* lives in the-loop's dispatcher either way;
  no SDK provides it.
- **Resume, don't respawn.** Routing to an *existing* session preserves its context —
  the point of linking events to sessions via registry metadata.

## Consequences

- New CLI surface: `the-loop sessions register|list|close`; new config
  `webhooks.ghWebhook.routing`; registry files under `.the-loop/sessions/`
  (git-ignored).
- GitHub redelivery is the retry mechanism (at-most-once local dispatch, delivery-id
  dedup).
- **Re-evaluation trigger:** if the GitHub MCP server ships event
  subscriptions (resource subscriptions or a push surface for PR/issue activity) AND
  harness clients start acting on unsolicited MCP notifications (waking idle sessions),
  revisit — the router/registry/adapters remain; only the receiving edge would change.
  Tracked context: modelcontextprotocol discussion #523 (webhooks for operations).
