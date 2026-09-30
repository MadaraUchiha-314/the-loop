# Self-review (issue-442)

Policy: this repository's `reviews` block — up to 3 self rounds and 3 critic rounds, stop
on no new findings, escalate on a repeat. Critic harnesses: `critics: []` in
`.the-loop/cli-config.yaml` — none declared, none run; the self rounds are an adversarial
read of the branch diff (`4fd746a...HEAD`) against the design's security section and the
callers' contracts.

## Round 1 — the client and the suite

| # | Finding | Fix | Test |
|---|---------|-----|------|
| C1 | `GitHubClient.rest()` returned the document PyGithub stamps a `url` onto when the answer carries none, so an empty issues document read as an object and `get_issue`'s "returned no object" guard never fired | the stamp (the request path, never GitHub's absolute `url`) is dropped in `rest()` | `test_an_empty_document_is_an_error_not_an_open_item` |
| C2 | A URL-built PyGithub object completes itself on construction unless told otherwise, so a "one POST" comment was a GET plus a POST — and a 404 on the GET before the write | every lazy object is built with `completed=False`, PyGithub's own idiom | `test_post_comment_is_one_post_on_the_issues_endpoint` (asserts exactly one exchange) |
| C3 | An empty label list reached GraphQL as `labels: []`, whose filter semantics GitHub leaves undefined, where the old listing simply had no `--label` | no labels → `labels: null` (no filter); the provider keeps nothing from it either way (issue-381) | `test_listings_ask_for_every_label_in_order`, `test_provider_drops_a_listed_item_missing_one_label` |
| C4 | Two graph tests (`test_the_outer_loop_assigns_without_a_pr`, `test_a_skipped_node_runs_none_of_its_entry_hooks`) passed or failed with the machine's ambient `GH_TOKEN` — on the unmodified tree they fail without one and pass with one, because `set-phase-label` resolved the real integration | an autouse fixture gives every graph test a provider over the in-memory client; a second autouse fixture deletes `GH_TOKEN`/`GITHUB_TOKEN` and installs a connection class that fails any HTTP PyGithub attempts | `conftest._hermetic_graph_integration`, `conftest._github_is_never_ambient` |
| C5 | The poller integration double stored the issues document under `item_state`, the name of the method the provider calls | renamed to `item_document` | the closure scenarios in `test_poller_integration.py` |

## Round 2 — the callers

| # | Finding | Fix | Test |
|---|---------|-----|------|
| C6 | `channels records` read the ticket twice (as an issue, then as a pull request) because `gh issue view` refused a pull request's number; the GraphQL `issueOrPullRequest` read answers for both, so the second try was dead code | one read | `test_channels_records_is_one_read_for_an_issue_and_a_pull_request_alike` |
| C7 | The daemon integration tests kept a stub `gh` on `PATH`, which the daemon no longer consults; with a token set the child would have reached api.github.com | a loopback GitHub (`ghstub.FakeGitHubServer`) the config's `baseUrl` points at, `host: github.com` so scope names are unchanged | `test_poll_daemon_integration.py`, `test_hosted_ingress_integration.py` |
| C8 | `looks_not_found` matched `HTTP 404` and would not have recognised the client's own rendering (`GitHub 404: Not Found`), so the announcer's 404-is-evidence path (issue-269) would have gone quiet | the pattern accepts both spellings | `test_looks_not_found_is_narrow`, `test_a_404_on_the_work_item_is_reported_as_a_missing_work_item` |

## Round 3 — read-through

No new findings. Checked: every `gh_binary=` caller passes `api=`; `_ghBinary` appears
nowhere but the migration's history; `shutil.which` is gone from every GitHub path; the
`ReactionTarget` kinds map one-to-one onto the three REST endpoints the old argv named;
the poller's request count per cycle is unchanged (T8); pyright is clean over `cli/`
including the doubles (they subclass the client for the type checker).
