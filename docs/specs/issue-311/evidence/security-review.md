# Security review — issue-311

> Mechanism: the-loop checklist (`security.review.mechanism: auto`; no security-review
> skill is invocable from this session's plugin set). Tier 4: a named human sign-off is
> required on the pull request (`security.review.humanSignOffMinTier: 4`).

## Threat model recap

A host string selects **which credential `gh` sends** and **where a human is sent** when
they click. The work item adds one configuration key, one environment read, one
subprocess read and one `--hostname`/`--repo` spelling on every outbound `gh` call.

## Abuse cases — disposition

| # | Abuse case | Closed by | Evidence |
|---|------------|-----------|----------|
| A1 | A configured host carries a scheme, a path, credentials, whitespace or an argv fragment and reaches an argv or a URL | `sessions.is_github_host` applied before any interpolation at every entry point: the resolver (skips with a warning), `ref_for`/`derive_ref` (`""`), `RepoSpec.parse` (`ValueError`), `create_issue` (refused), `_ref_parts` (malformed), `review._pull_ref` (`""`) | `test_ghhost.py::test_an_invalid_configured_host_is_skipped_with_a_warning`, `test_graph_refs.py::test_an_invalid_host_is_one_more_refusal`, `test_poller.py::test_repospec_refuses_a_path_that_is_not_a_host`, `test_comments.py::test_a_kickoff_slug_with_a_bad_host_is_refused`, `test_graph_integrations.py::test_a_ref_with_a_bad_host_is_malformed`, `test_ghhost_integration.py::test_a_bad_configured_host_never_reaches_a_ref` |
| A2 | A hosted ref makes the-loop send the operator's github.com token to another host | `gh` holds credentials per host and sends only the one for the host named by `--hostname`/`--repo`; the API transport derives a base only from a host that passed the grammar and only when `baseUrl` is the public default; an explicit `baseUrl` is honoured verbatim | `test_graph_integrations.py::test_the_api_transport_derives_the_enterprise_base` (explicit base kept) |
| A3 | A webhook payload names a host to redirect the-loop's calls | Unchanged boundary (issue-130): the payload is signed and the host was already the work item's identity; this work item makes the outbound calls agree with it | `test_routing.py::test_pr_work_item_carries_the_host_off_the_payload` (unchanged, passing) |
| A4 | The checkout's `origin` remote is pointed elsewhere | Tier 4 of five: consulted only when a caller names a root (the graph's session), after the config and `$GH_HOST`, through `git config --get` with no shell, validated as a host | `test_ghhost.py::test_the_remote_is_read_only_when_a_root_is_given`, `test_ghhost.py::test_gh_host_outranks_the_remote`, `test_ghhost_integration.py::test_the_checkouts_remote_answers_in_session` |
| A5 | A github.com deployment changes behaviour | The host is written only when it is not the default; every pre-existing argv/ref/URL assertion in the suite is unchanged and still passes | `test_ghhost_integration.py::test_github_com_mints_exactly_what_it_always_did`, `test_poller.py::test_a_github_com_read_is_byte_identical`, `test_comments.py::test_gh_host_args_is_written_only_off_the_default`, `test_reactions.py::test_a_github_com_reaction_argv_is_unchanged`, the 2919 pre-existing tests |

## Checklist

- [x] Input validation: one grammar for a host, applied before interpolation, at every entry point.
- [x] No shell: every `gh`/`git` spawn is an argv list (`subprocess.run([...])`).
- [x] Secrets: no token is read, logged or written by this change; the resolver logs the host and its tier only.
- [x] Fail closed: an invalid candidate falls to the next tier or to `""`; no new exception type reaches a caller.
- [x] No new attack surface on the ingress: the webhook/poll host derivation is untouched.
- [x] Evidence redaction: no real hostnames, tokens or personal data in the committed evidence (`ghe.corp.example` is a fixture).

## Outcome

**Pass** on the autonomous checklist. **Human sign-off required** (tier 4) — requested on
the pull request.
