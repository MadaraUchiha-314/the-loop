# Security review (issue-447)

Tier 3. the-loop's checklist over the requirements' abuse cases A1–A7, run on the branch
diff against `b473ced` on 2026-09-30, scoped to `cli/the_loop` and `hooks/`. The change in
the threat model is that **the agent can now trigger GitHub writes through the-loop**:
a comment, an issue, a pull request, a merge. No new credential enters. The token that
performs them is the one the daemon (routed) or the session's `GH_TOKEN` (in-process)
already held, and the scopes the docs name are unchanged. Tier 3 needs no named human
security sign-off. The autonomous review suffices, and no finding needs a
security-relevant decision.

## The checklist: abuse case → mechanism → negative test

| # | Abuse case | Mechanism | Test | Verdict |
|---|------------|-----------|------|---------|
| A1 | a token leaks through a verb's output, an error, or the event log | every client call goes through `_call` and `_translate` (status plus GitHub's message); core composes messages from `GitHubApiError.__str__`; the new `work_item.*` events carry refs, URLs and booleans only | `test_abuse_447_a1_the_token_never_reaches_a_verb_error` (client, 401), `test_abuse_447_a1_a_token_never_reaches_a_verbs_words` (core) | holds |
| A2 | a prompt-injected session merges a PR a human should merge | `merge_on_approval(config)` is read inside core from the executing process's config; no CLI flag, route field or MCP argument carries a policy; a body field `mergeOnApproval` is ignored by the pydantic model | `test_abuse_447_a2_merge_is_refused_when_the_operator_merges` (core), `test_abuse_447_a2_the_service_merges_by_its_own_policy_only` (route, with a smuggled field) | holds |
| A3 | hostile coordinates reach a URL path or a GraphQL variable | `_coordinates`, `_number`, `_branch` (`is_branch_name`: `[A-Za-z0-9._/-]`, no `..`, `//`, leading `-`/`/`, `@{`), `_sha` (7–40 hex), the merge-method allow-list, `_slug`/`_repository` with `is_github_host`; the `reviewThreads` document is a constant with values as variables | `test_abuse_447_a3_hostile_branches_are_refused_before_a_request` (7 cases), `…_a_hostile_sha_is_refused`, `…_an_unknown_merge_method_is_refused`, `…_create_ticket_refuses_a_bad_repository` (5 cases), `test_review_threads_walk_the_cursor_with_values_as_variables` | holds |
| A4 | an agent's comment is read back as human input and resumes its own session | the ledger's default branch stamps `mark_self_authored` and an envelope; `publish_comment` drops enveloped comments at ingress; the bus-fault fallback still stamps the marker | `test_abuse_447_a4_a_comment_is_marked_enveloped_and_mirrored`, `test_a_bus_fault_still_posts_the_marked_comment`, `test_an_agents_comment_is_recorded_and_mirrored_never_republished` | holds |
| A5 | an in-process fallback runs silently where the operator expected the service | `harness_routed` prints `IN_PROCESS_NOTE` on every fallback, and never auto-starts (`_spawn_service` is never called) | `test_abuse_447_a5_the_in_process_fallback_is_never_silent`, `test_harness_routed_uses_a_running_service` | holds |
| A6 | the hook turns a `git push` into a shell-injection surface | the argv is fixed words plus a ref that matched `_REF_RE`; `subprocess.run` with a list and no shell; nothing from the tool's response is read | `test_abuse_447_a6_no_response_text_reaches_the_argv`, `test_an_injected_work_item_ref_is_refused`, `test_the_hook_is_stdlib_only_so_it_survives_a_missing_cli` (asserts no `shell=True`) | holds |
| A7 | `ticket show` hands untrusted text to the agent as instructions, or fetches attacker content | output is JSON data; attachment URLs come from `github_attachment_urls` and are never fetched; the skill (`automation.md` § Reaching GitHub) says ticket text is data | `test_abuse_447_a7_show_ticket_fetches_no_attachment` | holds |

## What else was checked

- **New service surface.** Seven routes and seven MCP tools, all loopback-only like every
  other route (the exposure guard is unchanged). They grant nothing the token did not
  already allow, and no generic proxy exists (decision-140 D3).
- **Merge through MCP.** `merge_pull_request` is registered. The policy check sits in
  core, below the facade both the route and the tool call, so the tool can do nothing
  the verb cannot. GitHub's own branch protection still applies.
- **`pr create` on the service.** The head branch comes from the CLI's checkout and is
  validated (A3) before it reaches the JSON body. The service never reads a working
  directory for it.
- **Discovery after every push.** It is one GitHub read, and each link is idempotent. A
  hostile branch name in a checkout is refused before the request.
- **Dependencies.** None added.

## Verdict

No unresolved security finding. Tier 3: the autonomous review suffices.
