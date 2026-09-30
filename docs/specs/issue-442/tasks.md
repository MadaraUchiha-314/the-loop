---
type: tasks
phase: tasks-breakdown
workItem: "issue-442"
status: draft
approvedBy: []
overrides: {}
---

# Tasks: the daemon reaches GitHub through PyGithub

> The last spec artifact. All six tasks landed on this work item's PR. A DAG derived from
> the design and testing plan; each task names the testing-plan row that proves it.

## Task list

- [x] 1. The dependency and the client — `PyGithub` in `cli/pyproject.toml` and `uv.lock`;
  `cli/the_loop/ghapi.py` (`GitHubApiConfig`, `GitHubApiError`, `GitHubClient`, the two
  GraphQL documents, `GhItem`/`GhComment`/`GhItemState`); `cli/tests/ghreplay.py`
  - _Depends on:_ none
  - _Requirements:_ R1.1, R2.1, R2.2, R2.4, R3.1 (O1–O12), R3.2, R3.3, R5.1
  - _Test:_ T1 — `test_ghapi.py`; T7 — A1, A2, A3, A5, A6; T8
- [x] 2. The writers — `comments`, `linkage`, `reactions`, `announce`, `core/selfdiagnosis`,
  `channels/github`, `control`, `cli_config.apply_integrations` (`_github`); every caller
  passing `gh_binary=` passes `api=`; `cli/tests/ghfakes.py`
  - _Depends on:_ 1
  - _Requirements:_ R2.3, R3.1 (O1–O5), R5.1
  - _Test:_ T2; T7 — A7, A8; T4 (announce, reactions, control, channels scenarios)
- [x] 3. The readers — `poller/github.py` over the client (`GhClient` and
  `check_gh_dependency` removed, `GhError` kept, 410 classified), `poller/poller.py` and
  the daemon's provider construction, `graph/integrations/{base,github}.py` (one provider),
  `commands/channels_cmd.py`
  - _Depends on:_ 1
  - _Requirements:_ R1.2, R3.1 (O5–O12), R3.4, R4.3, R5.2
  - _Test:_ T3; T4 (poller scenarios); T7 — A4
- [x] 4. The configuration — schema (authored + packaged), `migrations.py` (`0.11.0`,
  `_retire_github_cli`), `sdk/environment.py`, `skills/the-loop/templates/cli-config.yaml`,
  `.the-loop/cli-config.yaml`, the `0.10.0` fixtures
  - _Depends on:_ 2, 3
  - _Requirements:_ R1.2, R4.1, R4.2, R4.4
  - _Test:_ T5; T6
- [x] 5. The documentation — `docs/config/cli/integrations-options.md` and the sibling
  pages that describe the `gh` path, `docs/cli/installation.md`, `getting-started.md`,
  `receiver.md`, `concepts.md`, `docs/guide/onboarding.md`, `docs/sdk/environment.md`,
  `docs/cli/commands/{ask,diagnose,channels}.md`, the capability docs (`cli`,
  `webhook-triggers`, `interactive-sessions`, `self-diagnosis`, `sdk`, `channels`,
  `control-plane`), `decision-139` and its row
  - _Depends on:_ 4
  - _Requirements:_ R4.4, A4
  - _Test:_ T5 (docs parity); T11 (markdownlint)
- [x] 6. Verification and evidence — `make check`; the manual row on a `gh`-less box;
  `evidence/{verification,self-review,security-review,documentation,manual,reviewer-briefing}.md`;
  the PR
  - _Depends on:_ 5
  - _Requirements:_ all
  - _Test:_ T10, T11, T12
