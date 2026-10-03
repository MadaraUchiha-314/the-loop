---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#452"
---

<!-- Authored per the the-loop:writing skill. -->

# Documentation: a work item's terminal record outlives its checkout (issue-452)

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| `docs/capabilities/process-graph.md` | new requirement after issue-396's: an ended ref whose state file is not found is reported from its archive — `archived`, no node findings, `ok` only for `completed`; a found state file wins | issue-452 row added |
| `docs/capabilities/webhook-triggers.md` | new requirement after issue-329's closure bullet: the stamp keeps the terminal record read before the checkout goes, the outcome rule, the session-less read, the cleanup backfill, the poller's `state_reason` | issue-452 row added |
| `docs/capabilities/cli.md` | the `the-loop check` bullet: an archived ref prints `ARCHIVED — <outcome>` | issue-452 row added |

## Documentation

| Document | What changed |
|----------|--------------|
| `docs/cli/commands/check.md` | new section *An archived work item*: example output, the outcome vocabulary, the unavailable detail, exit codes, when the archive is and is not consulted, the JSON shape |
| `docs/cli/commands/graph.md` | `status` prints the same archive when the ref has ended |
| `docs/cli/state.md` | the `ended` table gains `outcome` and `terminal`; `cleanup` backfills; `check` answers from it |
| `docs/api-specs/openapi/the-loop.v1.yaml` | `graphCheck` description: the archived answer (the served docstring in `api/routes.py` says the same; the surface is unchanged) |
| `cli/the_loop/api/mcp.py` (`check_work_item`) | tool description: how an agent reads a report carrying `archived` |
| `cli/the_loop/eventlog.py` | the `work_item.ended` catalog entry names its new `outcome` field |
| `README.md`, the skill (`skills/the-loop/`) | no change: neither describes what `check` prints for a closed work item; the behaviour is documented on the command's page |
