---
type: tasks
phase: tasks-breakdown
workItem: "issue-311"
status: locked
approvedBy: []
overrides: {}
---

# Tasks: every link and every `gh` call names the GitHub it is on

> Phase 3 of 3. Small, verifiable tasks; each `_Test:_` names a row of `testing-plan.md`.

## Task list

- [x] 1. The resolver
  - `cli/the_loop/ghhost.py`: `github_host`, `api_base_for`, `host_of_api_base`,
    `host_from_remote`; `sessions.is_github_host` made public.
  - Security-relevant (A1, A4): the grammar is applied before any interpolation; the
    remote is last and gated on a root.
  - _Depends on:_ none
  - _Requirements:_ R1.1, R1.2, R6.1
  - _Test:_ `T1 — uv run pytest cli/tests/test_ghhost.py`

- [x] 2. Minting with the host
  - `cli/the_loop/graph/refs.py` (`host=""` on both functions), `graph/bootstrap.py`
    (`config["githubHost"]`, `prRef`), `graph/runtime.py` (`derive_ref(..., host)`).
  - _Depends on:_ 1
  - _Requirements:_ R2.1–R2.3
  - _Test:_ `T2, T7`

- [x] 3. One `gh` spelling, every writer
  - `cli/the_loop/comments.py` (`gh_host_args`, `comment_argv`, `issue_argv`,
    `create_issue`), `linkage.py` (`existence_argv` reuses it), `reactions.py`
    (`ReactionTarget.host`, `_argv`).
  - _Depends on:_ 1
  - _Requirements:_ R4.1, R4.2, R4.4, R4.5
  - _Test:_ `T3`

- [x] 4. The poller
  - `cli/the_loop/poller/github.py`: `RepoSpec.host`/`gh_repo`/`parse`; `GhClient`
    methods take `host`; the provider passes it; `owns` and `closure`.
  - _Depends on:_ 3
  - _Requirements:_ R4.1, R4.2, R5.1–R5.3
  - _Test:_ `T4`

- [x] 5. The graph integrations
  - `cli/the_loop/graph/integrations/github.py`: `_ref_parts`, `GitHubCli` argv,
    `GitHubApi` base derivation, `_linked_pull_refs(host)`.
  - _Depends on:_ 1, 3
  - _Requirements:_ R4.1–R4.4
  - _Test:_ `T5`

- [x] 6. The review brief
  - `cli/the_loop/graph/hooks/review.py`: `_PULL_URL` any host; `_own_coords`;
    `_normalize_pulls` and `_state_pulls` spell refs via `WorkItemRef`.
  - _Depends on:_ none
  - _Requirements:_ R3.1–R3.3
  - _Test:_ `T6`

- [x] 7. Schema, template, config, docs
  - Both schema copies (byte-identical), `skills/the-loop/templates/cli-config.yaml`,
    `.the-loop/cli-config.yaml`, `docs/config/cli/integrations-options.md`,
    `polling-options.md`, `routing-options.md`, `docs/cli/concepts.md`, `docs/cli/state.md`,
    `skills/the-loop/reference/automation.md`.
  - _Depends on:_ 1
  - _Requirements:_ R1.3, R1.4, R5.1
  - _Test:_ `T8`

- [ ] 8. Capability docs, decision, execution log, evidence
  - `docs/capabilities/cli.md`, `docs/capabilities/channels.md`, `docs/decisions/decision-104.md`
    (+ index), `docs/specs/issue-311/execution-log.md`, `evidence/verification.md`,
    `evidence/security-review.md`.
  - _Depends on:_ 1–7
  - _Requirements:_ all
  - _Test:_ `T9, T10 — make check`
