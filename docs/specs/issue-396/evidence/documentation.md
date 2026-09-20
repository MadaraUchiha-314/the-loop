---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#396"
---

# Documentation: `graph status` reads the state file the runtime wrote (issue-396)

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| `docs/capabilities/process-graph.md` | § State, recovery and the escape hatch gains the requirement: every check report names its state file (`statePath`/`stateFound`, the CLI's `state:` line), every graph verb accepts a ref, and the read verbs resolve the session's checkout through the registry with a `repo:` note; the issue-238 no-path answer is unchanged | issue-396 row added |
| `docs/capabilities/cli.md` | the `the-loop check` bullet: id or ref, the state line, the registry resolution | issue-396 row added |

## Documentation

| Document | What changed |
|----------|--------------|
| `README.md` | the quick-reference line: `graph status <id\|ref>`, and that the command says which `work-item-state.json` answered |
| `docs/cli/commands/graph.md` | the synopsis (`--repo DIR`, unset resolves), the id-or-ref rule for every verb, and a `status` section showing the `repo:` / `state:` lines and when each appears; read verbs only |
| `docs/cli/commands/check.md` | synopsis and flags table (positional accepts a ref; `--repo` unset means resolve), the example output with its `state:` line, the not-found wording, `--all` prints none, JSON carries the two fields |
| `docs/api-specs/openapi/the-loop.v1.yaml` | `graphCheck` description: `workItem` as id or ref; `statePath`/`stateFound` on every resolving answer (the served schema's docstring in `api/routes.py` says the same; the surface is unchanged) |
| `cli/the_loop/api/mcp.py` (`check_work_item`) | tool description: id or ref, and what `stateFound: false` means for an agent reading the report |
| `docs/reports/e2e-slack-test-2026-09-19.md`, `docs/reports/followups/README.md`, `docs/reports/followups/b7-graph-status-stale-node.md` | B7 and O6 link the filed issue and record the root cause and the fix that landed |
| operating-model skill (`skills/the-loop/`) | no change: the skill names `the-loop graph status <id>` by id, which keeps working; the ref form is a CLI convenience documented on the command's page |
