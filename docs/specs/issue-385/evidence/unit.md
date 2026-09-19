---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#385"
---

<!-- Authored per the the-loop:writing skill. -->

# Unit evidence: the repository carries its own knowledge graph

> Testing-plan rows T1 and T4. Run from the repository root with
> `uv run --project cli python -m pytest -q <suite>`.

## T1 — the workflow's invariants (`cli/tests/test_graphify_workflow.py`)

```text
11 passed in 0.11s
```

One test per invariant: the triggers (push to `main`, dispatch, pull requests filtered to
the two pipeline files); queue-not-cancel; the secret read by the `rebuild` job only and
that job conditioned away for pull requests; `contents: write` on that job and nowhere
else; the pinned `graphifyy` with `--with anthropic` in both jobs; the exact `extract` and
`cluster-only` command lines with the `claude` backend and the pinned model, plus the
named error for a missing key; the rehearsal's `--code-only`/`--no-label` with no push;
the commit going through the script with the semantic cache on the Actions cache; the
ignore rules; the markdownlint exclusion; the `make graph` target.

## T4 — the abuse cases pinned by tests

```text
uv run --project cli python -m pytest -q cli/tests/test_graphify_workflow.py cli/tests/test_graphify_commit_integration.py -k "api_key or write_access or rebased or conflict or keeps_failing or names_the_communities"
6 passed, 11 deselected
```

Abuse case 1 (a pull request reaches for the key) is `test_the_api_key_reaches_exactly_the_rebuild_job` and `test_write_access_is_confined_to_the_rebuild_job`; abuse case 3 (the race with the release) is the rebase, conflict and rejecting-remote scenarios; abuse case 5 (a smaller graph replacing the committed one) is the command-line pin, which has no `--allow-partial`.

## Red → green

| Step | The red |
|---|---|
| `test_graphify_workflow.py`, whole file | `11 failed` — `FileNotFoundError: .github/workflows/graphify.yml` and then each invariant in turn as the file grew |
| `test_graphify_commit_integration.py`, whole file | `6 skipped` — the script did not exist (`skipif(not SCRIPT.is_file())`), then `3 failed` on the first script |
| `test_a_changed_graph_lands_as_one_chore_commit` | **a real defect**: `error: cannot rebase: You have unstaged changes.` — a file the build had modified outside `graphify-out/` blocked the rebase. Fixed with `git rebase --autostash` |
| the same test, second red | the author assertion: the test's own identity override reached the script — the test now passes an empty identity, which the script's `:-` defaults treat as unset |
| the rebase and shallow scenarios | expected the built SHA as `HEAD~1` after the run; it is the clone's `HEAD` before the run, and the tests now capture it there |
| the same two scenarios, **red on the GitHub runner only** (PR #386's first CI run) | the runner exports `GITHUB_SHA`, the script honours it by design, and the test inherited it — the message named the run's merge commit instead of the clone's `HEAD`. The test harness now passes an empty `GITHUB_SHA`, which the script's `:-` default reads as unset; reproduced locally with `GITHUB_SHA=deadbeef` before the fix, green after |
