---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#496"
---

# Pull requests: the-loop gateway — one ingress, many instances

> Authored as pull requests are opened, gated at `reviewer-briefing`. A work item may be
> delivered by **several** PRs; this one is delivered by one, in this repository. Each PR
> is recorded against the work item as it is opened (`the-loop pr create`), which also
> puts every `routing.autoExecuteLabels` label on it (issue-466). The work item is
> complete only once it is merged or closed (`finish-tasks`).

## Pull requests

| PR | Repository | Scope / tasks | Status |
|----|------------|---------------|--------|
| [#499](https://github.com/MadaraUchiha-314/the-loop/pull/499) | MadaraUchiha-314/the-loop (this one) | The whole DAG, A1–E3: the gateway process, store, routing, consume API, adapters, verbs and contract; the instance's block, client, pipeline, claims and bindings, hosted set, status and API; the Gateway card; the capability docs, decisions 144–146, the command and options pages | open (draft until `verification` fills the plan's results; `pr ready` before the reviews) |

Opened 2026-10-19 from `feat/issue-496-gateway` against `main`; recorded with
`the-loop pr create --work-item github:MadaraUchiha-314/the-loop#496`, which labelled it
`the-loop: auto-execute` and `the-loop: rr`.
