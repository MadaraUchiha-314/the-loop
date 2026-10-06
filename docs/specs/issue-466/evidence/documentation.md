---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#466"
---

# Documentation: arming a linked pull request (issue-466)

## Capability docs

- **[`docs/capabilities/cli.md`](../../../capabilities/cli.md)** gains an EARS
  requirement under `sessions … link-pr`: recording a PR puts every
  `routing.autoExecuteLabels` label on it. It also gains a history row.
- **[`docs/capabilities/webhook-triggers.md`](../../../capabilities/webhook-triggers.md)**:
  the "session that opens a pull request records it" requirement now says the record
  also arms the PR. It also gains a history row.

## Documentation

- **CLI reference:** `docs/cli/commands/sessions.md` (`link-pr`) and
  `docs/cli/commands/pr.md` (`pr create`) say when labels are applied, when they are
  not, and what the note means.
- **Skill:** `skills/the-loop/reference/automation.md` replaces "adds the label" and
  "Every one of them is labelled" with every configured label, applied by the verb.
  The `templates/evidence/pull-requests.md` template says the same.
- **Slash commands:** `/the-loop:work-on` and `/the-loop:execute-tasks` drop "label every
  PR" as a manual step. The agent adds labels by hand only on a `note:`.
  `execute-tasks` also stops pointing at the retired execution log (issue-365).
- **MCP tool descriptions** (`api/mcp.py`) for `link_pull_request` and
  `create_pull_request` mention the labels.
- **Event catalogue:** `work_item.pr_labelled` added to `eventlog.EVENT_TYPES`.
- **`README.md`** says nothing about PR labelling, so it is unchanged.
