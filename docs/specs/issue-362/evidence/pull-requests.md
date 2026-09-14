---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#362"
---

# Pull requests: a DM is a channel like any other

One contributing repository — this one — so one pull request. The change touches no other
repository: the manifest, the channel module, the CLI command, the schema copies and the
docs all live here.

## Pull requests

| PR | Repository | Scope / tasks | Status |
|----|------------|---------------|--------|
| _(recorded on open)_ | `MadaraUchiha-314/the-loop` | Tasks 1–11 — the whole work item: the manifest's four conversation kinds, the kind/finding/probe diagnosis, `read.catchUpSeconds` and the periodic reconcile, `channels status --probe`, and the documentation | open |

## The reviewer briefing

The PR description **is** the R10 briefing, produced from
`skills/the-loop/templates/pr-briefing.md`: TL;DR, where to focus in priority order, a
mermaid map of the three layers, the six key decisions with the trade-off each made, the
security summary, the evidence table with what T9 did **not** prove, an upgrade note for
operators whose Slack app predates this change, and three open questions for the reviewer
(the 900s default, whether an unprobed `D…` should keep its `[!]` line, and the
unanswered spec gates).

## Gate state at the time of opening

The spec chain is `status: in-review`, not `approved`: this session neither answers a
human gate nor sets `status: approved` itself (the skill's approval rule — one gate, one
human reply). The work item is **risk tier 3** — it touches a sensitive path
(`**/*schema*`, via both `cli-config.schema.json` copies) — so the tier's gate is
`human-approves-pr`, and the PR waits for that approval rather than completing
autonomously.
