---
type: tasks
phase: tasks-breakdown
workItem: issue-183
status: approved              # draft | in-review | approved
approvedBy: []                # pending — human gate on the PR (risk tier 4)
overrides: {}
---

# Tasks: multi-repo work items — the outer loop stays in the origin repo

> Derived from the approved `design.md` and `testing-plan.md`. TDD invariant: no production
> code without a failing test that motivates it.

## Task list

- [x] 1. `repo_state_key` + repo-qualified `inner_loop_state_dir`
  - `cli/the_loop/graph/hooks/loops.py`: the validator (two-plus segments, `[A-Za-z0-9._-]+`,
    never `.`/`..`) and the optional `repo` argument; `repo=""` returns the shipped path.
  - _Depends on:_ none
  - _Requirements:_ R1.3, R1.4, R1.6, abuse case 1
  - _Test:_ `T1/T8 — pytest tests/test_graph_loops.py -k "state_key or state_dir"` (red→green)

- [x] 2. `await-inner-loops` reads declared repositories
  - Same file: read `repos:` from the execution log's front matter, match each declared repo
    to its loops by key (origin ⇒ top level, from `config["originRepo"]`), `wait` naming a
    declared repo with no loop, and `wait` when the origin repo is unknown.
  - _Depends on:_ 1
  - _Requirements:_ R4.1–R4.4, abuse case 4
  - _Test:_ `T1/T8 — pytest tests/test_graph_loops.py -k await` (red→green)

- [x] 3. Thread `pr_repo` through the runtime, the CLI and the daemon link
  - `graph/bootstrap.build_runtime`, `core/graphs.*`, `commands/graph_cmd.py` (`--pr-repo`,
    added beside `--pr` by one helper; `--pr-repo` without `--pr` is a usage error),
  - `graphlink`: `_guarded`/`_build_runtime` parameter, the state-lock directory, and the
    four `on_pr_*`/`pr_context` methods deriving it from the refs they already hold.
  - _Depends on:_ 1
  - _Requirements:_ R1.3, abuse case 2
  - _Test:_ `T1/T8 — pytest tests/test_graphlink.py tests/test_core_graphs.py tests/test_cli.py -k pr_repo` (red→green)

- [x] 4. Cross-repo linkage in the router
  - `webhook/router.py`: `linked_work_items` (ref-returning, honours a qualified closing
    keyword and a `closingIssuesReferences` entry that names its repository);
    `linked_issue_numbers` becomes its same-repo wrapper; `extract_work_items` emits the refs.
  - _Depends on:_ none
  - _Requirements:_ R1.5, abuse case 3
  - _Test:_ `T1/T8 — pytest tests/test_poller.py tests/test_webhook*.py -k "linked or cross_repo"` (red→green)

- [x] 5. The surface, declared by the work item at `phase-selection`
  - _(Rewritten in review, PR #184: shipped first as `workflow.outerLoop.surface` in the
    harness config, then moved — the config key, its reader, its `READS` row, its schema
    block and both YAML files were removed again.)_
  - `hooks/selection.py`: the checklist row, `_parse_surface`, the phase-parser exclusion,
    the confirmation line and the frozen record; `GraphState.surface`;
    `HookContext.surface`; the runtime recording it and passing it into every hook context;
    `graph/bootstrap` keeps `originRepo` only.
  - _Depends on:_ none
  - _Requirements:_ R2.1–R2.5, R2.9
  - _Test:_ `T1 — pytest tests/test_graph_skips.py -k surface` (red→green)

- [x] 6. Tell the session where to iterate, and how to claim
  - `graph/hooks/assignment.render_assignment` and `graphlink.render_graph_context`
    (+ `GraphContext.surface`, read from `GraphState.surface`): the surface line for an
    outer-loop node, the pull-request line for an inner one, and `--pr-repo` in the claim
    command for a cross-repo loop; the dispatcher passes the endpoint's repository.
  - _Depends on:_ 3, 5
  - _Requirements:_ R2.7, R2.8
  - _Test:_ `T1 — pytest tests/test_graph_loops.py -k "surface or claim"` (red→green)

- [x] 7. The rules: skill, references, templates, config docs
  - `skills/the-loop/SKILL.md`, `reference/workflow.md`, `reference/collaboration.md`,
    `templates/execution-log.md` (`repos:`), `docs/config/harness-config.md` (the
    `ticketing.github` CLI-read row), `docs/cli/commands/graph.md` (`--pr-repo`, and the
    surface row on the `phase-selection` checklist).
  - _Depends on:_ 1–6
  - _Requirements:_ R1.1, R1.2, R2.4, R2.5, R2.7, R3.1–R3.3
  - _Test:_ `T12 — pytest tests/test_docs_parity.py tests/test_harness_config.py`

- [x] 8. Integration scenarios
  - `cli/tests/test_graph_multirepo_integration.py`: the cross-repo PR walking its inner
    loop under the origin repo's spec directory, and the outer gate holding until a declared
    repository finishes. Gherkin docstrings, `Requirement:` links.
  - _Depends on:_ 1–6
  - _Requirements:_ R1.1–R1.5, R4.1, R4.2
  - _Test:_ `T2 — pytest tests/test_graph_multirepo_integration.py` (red→green)

- [x] 9. Capability docs, user-facing docs, decision record
  - `docs/capabilities/process-graph.md`, `spec-workflow.md`, `interactive-sessions.md`,
    `webhook-triggers.md`; `README.md`, `docs/index.md`, `docs/guide/how-it-works.md`;
    `docs/decisions/decision-069.md` + the index, and the pointer back from decision-051.
  - _Depends on:_ 7
  - _Requirements:_ all (the ready-to-ship gate)
  - _Test:_ `T12 — pytest tests/test_docs_parity.py`

- [x] 10. Verification: execute `testing-plan.md`, record results and evidence
  - _Depends on:_ 1–9
  - _Requirements:_ all
  - _Test:_ `T1, T2, T8, T10, T12, T13 — the whole matrix`

- [x] 11. Review round (PR #184): move the surface out of the config
  - The owner's two review comments: the surface belongs on the `phase-selection`
    checklist, per work item, defaulting to the work item itself; no key in either config
    file. Removed `workflow.outerLoop` from the schema, both YAML files, `harness_config`
    (reader, constants, `READS` row) and `docs/config/harness-config.md`; added the
    checklist row and its plumbing; rewrote R2, design C5/F3, decision-069 D7–D9 and its
    alternatives, the capability docs, the README, the guide and this file.
  - _Depends on:_ 1–10
  - _Requirements:_ R2 (revised)
  - _Test:_ `T1/T12/T13 — the whole matrix, re-run`

## Dependency graph (DAG)

```mermaid
graph LR
  T1[1 repo key] --> T2[2 await gate]
  T1 --> T3[3 thread pr_repo]
  T5[5 surface at phase-selection] --> T6[6 assignment/prompt]
  T3 --> T6
  T4[4 cross-repo routing]
  T2 & T3 & T4 & T6 --> T7[7 rules & docs]
  T2 & T3 & T4 & T6 --> T8[8 integration]
  T7 --> T9[9 capability docs & decision]
  T8 & T9 --> T10[10 verification]
  T10 --> T11[11 review round: surface moves out of config]
```

## Checkpoints

Tests run after each task (red→green recorded in `execution-log.md`), the full suite plus
lint/typecheck after task 9, and the whole matrix at task 10 — after which the review chain
and the security-review gate run before the work item can be marked ready. Task 11 is the
owner's review round on PR #184: the whole matrix ran again after it.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with comments.
