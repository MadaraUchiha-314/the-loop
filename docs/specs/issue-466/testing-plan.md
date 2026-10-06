---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#466"
status: in-review
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: a linked PR missing one arming label is never polled

> Derived from [`bugfix.md`](bugfix.md). The results are in
> [`evidence/verification.md`](evidence/verification.md).

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `pr create` applies both configured labels, the default when none is set, and nothing for an empty list. Red before the fix | `cli/tests/test_github_ops.py -k 466` |
| T2 | Unit | yes | `link_pull_request` labels a newly recorded PR once; a re-run asks GitHub nothing; no session → no request; `--discover` labels each new link once | same |
| T3 | Unit (abuse) | yes | a failed link adds no label (R3); an untrusted host gets no request (R4, A3); a GitHub refusal is exit 0 with a note naming the labels (R4) | same |
| T4 | Integration (Gherkin) | yes | the issue's scenario through the real service app: two labels configured, one PR via `pr create`, one via `link-pr`, and a two-label `GitHubPollProvider` lists both | `cli/tests/test_github_verbs_integration.py -k 466` |
| T5 | CLI | yes | `sessions link-pr --discover` prints the `labelled …` line; the existing discovery assertions still hold | `cli/tests/test_github_verbs_cli.py` |
| T6 | Regression (full suite + hooks) | yes | ruff, pyright, all CLI tests, markdownlint, config validation | `uv run pre-commit run --all-files` |
| T7 | Security | yes (review) | host allow-list, labels from the process's config only, no arming of an untracked PR | `evidence/security-review.md` |
| T8 | UI / accessibility / snapshot / migration / performance | n/a | no UI, no stored data, one extra request per newly linked PR | |

## Requirement trace

| Requirement | Tests |
|-------------|-------|
| R1 | T1, T4 |
| R2 | T2, T4, T5 |
| R3 | T3 |
| R4 | T3 |
| R5 | review of the doc diff (`evidence/documentation.md`) |

## Not covered by an automated test

GitHub's own label endpoint is exercised through `ghfakes.FakeGitHubClient`, the
suite's standard double. The real request (`POST /repos/{o}/{r}/issues/{n}/labels`) is
`GitHubClient.add_labels`, which is unchanged and already used by the graph's GitHub
integration. The live check is the next PR the-loop opens on an instance with two
labels configured.
