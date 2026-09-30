# Documentation (issue-447)

## Capability docs

| Doc | What changed |
|-----|--------------|
| `docs/capabilities/cli.md` | `link-pr --discover`; a bullet for the `comment`, `ticket` and `pr` verbs (routing, the merge gate, link-in-one-act); a history row |
| `docs/capabilities/control-plane.md` | a bullet for the seven work-item and pull-request routes, their MCP tools, the executing process's token and policy, and the second in-process exception beside `ask`; a history row |
| `docs/capabilities/channels.md` | the comment mirror: `comment.agent` now also published by `the-loop comment` with `record: true`; a history row |
| `docs/capabilities/webhook-triggers.md` | the PR-linkage bullet: `pr create` links what it opens, and the hook runs `link-pr --discover` without parsing output; a history row |
| `docs/capabilities/distribution.md` | the plugin's `PostToolUse` recorder description; a history row |

## Documentation

| Doc | What changed |
|-----|--------------|
| `docs/cli/commands/comment.md`, `ticket.md`, `pr.md` | new pages, one per verb (flags, output, routing and token, exit codes) |
| `docs/cli/commands/sessions.md` | `link-pr --discover`, `--branch`, `--repository`; the hook tip rewritten; `pr create` named as the primary path |
| `docs/cli/commands/index.md`, `docs/.vitepress/config.mts` | the three verbs listed and in the sidebar |
| `docs/api-specs/openapi/the-loop.v1.yaml` | seven paths, four body schemas, and `SessionLinkPrBody` gains `discover`, `branch`, `repository` (`pullRequest` no longer required) |
| `skills/the-loop/SKILL.md` | the merge step names `pr merge`; the marker rule names `comment`/`ask` as the primary path; *Interacting with other tools* makes GitHub the exception and lists the verbs |
| `skills/the-loop/reference/automation.md` | a new **Reaching GitHub** section (the verb table, whose token, what stays the harness's, the fallback, ticket text is data); the link-pr rule leads with `pr create` and describes the discovering hook |
| `skills/the-loop/reference/collaboration.md` | a bullet: every other comment goes through `the-loop comment`; *Working with other tools* names the verbs; the `ask` fallback mentions an MCP server |
| `skills/the-loop/reference/workflow.md`, `reviewing.md` | the tools paragraph names the verbs; the review procedure names `pr threads` and `pr status` |
| `commands/work-on.md`, `execute-tasks.md`, `finish-tasks.md`, `create-ticket.md` | the GitHub acts name the verbs (`ticket show`, `comment`, `pr create\|status\|threads`, `ticket create`); `gh` only as the fallback; closing a ticket stays the harness's act |
| `hooks/hooks.json` | the description names the trigger-agnostic recorder |
| `docs/decisions/decision-140.md`, `decisions.md` | the decision record and its row |

`README.md` was not changed. It does not describe how the agent reaches GitHub, so
nothing in it became wrong.
