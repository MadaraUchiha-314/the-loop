---
type: evidence
workItem: "issue-543"
---

<!-- Written per the `the-loop:writing` skill. -->

# Documentation: PR-scoped specs for multi-PR work items

## The short version

Two capability docs gain the PR-spec behaviour and a history row each. The skill, the
workflow reference, the commands reference, the graph CLI page and decision-153 describe
the verb and the gate as built, including the rules the reviews tightened.

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [process-graph](../../../capabilities/process-graph.md) | The inner loop starts at `pr-spec`, its only skippable node. `pr-spec-current` gates three exits. The verb and its API route are described. A `spec-only` record older than the inner `implementation` run blocks. | issue-543 |
| [spec-workflow](../../../capabilities/spec-workflow.md) | Each delivery PR of a multi-PR work item carries a PR spec: derived, cited and without `status`. The order is commit, record, then push. `pr-spec still-valid` and `allow-disclosure` count only as a line of their own. | issue-543 |

## Documentation

| Document | What changed |
|----------|--------------|
| [`skills/the-loop/SKILL.md`](../../../../skills/the-loop/SKILL.md) | The PR-spec rule, and `/the-loop:derive-pr-spec` added to the command list. |
| [`skills/the-loop/reference/workflow.md`](../../../../skills/the-loop/reference/workflow.md) | New § PR specs: when one is needed, the path, citing, recording, stale and `--still-valid`, disclosure, and feedback routing. |
| [`commands/derive-pr-spec.md`](../../../../commands/derive-pr-spec.md) | New slash command, the `pr-spec` node's instructions. |
| [`skills/the-loop/templates/pr-spec/`](../../../../skills/the-loop/templates/pr-spec/) | Four new templates, each with the Context section first. |
| [`skills/the-loop/templates/pr-briefing.md`](../../../../skills/the-loop/templates/pr-briefing.md) | A first-card line linking the PR's own spec. |
| [`docs/cli/commands/graph.md`](../../../cli/commands/graph.md) | New `## pr-spec` section: flags, exit codes and checks. |
| [`docs/reference/commands.md`](../../../reference/commands.md) | `derive-pr-spec` listed. |
| [`docs/api-specs/openapi/the-loop.v1.yaml`](../../../api-specs/openapi/the-loop.v1.yaml) | `POST /api/v1/graph/pr-spec` and `GraphPrSpecBody`. |
| [`docs/decisions/decision-153.md`](../../../decisions/decision-153.md) | The decision, and an entry in `decisions.md`. |
