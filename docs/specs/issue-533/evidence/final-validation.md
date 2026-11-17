---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#533"
---

# Final validation: opt-in session credentials, never on argv

Summarised from [`testing-plan.md` § Verification results](../testing-plan.md#verification-results)
(raw output in [`verification.md`](verification.md)). Re-run after the review fixes:
the targeted suites and T2 still pass (265 passed).

## Final validation evidence

| Acceptance criterion (#533) | How it was proved | Where |
|-----------------------------|-------------------|-------|
| No `sessionCredentials`: behaviour identical, issue-482 tests unchanged (R1.2) | issue-482 unit + real-tmux tests unchanged and green; unconfigured boundary equals today's; no file, no loader | T2, T10; `test_envstate.py::…no_session_credentials…`, `test_tmux_runner.py::…no_credentials_is_todays_command` |
| Pane holds `GH_TOKEN` with the source value | real tmux: `/proc/<pane>/environ` has `GH_TOKEN=<value>` and not `SESSION_GH_TOKEN` | T2 `…inherits_a_credential_no_argv_holds` |
| No argv holds the value (`ps -eo args`, server name, pane command) | real tmux: `ps -eo args`, server `/proc/<pid>/cmdline`; unit: runner argv; loader keeps the path in `$1` | T2; T1 A1, CR1-1 |
| `show-environment -g` lacks it, including when the spawn starts the server | real tmux, server started by the spawn; also the server's own environ lacks the value and the daemon's same-named token | T2 |
| No other session or the web-terminal hub inherits it | real tmux: a second session on the same server holds neither name nor value | T2 `…second_session_does_not_inherit_it` |
| Delivery file is `0600`, under `state.root`, gone once the harness runs | unit: mode/dir/symlink/owner; real tmux: directory empty once the harness runs | T1 A3, SR2-1, CR1-3; T2 |
| Rotating the source marks the session `stale` | real tmux: rotation reads `stale` on `GH_TOKEN`; a respawn reads `fresh` | T2 `…rotating_the_source_marks_the_session_stale` |
| A comment containing the value is scrubbed | every session route masks before the facade; the event log masks | T1 A4 `test_api_session_credentials.py`, `test_sessioncreds.py` |
| Invalid name or unset source warns (names only), spawn proceeds without it | caplog tests assert the variable is named and the value absent; names stay stripped | T1 R1.3, R1.4, CR1-2 |

Known limit, escalated: the `repositories` scope limits delivery, not reach (SEC-1,
[`security-review.md`](security-review.md)).
