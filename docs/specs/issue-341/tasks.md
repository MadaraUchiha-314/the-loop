---
type: tasks
phase: tasks-breakdown
workItem: "issue-341"
status: draft
approvedBy: []
overrides: {}
---

# Tasks: the kickoff prefix, the declared set, and the refusal that answers

> The last spec artifact. A DAG derived from the design and testing plan; each task names
> the testing-plan row that proves it. TDD: the test first, red, then green.

## Task list

- [ ] 1. `channels/repos.py` — `DeclaredRepo`, `parse_repo_path`,
  `declared_repositories`, `repository_keys`
  - _Depends on:_ none
  - _Requirements:_ R2.1
  - _Test:_ T1 — the declared-set tests; T8 — A6
- [ ] 2. `channels/commands.py` delegates — `_ref_from_path` through `parse_repo_path`,
  `may_target` through `repository_keys`, `_configured_repositories` deleted
  - _Depends on:_ 1
  - _Requirements:_ R2.1
  - _Test:_ T10 — `test_channels_commands.py` unchanged and green
- [ ] 3. `channels/kickoff.py` — `PREFIX_RE`, `KickoffTarget`, `resolve_target`,
  `refusal_text`
  - _Depends on:_ 1
  - _Requirements:_ R1.1–R1.4, R2.2–R2.5, R3.1, R3.2
  - _Test:_ T1 — the grammar, resolution and wording tests; T8 — A2, A3, A4, A5
- [ ] 4. `channels/slack.py` — `kickoff_enabled` without `kickoff.repo`
  - _Depends on:_ none
  - _Requirements:_ R3.3
  - _Test:_ T1 — `test_kickoff_is_enabled_without_a_repo`; T8 — A7
- [ ] 5. `channels/inbound.py` — `process_kickoff` resolves after the allow-list, refuses
  with a reaction and a threaded reply, creates with the resolved slug and stripped text
  - _Depends on:_ 3, 4
  - _Requirements:_ R1.1, R1.3, R1.5, R2.5, R2.6, R3.1, R3.2, R4.1, R4.2
  - _Test:_ T2 — the four scenarios; T8 — A1, A7
- [ ] 6. `eventlog.py` — the three drop reasons in the `channel.dropped` catalog entry
  - _Depends on:_ 5
  - _Requirements:_ R4.2
  - _Test:_ T10 — `test_eventlog.py`
- [ ] 7. The scenarios — four Gherkin integration scenarios in
  `test_channels_integration.py`
  - _Depends on:_ 5
  - _Requirements:_ R1.1, R2.3, R3.1, R3.2
  - _Test:_ T2
- [ ] 8. `channels status` — the `kickoff:` line names the fallback (or its absence) and
  the size of the declared set
  - _Depends on:_ 1, 4
  - _Requirements:_ R5.1
  - _Test:_ T1 — the status tests
- [ ] 9. Schema + docs — the `kickoff.repo`, `publish` and `read` descriptions in both
  schema copies, the guide, the channels options page, the capability doc and its
  history row, `decision-120` + index row
  - _Depends on:_ 5
  - _Requirements:_ R3.4, R5.1
  - _Test:_ T10 — schema parity and docs parity
- [ ] 10. Verification and evidence — run the matrix, write
  `evidence/verification.md` and `evidence/security-review.md`
  - _Depends on:_ 1–9
  - _Requirements:_ all
  - _Test:_ T12, T13

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with comments.
