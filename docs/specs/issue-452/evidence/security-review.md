---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#452"
---

<!-- Authored per the the-loop:writing skill. -->

# Security review: a work item's terminal record outlives its checkout

> The ready-to-ship gate's security item
> ([`reference/security.md`](../../../../skills/the-loop/reference/security.md)), run
> with the-loop's checklist against the branch diff.

## Security review (gate)

### Scope of the diff

| File | Change | Runtime reach |
|---|---|---|
| `archive.py` *(new)* | build, classify, read and shape the terminal record | daemon close path; `check` |
| `graphlink.py` | `terminal_record`, a guarded read | daemon close path, before checkout removal |
| `webhook/dispatcher.py` | read before `close_session`; `outcome` + `terminal` on the stamp; cleanup backfill | the portable record |
| `core/graphs.py` | archived branch of `check` | CLI, `POST /graph/check`, MCP `check_work_item` |
| `commands/graph_cmd.py` | render the archive | the operator's terminal |
| `ghapi.py`, `poller/base.py`, `poller/github.py` | carry `state_reason` | the synthesized close event |

### Checklist

| Item | Result |
|---|---|
| Agent-writable input becoming authority | **No.** The record is a copy of `work-item-state.json`, which a session can edit (issue-109). Nothing reads `ended.terminal` or `ended.outcome` back into routing, a gate, a spawn, a cleanup or the attention surfaces; `check` already reported from the same file. A forged claim changes a report, never a gate (abuse a). |
| Filtering on the way in | Node must exist in the compiled graph; skips through `Runtime.declared_skips` (a forged skip of `phase-selection` or of a non-node is dropped, tested); opt-ins through `Runtime.selected`; a pull request kept only when its ref parses, its URL re-derived from the parsed ref (a forged `https://evil.example/…` is not copied, tested); scalar choices held to a short printable grammar (an escape in `effort`, a 500-char model dropped, tested). |
| Terminal injection through `check` output | Evidence names restricted to `[A-Za-z0-9._-]` path segments, no `..`, symlinks skipped, at most 50 (an `\x1b[31m` name and a spaced name dropped, tested). Every other printed field is filtered as above or is a closure fact from the provider event (as `ended` was before). |
| Foreign checkout | The read sits behind the coupling's existing ownership gate (the checkout's `origin` must be the work item's repository) and containment gate; a foreign checkout yields no record and `unknown`, never `completed` (tested). |
| Fail closed | Every read failure is `None`: the closure is stamped as before plus `unknown`/`cancelled`. A malformed stamp or `terminal` reads as not-ended or `unavailable`. |
| Untracked refs | Unchanged: a close for a ref the-loop never tracked writes nothing (issue-329 abuse case A1, existing test green). |
| `check` purity | Still no network, no subprocess, no write: one JSON read of the operator's own portable file. |
| Size | Bounded: evidence list capped; the record is a handful of short strings. |
| New egress, secrets, scopes, dependencies | None. `state_reason` is a field of the REST document the poller already fetches. |

### Findings

**None.**

### Sign-off

Risk tier 3 (no sensitive path touched), so the autonomous review suffices and the
human gate is the PR approval.
