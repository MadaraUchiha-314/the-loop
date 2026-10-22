---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#517"
---

# Documentation: hand a conversation to the-loop from any surface, at any stage

> The `capability-docs` node's proof. Every row below is updated in PR #518, the PR that
> carries the change.

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [process-graph](../../../capabilities/process-graph.md) | New § Handed-off work items: the `requiresHandoff` flag and its `no-handoff` skip, the `import-handoff` node and hook (check, demote, lock), the pre-unticked checklist and *skipped by handoff*, the landing on `enter`, locks recognised by recorded sha256, symlink containment, and adopting the claude.ai artifact URL | issue-517 |
| [spec-workflow](../../../capabilities/spec-workflow.md) | `/the-loop:handoff` drafts only the settled prefix of the chain; the five starting steps; the furthest artifact is never approved in chat | issue-517 |
| [webhook-triggers](../../../capabilities/webhook-triggers.md) | Arming reads the handoff record once (authorized, non-empty author only); the checkout is made on the record's spec branch; a Jira copy labelled `the-loop-mirror` never arms; the graph context names the handoff and the artifact URL; the new events | issue-517 |
| [cli](../../../capabilities/cli.md) | The `handoff` command (`post`, `show`, `import`, `note`); `ticket create --issue-type --parent` for Jira; the read-only `ticket projects` | issue-517 |

## Documentation

| Document | What changed |
|----------|--------------|
| [`docs/cli/commands/handoff.md`](../../../cli/commands/handoff.md) (new) and the docs-site sidebar | The record format, its keys and parts, and each subcommand |
| [`docs/cli/commands/ticket.md`](../../../cli/commands/ticket.md), [`index.md`](../../../cli/commands/index.md), [`graph.md`](../../../cli/commands/graph.md) | `--issue-type`/`--parent` and `ticket projects`; the command index; *skipped by handoff* in `check` |
| [`docs/cli/state.md`](../../../cli/state.md) | `handoff` (including `lockedSha256`), `handoffDemoted`, `claudeArtifactUrl` |
| [`docs/api-specs/openapi/the-loop.v1.yaml`](../../../api-specs/openapi/the-loop.v1.yaml) | `issueType` and `parent` on `POST /work-items/tickets` |
| [`docs/decisions/decision-150.md`](../../../decisions/decision-150.md) and the index | A handoff pre-fills phase selection rather than bypassing it |
| [`docs/reference/commands.md`](../../../reference/commands.md), [`commands/handoff.md`](../../../../commands/handoff.md) | The `/the-loop:handoff` command |
| [`skills/handoff-to-the-loop/SKILL.md`](../../../../skills/handoff-to-the-loop/SKILL.md) (new) | The skill: drafting, the interview, confirmation, posting order, refusal in a daemon session |
| [`skills/the-loop/SKILL.md`](../../../../skills/the-loop/SKILL.md), [`reference/workflow.md`](../../../../skills/the-loop/reference/workflow.md), [`reference/observability.md`](../../../../skills/the-loop/reference/observability.md) | The operating model points to the handoff; how a handed-off item is worked; the new events |
