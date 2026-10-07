---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#475"
---

# Pull requests: Jira as a first-class work-item source and update channel

> Five stacked PRs in this repository. Each is based on the one before it, and each was
> recorded against #475 with `the-loop pr create --work-item github:MadaraUchiha-314/the-loop#475`,
> which also labelled it with `routing.autoExecuteLabels`. Review fixes from the self-review,
> critic and security rounds land on the top PR (#480). The stack merges in order, and the
> work item completes once all five are merged or closed.

## Pull requests

| PR | Repository | Branch → base | Scope / tasks | Status |
|----|------------|---------------|---------------|--------|
| [#476](https://github.com/MadaraUchiha-314/the-loop/pull/476) | this one | `feat/issue-475-jira-support` → `main` | spec chain; identity: `RefScheme`/`JiraScheme`, provider-derived spec ids, `origin_repository` (tasks 1.1–1.5) | open |
| [#477](https://github.com/MadaraUchiha-314/the-loop/pull/477) | this one | `feat/issue-475-jira-2-integration` → #476 | `JiraClient`, `JiraProvider`, `integrations.jira` schema 0.12.0 and migration, decision-142, `the-loop doctor jira` (tasks 2.1–2.7) | open |
| [#478](https://github.com/MadaraUchiha-314/the-loop/pull/478) | this one | `feat/issue-475-jira-3-channels` → #477 | `jiraformat`, `jiralabels`, Jira self-marker, hooks resolved by ref, `RoutedLedger`/`JiraLedger`, `JiraChannel` and mirror-only rooms (tasks 3.1–3.7) | open |
| [#479](https://github.com/MadaraUchiha-314/the-loop/pull/479) | this one | `feat/issue-475-jira-4-ingress` → #478 | `JiraPollProvider`, `/jira-webhook` doorbell, Jira allow-list, relay marker (tasks 4.1–4.5) | open |
| [#480](https://github.com/MadaraUchiha-314/the-loop/pull/480) | this one | `feat/issue-475-jira-5-edges` → #479 | PR→Jira linkage, ticket/comment/ask/pr verbs, `/init` and skill text (tasks 5.1–5.4); verification and T11 evidence; all review fixes (self-review H1–L5 and R2-1–R2-4, critic C1–C3) | open |
