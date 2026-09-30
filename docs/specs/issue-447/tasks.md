---
type: tasks
phase: tasks-breakdown
workItem: "issue-447"
status: draft
approvedBy: []
overrides: {}
---

# Tasks: the harness's GitHub verbs

> The last spec artifact: a DAG derived from the design and the testing plan. Each task
> names the testing-plan row that proves it.

## Task list

- [ ] 1. The client: seven methods on `ghapi.GitHubClient` (`repository`, `create_pull`,
  `get_pull`, `commit_checks`, `merge_pull`, `review_threads`, `open_pulls_for_head`), the
  branch, SHA and method checks, and the fake client's matching methods
  - _Depends on:_ none
  - _Requirements:_ R1.2–R1.8, R4.1, NFR
  - _Test:_ T1, T7 (A1, A3), T8
- [ ] 2. Core: `core/github_ops.py` (the eight operations, `resolve_pull_request`, the
  checks roll-up); `cli_config.merge_on_approval`, shared with the graph's `notify` hook;
  `core.sessions.pull_request_ref` made public
  - _Depends on:_ 1
  - _Requirements:_ R1.1–R1.9, R2.3, R4.1
  - _Test:_ T2, T7 (A2, A4, A7)
- [ ] 3. The surface: `client.routing.harness_routed`; the `comment`, `ticket` and `pr`
  commands; `sessions link-pr --discover`; `CoreFacade`, `ManagerFacade`, routes, MCP
  tools, and the OpenAPI contract
  - _Depends on:_ 2
  - _Requirements:_ R1.*, R2.1–R2.3, R3.1–R3.3, R4.1, R4.2
  - _Test:_ T3, T4, T5, T7 (A5)
- [ ] 4. The hook: `hooks/the-loop-link-pr.py` trigger-agnostic, running `--discover`;
  the `hooks/hooks.json` description
  - _Depends on:_ 3
  - _Requirements:_ R4.3, R4.4
  - _Test:_ T6, T7 (A6)
- [ ] 5. The documentation: `docs/cli/commands/{comment,ticket,pr}.md` and
  `sessions.md`; the skill (`SKILL.md`, `reference/{automation,collaboration,workflow,reviewing}.md`);
  the slash commands (`work-on`, `execute-tasks`, `finish-tasks`, `create-ticket`); the
  capability docs; `decision-140` and its row
  - _Depends on:_ 3, 4
  - _Requirements:_ R5.1, R5.2
  - _Test:_ T5, T11
- [ ] 6. Verification and evidence: `make check`,
  `evidence/{verification,self-review,security-review,documentation,reviewer-briefing}.md`,
  and the PR
  - _Depends on:_ 5
  - _Requirements:_ all
  - _Test:_ T11, T12
