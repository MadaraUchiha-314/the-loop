---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#453"
---

<!-- Authored per the the-loop:writing skill. -->

# Security review: a parked work item is owned by the instance that accepted it

> The ready-to-ship gate's security item
> ([`reference/security.md`](../../../../skills/the-loop/reference/security.md)), run
> with the-loop's checklist against the branch diff. Tier 3: the autonomous review
> suffices; nothing here needs a security decision.

## Scope of the diff

| File | Change | Runtime reach |
|---|---|---|
| `core/github_ops.py` | `_accepted_here`; one clause in `_authority`; `_cancel_pending_start` in `close_ticket` | whether a lifecycle verb acts, and one control record written after a close |
| `api/mcp.py` | the `close_ticket` tool's docstring | text only |

## Checklist

| Item | Result |
|---|---|
| A new way to act on a ref the instance does not track | **No.** The new source needs a control record for the target in this instance's own state directory, stamped with this instance's name as the config declares it, for an item not stamped `ended`. An unrelated ref, another instance's record, an unnamed record on a named instance (and the reverse) and an ended item are all refused with nothing sent (tested, unit and integration). |
| A record naming itself in | **No.** The reference name is the config's; the record's field is only compared (decision-141 D5). |
| Authority over pull requests | **Unchanged.** The clause reads the target's own record; the live-session scan over recorded pull requests is as before. A parked `--work-item` cannot merge a stranger PR (tested). |
| Closure becoming a launch | **No.** The only write is `ControlStore.record(stop)`, the record the spawn gate already reads as *not armed*; a labelled event and a `control-start` after the close spawn nothing through the real dispatcher (tested). |
| Fail closed | Every exception in the guard resolves to "not owned"; a failed record write after the close is reported, never hidden. |
| Untrusted text reaching an argv, a request or a comment | None added. Nothing from GitHub is read by the guard; the close request is the existing `close_issue`. |
| New egress, secrets, dependencies, files | None. |

## Findings

**None.**
