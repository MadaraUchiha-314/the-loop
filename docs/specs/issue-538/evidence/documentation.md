---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#538"
---

# Documentation: tell the work item's session what happens to its pull-request sessions

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| `docs/capabilities/process-graph.md` | New requirement beside the inner-loop rules: one notice per endpoint transition into the work item's session, and the daemon-side re-run of a parked `await-inner-loops` node when an inner loop finishes; the one-way rule restated | issue-538 |
| `docs/capabilities/webhook-triggers.md` | New requirement: which transitions are reported, that a declined or failed spawn's notice rides ahead of the event in one paste, and the skip and failure behaviour | issue-538 |

## Documentation

| Document | What changed |
|----------|--------------|
| `skills/the-loop/reference/workflow.md` | § Several repositories: the session is told when its pull requests' sessions change and the waiting gate is re-run, so there is no need to poll; what a `closed` notice asks of it |
| `docs/config/cli/routing-options.md` | `sessionPerPr`: a decline's event now arrives behind a notice; every mode's notices, and `session.pr_notice_*` in `the-loop events` |

`README.md` is unchanged: its two `await-inner-loops` sentences describe the gate holding
until inner loops finish, which is still true. `skills/the-loop/SKILL.md` is unchanged: its
multi-repository bullet points to `reference/workflow.md`, which carries the new paragraph.
