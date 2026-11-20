---
type: evidence
workItem: issue-551
---

# Final validation: a session never goes idle unnoticed

> The `evidence` node's proof. Summarised from the executed verification in
> [`testing-plan.md`](../testing-plan.md), re-run at `a0b978dd` after the review
> fixes. Whole suite: 7928 passed, 2 skipped; `pre-commit run --all-files` exit 0.

## Final validation evidence

| Acceptance criterion | How it was proved | Where |
|----------------------|-------------------|-------|
| **R1** an advance says what comes next | The claim envelope carries `assignment` and `next`; an agent node says "continue in this same turn"; a human node names the gate; absent when the pointer did not move or the daemon delivered. Scenarios "a claim returns the next assignment and says to continue" and "an advance the daemon drives delivers the assignment once". | [`unit.md`](unit.md) T1, [`integration.md`](integration.md) T2, [`contract.md`](contract.md) T3 |
| **R2** the skill never tells a daemon session to stop at a boundary | The grep for both forbidden phrases returns nothing; `test_interaction.py` asserts the five stops, the three ask cases and the prompt's `--after` and `the-loop wait`. | [`documentation-check.md`](documentation-check.md) T12 |
| **R3** the Stop gate refuses a stop while agent work is owed | One test per step of the stop-check order. The regression: "a stop with work owed is refused past an approved gate". "A stop with an open ask is allowed". "The gate gives up after its attempts and records why". End to end with the real hook scripts. | [`unit.md`](unit.md) T1, [`integration.md`](integration.md) T2, [`e2e.md`](e2e.md) T4 |
| **R4** a watcher notices an idle session | One test per transition of the session's state. "An idle session is nudged, then a person is told once". "A restart repeats no nudge and no notice". "A stall ends when the session takes a turn, and the notice is edited". "A switched-off watchdog sends nothing and the gate still holds". End to end against a real tmux pane with no ingress running. | [`unit.md`](unit.md) T1, T7; [`integration.md`](integration.md) T2; [`e2e.md`](e2e.md) T4 |
| **R5** a comment does not grade the node | "A comment does not block an agent node", its inner-loop variant, "a met exit gate still advances on a comment", "a human gate still classifies the comment it receives"; a claim still records its block. | [`integration.md`](integration.md) T2 |
| **R6** a question can carry a default and a deadline | "A default is taken at its deadline, once, across a restart". "An answer cancels the default". "An answer after the default still reaches the session". "A question with no default is reminded once". The minimum wait, the upper bound, `--after` without `--default`. | [`unit.md`](unit.md) T1, [`integration.md`](integration.md) T2 |
| **R7** status says what is really happening | The `session:` line of `check` for each state, `sessions list`, the attention kinds, the dashboard's ask rule. "The stall notice is a short form in the work item's conversation". | [`unit.md`](unit.md) T1, [`contract.md`](contract.md) T3, [`ui.md`](ui.md) T5 |
| **Abuse cases 1–7** and the review's added cases | One named negative test each, 324 selected by the plan's expression. | [`security-tests.md`](security-tests.md) T8, [`security-review.md`](security-review.md) |
| **NFR** config, events, prompts and strings, migration, docs | Defaults and validation; nine registered events; an older CLI, an older log and a config with neither block. Docs parity. | [`unit.md`](unit.md) T10, [`documentation.md`](documentation.md) |

## Criteria met with a stated difference

| Criterion | What was built | Why |
|---|---|---|
| R4.4, R4.6, R3 for a pull request's own session | It gets the stall notice and ask handling. It gets no nudge, and its Stop gate does not judge the PR's inner loop. | Which checkout holds the inner loop's state is a design decision. Recorded as a limit; follow-up ticket proposed. |
| R4.5 on GitHub | A stall's end is a follow-up comment, not an edit. | The GitHub channel cannot edit a comment in place. Slack edits the notice. |
| R4.10 "from the recorded events" | True, and it has a cost: with the event log disabled or unwritable the watcher does nothing. | The budget lives in the log; acting without a record would mean nudging without bound. |
| R6.1 "the time at which it will be taken" | A second timed ask on the same step is refused while one is open, and after one's default was taken. | Review finding: without it a session could renew defaults forever. |
| Design, Security design: "refuses any other" ref | The service confirms a live registered session; it authenticates no caller. | See [`security-review.md`](security-review.md), "The binding check". Sign-off requested. |

## Not proved before merge

A stall on a real harness (T11). The daemon that drives sessions runs the released
code. The first real nudge or "default taken" after release will be reported on the
ticket with its event-log lines. One dependency rides on that: Claude Code's
prompt-submit hook must also fire on turns the harness starts itself.
