---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#465"
---

# Documentation: `the-loop pr ready` (issue-465)

## Capability docs

- **[`docs/capabilities/cli.md`](../../../capabilities/cli.md)** gains the `pr ready`
  EARS criteria (ready an open draft; a ready PR is a no-op; a closed or merged one is
  refused) and adds it to the lifecycle acts the registered-work-item rule covers. It
  also gains a history row.
- **[`docs/capabilities/control-plane.md`](../../../capabilities/control-plane.md)**
  names `POST /pull-requests/ready` (`markPullRequestReady`) and the MCP tool
  `mark_pull_request_ready`. It also gains a history row.

## Documentation

- **CLI reference:** `docs/cli/commands/pr.md` gains a `pr ready` section, the usage
  line, a pointer from `pr create --draft`, and `ready` in the registered-work-item
  rule. `docs/cli/commands/index.md` lists `ready` on the `pr` row.
- **API contract:** `docs/api-specs/openapi/the-loop.v1.yaml` gains the route and
  `PullRequestReadyBody`.
- **Skill:** `SKILL.md` § Interacting with other tools and `reference/automation.md`
  § Reaching GitHub name `the-loop pr ready` and say to run it on a draft before asking
  for human review. The registered-work-item bullet adds "readying".
- **Slash command:** `/the-loop:work-on` lists `pr … ready` among the verbs.
- **MCP tool description** (`api/mcp.py`) for `mark_pull_request_ready`.
- **Event catalogue:** `work_item.pr_ready` added to `eventlog.EVENT_TYPES`.
- **`README.md`** does not list the `pr` subcommands, so it is unchanged.
