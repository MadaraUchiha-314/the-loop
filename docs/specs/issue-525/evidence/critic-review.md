# Critic review — issue-525

Policy (`the-loop critic policy`): `criticReviewCount: 1`, `stopOnNoNewFindings: true`.

## Review cycles

| Round | Critic | Verdict | Findings | Action |
|-------|--------|---------|----------|--------|
| 1 | codex (`gpt-6.1-sol`), via `the-loop critic run codex --cwd <worktree>` | no blocking findings | (a) An outer `implementation` parked by `await-inner-loops` would now be re-evaluated only by another `graph complete`, where an event used to re-evaluate it. (b) Coverage gaps: a `code` actor and the parked case. | (a) Fixed: an agent node parked on a wait its own chain returned is still evaluated on an event. Entering a node clears `parked`, so a park on an agent node means its chain already ran. The `review` step is never parked, so the issue's bug stays fixed. (b) Added `test_a_code_node_is_not_evaluated_on_an_event`, `test_an_event_re_evaluates_an_agent_node_its_own_chain_parked` and `test_a_claimed_node_waiting_on_inner_loops_still_hears_events`. |

The critic's first attempt ran in the wrong checkout and reviewed nothing. It was re-run
with `--cwd`, and only that round is counted.
