# Decision 001: Ship the-loop as a Claude plugin installable from GitHub

- **Status:** accepted
- **Date:** 2026-06-27
- **Deciders:** @MadaraUchiha-314 (via issue #1)
- **Work item:** issue-1

## Context

Every persona in the PDLC (PM, design, architect, dev, QA) uses an agent harness.
the-loop must reach them where they work. The issue scopes support to Claude and
Cursor, and explicitly rules out publishing to bespoke marketplaces.

## Decision

Distribute the-loop as a Claude Code plugin via a `.claude-plugin/marketplace.json` in
this repo, installable directly from GitHub. Structure follows the Claude plugin
convention: `commands/`, `skills/`, `hooks/`. Cursor support is planned; its
distribution equivalent is a TODO.

## Consequences

- Users install with the native marketplace flow; no external publishing pipeline.
- Commands/skills/hooks are the primary extension surface.
- Cursor parity requires a separate adapter later.

## Alternatives considered

- A standalone CLI — rejected: every persona already lives inside a harness.
- Publishing to a third-party marketplace — rejected by the issue.
