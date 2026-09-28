---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#429"
---

# Security review: the stop gate blocks on a node the work item never entered

> The ready-to-ship gate's security item, always required regardless of risk tier
> ([`reference/security.md`](../../../../skills/the-loop/reference/security.md)). I ran
> the checklist below against the branch diff, file by file.

## Security review (gate)

### Scope of the diff

| File | Change | Runtime reach |
|---|---|---|
| `hooks/the-loop-gate.py` | `blocking_node` bounds by `pointer`; inconclusive rules | what the Stop hook blocks on |
| `cli/the_loop/graph/runtime.py` | `StatusReport.pointer` | one extra key on a read-only report |
| `cli/the_loop/commands/graph_cmd.py` | `_state_line` names the pointer | CLI text only |
| `cli/the_loop/api/routes.py`, `api/mcp.py`, OpenAPI contract | descriptions | none |
| `cli/tests/*` | tests | none |
| `docs/**`, `skills/the-loop/reference/automation.md` | prose | none |

### Findings

**None blocking.** One accepted residual, recorded below.

### Checklist

- **Trust boundary.** The gate now reads one fact from agent-writable
  `work-item-state.json`: the position.
  - *Forward* tampering gains nothing. The walk starts at the graph's first node, so
    the first unmet node behind the pointer is still the finding. This is pinned by
    `test_a_broken_node_behind_the_pointer_still_blocks` and
    `test_a_pointer_moved_past_an_unmet_node_still_blocks_on_it`.
  - *Backward* tampering lets an agent end turns while later nodes are unmet. Those
    nodes are ones the item has not entered, and entering them takes an `advance`
    that evaluates their gates, or a recorded `force`.
  - **Accepted residual:** the Stop hook is a nudge bounded by an attempt cap, not the
    merge boundary. CI's `check --recompute` reads no pointer and still gates the
    merge.
- **Verdict integrity.** No verdict is computed differently, and the pointer never
  marks a node satisfied.
- **Fail direction.** Every malformed or partial report now resolves to "let the turn
  end". That is the direction issue-109 chose for a missing CLI or unparsable output,
  and it is safe: CI is the backstop.
- **Input handling.** No new input. `pointer` is a string the runtime already loaded
  and already exposed as `currentNode` in non-recompute mode. It is never used as a
  path or passed to a shell: the CLI prints it, and the gate compares it for equality.
- **Secrets / credentials / network / subprocess.** None added. The gate's one
  subprocess (`the-loop check`) is unchanged.
- **Information exposure.** The new key carries a graph node id, which is already public
  in the same report.
- **Sensitive paths.** None touched (`**/*schema*`, `.the-loop/**`,
  `.github/workflows/**`, auth/secret/credential). Tier stays 3.
