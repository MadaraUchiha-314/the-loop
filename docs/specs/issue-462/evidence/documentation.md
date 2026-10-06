---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#462"
---

# Documentation: CI monitoring and self-healing (issue-462)

## Capability docs

- **[`docs/capabilities/webhook-triggers.md`](../../../capabilities/webhook-triggers.md)**
  gains the CI gate's EARS criteria: which CI events are delivered, the CI section, the
  attempt budget and its reset, the drop reasons, and the `autofix: false` escape hatch;
  and the poller's CI read (`polling.ci`, the `ciSeen` ledger, `ci_forwarded`).
  It also gains a history row.
- **[`docs/capabilities/cli.md`](../../../capabilities/cli.md)** gains the `pr checks`
  criteria (entries, `--failing`, log tails, the bounds, `logError`), plus a history row
  that also notes `startup_failure` now counts as failing.
- **[`docs/capabilities/control-plane.md`](../../../capabilities/control-plane.md)**
  names `GET /pull-requests/checks` (`listPullRequestChecks`) and the MCP tool
  `pull_request_checks`, plus a history row.

## Documentation

- **CLI reference:** `docs/cli/commands/pr.md` gains a `pr checks` section (fields,
  flags, bounds, the untrusted-log warning) and the usage line, and its `pr status`
  table gains `startup_failure`. `docs/cli/commands/index.md` lists `checks` on the `pr`
  row.
- **Configuration reference:** `docs/config/cli/routing-options.md` gains *CI: monitoring
  and self-healing* with `ci.autofix` and `ci.maxAttempts`;
  `docs/config/cli/polling-options.md` gains *CI monitoring* with `ci.enabled` and
  `ci.intervalSeconds` (the poll ingress, added on review). The schema (both copies)
  describes them, and the template `skills/the-loop/templates/cli-config.yaml` shows
  them commented out.
- **API contract:** `docs/api-specs/openapi/the-loop.v1.yaml` gains the route.
- **Skill:** `SKILL.md` gains the *Heal a failing check; never game it* rule and names
  `pr checks` among the GitHub verbs. `reference/workflow.md` gains § Self-healing CI
  (the procedure, the two frames, the never-list). `reference/automation.md`'s verb table
  gains `pr checks`.
- **Slash command:** `/the-loop:work-on` lists `pr … checks`.
- **MCP tool description** (`api/mcp.py`) for `pull_request_checks`.
- **Event catalogue:** `ci.check_failed`, `ci.autofix_exhausted`, the two new
  `dispatch.dropped` reasons, and `poll.cycle`'s `ci_forwarded` in
  `eventlog.EVENT_TYPES`.
- **`README.md`** does not list the `pr` subcommands or the routing keys, so it is
  unchanged. The event prompt template (`webhook-event-prompt.md`) already says
  "diagnose, then fix and push, for failed checks"; the CI section is appended after any
  template, so it is unchanged too.
