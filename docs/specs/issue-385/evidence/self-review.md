---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#385"
---

<!-- Authored per the the-loop:writing skill. -->

# Self-review: the repository carries its own knowledge graph

> The `self-review` node's record: the diff re-read adversarially against the design,
> before any other reviewer sees it.

## What I went looking for

| # | Question | Answer |
|---|---|---|
| 1 | Can a pull request — from a fork or not — get the key out of this workflow? | No path found. The only job that names `secrets.ANTHROPIC_API_KEY` is conditioned on `github.event_name != 'pull_request'`, the `dry-run` job names no `secrets.` at all, and both facts are pinned by a test that reads the YAML. A pull request that edits the workflow still runs under *its own* event, so it can only ever run the `dry-run` job; the edit reaches the secret only once merged, which is a review |
| 2 | Can the bot commit start a loop? | No: it is pushed with `GITHUB_TOKEN`, and GitHub starts no workflow for such a push. release.yml has relied on the same rule for its `bump:` commit since decision-019. The `if: !startsWith(head_commit.message, 'bump:')` guard in release.yml exists for a *manual* re-run of a bump, not because the token loops |
| 3 | What does a failed run cost the next one? | The first draft used `actions/cache@v4`, which saves only when the job succeeds — so a run that extracted 48 chunks and then failed at `cluster-only` would have thrown the model's answers away and the next run would have paid again. **Changed**: `actions/cache/restore` before the extraction and `actions/cache/save` with `if: always()` after it. The test now asserts the split and the condition |
| 4 | Does the script ever touch anything but `graphify-out/`? | `git add -A -- graphify-out` and `git commit … -- graphify-out` are both pathspec-scoped. `git add -A` honours `.gitignore`, so the cache and the sidecars are not staged even though they sit under the same directory (`git check-ignore -v` in `evidence/pipeline.md`). A file the build modified elsewhere is neither committed nor allowed to block the rebase — that second half was **a real defect** the integration scenario caught: the first script failed with `cannot rebase: You have unstaged changes`, fixed with `--autostash` |
| 5 | Does the rebase work on the depth-1 checkout Actions makes? | Proved by `test_a_shallow_checkout_is_enough`: a depth-1 clone, a commit landed on the remote, rebase and push succeed |
| 6 | Can the script force-push? | The word does not appear in it; the conflict scenario proves a diverging remote commit survives and the script exits 1 |
| 7 | What happens on the very first run, with no `graphify-out/` in the tree? | `graphify extract` creates it; `git add -A -- graphify-out` stages a new directory; the first commit carries the full asset. The fake-model run 1 is that case |
| 8 | Is the model actually reachable with graphify's request shape? | `_call_claude` sends `model`, `max_tokens`, `system`, `messages` and nothing else — no `temperature`, which the Claude 5 family rejects. The `anthropic` package is **not** a dependency of `graphifyy` (no extra pulls it; `import anthropic` failed in the tool environment until `--with anthropic`), which is why the install line carries it and a test pins that |
| 9 | Will the tool's binary be on `PATH` in the runner? | `uv tool install` puts it in `uv tool dir --bin` (`~/.local/bin` here), which `setup-uv` may or may not add; the step appends it to `GITHUB_PATH` explicitly |
| 10 | Does anything in this repository choke on a 30 MB JSON file or a 300 KB generated markdown file? | markdownlint would have linted `GRAPH_REPORT.md` (`**/*.md` in the Makefile, `types: [markdown]` in pre-commit); it is excluded in `.markdownlint-cli2.jsonc`, and the exclusion is asserted. `test_writing_parity` scans `docs/`, `skills/`, `commands/`, `rules/` and `README.md` only. VitePress reads `docs/` only. ruff and pyright read `cli/` and `hooks/` |
| 11 | Are the numbers in the docs the numbers that were measured? | Sizes, counts and timings come from `evidence/pipeline.md`. The dollar figures are derived: graphify's own estimate ($22.59 for 6.59 M "sent" tokens at its Sonnet 4.6 rates) counts three retry attempts per hollow chunk, so the real first-run input is ~2.2 M tokens (48 chunks at the 60 k budget); at Opus 5's $5/M in and $25/M out with ~200 k output tokens that is ~$16, and the docs say "$20–30" to leave room for images and retries. Sonnet 5 at $2/$10 is a third |
| 12 | Did the writing-tell scan and markdownlint pass on the new prose? | `markdownlint-cli2` on the ten new or changed markdown files: 0 errors. The P0 tells list was read before writing; none of its patterns appear |

## What I changed after re-reading

- **The cache is saved on failure** (finding 3): restore/save split with `if: always()`.
- **`--autostash` on the rebase** (finding 4), found by the test before the re-read.
- **`GITHUB_SHA` is captured before the commit** in the script, and the tests capture the
  built SHA before running it, after two scenarios asserted `HEAD~1` post-run and got the
  fetched commit instead.
- **The identity override in the single-commit scenario** — the test's own `GIT_AUTHOR_*`
  fixture reached the script; the scenario now passes an empty identity so the script's
  bot default is what is asserted.

## Round 2 — zero new findings

A second pass over the final diff after the docs were written: every workflow property a
reviewer would check is a named test; the script's six behaviours are six scenarios; the
one thing that cannot be proved here (the real model, the real push) is recorded as
unexecuted with the owner's exact step rather than ticked. Converged.
