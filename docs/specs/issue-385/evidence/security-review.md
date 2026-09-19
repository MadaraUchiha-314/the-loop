---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#385"
---

<!-- Authored per the the-loop:writing skill. -->

# Security review: the repository carries its own knowledge graph

> The `security-review` node's record, against `requirements.md` § Security considerations
> and `design.md` § Security design. See `skills/the-loop/reference/security.md`.

## Security review (gate)

- **Mechanism:** the-loop checklist (`reference/security.md`), applied to the diff.
- **Outcome:** pass, with one named human action outstanding (below).
- **Human sign-off:** **required** — risk tier 4 (`.github/workflows/**` is a sensitive
  path, and the change adds a paid credential and write access to `main`). Requested from
  @MadaraUchiha-314 (role `approver`) on the pull request, distinct from the PR approval.

## The boundaries this work item adds

Two, both in one job of one workflow:

1. **A paid third-party credential** (`ANTHROPIC_API_KEY`) enters GitHub Actions. It is
   a secret on the `graphify` environment, named by the `rebuild` job's one extraction
   step, and that job runs for `push` to `main` and `workflow_dispatch` only. The
   `dry-run` job — the only one a pull request can start — references no secret.
2. **Write access to `main`** (`contents: write`) for that same job, exercised through
   `GITHUB_TOKEN` by `scripts/graphify-commit.sh`, which commits a pathspec-scoped
   `graphify-out/`, rebases, and never forces.

The data crossing outward is the repository — every document and image — sent to the
Anthropic API. The tree is public and carries no secret; graphify skips credential-shaped
files by name and honours `.gitignore` before anything is read. The data crossing back is
JSON under `graphify-out/`, executed by nothing.

## Abuse cases, and where each is closed

| # | Abuse case | Closed by | Asserted in |
|---|---|---|---|
| 1 | A pull request edits the workflow to print or exfiltrate the key | the `rebuild` job's `if: github.event_name != 'pull_request'`; the `dry-run` job names no `secrets.`; GitHub withholds secrets from fork pull requests regardless; the merged workflow is reviewed as code | `test_graphify_workflow.py::test_the_api_key_reaches_exactly_the_rebuild_job`, `::test_write_access_is_confined_to_the_rebuild_job` |
| 2 | Prompt injection through a document aimed at the extraction model | graphify wraps every file in `<untrusted_source path sha256>`, neutralises chat-template sentinels, and instructs the model to treat the content as data; the output is graph JSON no workflow, hook or test executes | by construction (graphify `llm.py`; nothing of ours parses the graph) |
| 3 | The push races the release workflow's `bump:` push | rebase onto the remote tip, five attempts with backoff, never `--force`, abort on conflict | `test_graphify_commit_integration.py::test_a_commit_that_landed_meanwhile_is_rebased_past`, `::test_a_rebase_conflict_is_reported_not_forced`, `::test_a_push_that_keeps_failing_fails_the_job` |
| 4 | The bot commit re-triggers a rebuild (a token-spending loop) | a `GITHUB_TOKEN` push starts no workflow — the platform rule release.yml already relies on | design; no test can observe GitHub's scheduler |
| 5 | A bad model answer replaces the committed graph with a smaller one | graphify's shrink guard is left armed (`--allow-partial` is not passed) and the job fails; nothing is committed | `test_graphify_workflow.py::test_the_rebuild_extracts_with_claude_then_names_the_communities` (pins the exact command line) |
| 6 | A maintainer dispatches the workflow on a branch other than `main` with the environment's secret | the `graphify` environment's deployment-branch restriction — **an owner action**, not in this diff | requested below |

## What the change removes

Nothing. It adds two boundaries and confines both to one job on one event.

## Fail-closed

A missing key fails the extraction step before any request; a partial extraction fails
the job before any commit; a rejected push fails after bounded retries; a rebase conflict
fails at once. `main` is untouched in every failure and the next merge retries. A red run
keeps its semantic cache (`actions/cache/save` with `if: always()`) so the retry is not a
full re-extraction.

## Secrets

`ANTHROPIC_API_KEY` is read from `secrets` into one step's environment. It is not echoed:
the step does not `set -x`, graphify logs token counts and a cost estimate, not headers.
The `GITHUB_TOKEN` is the checkout's persisted credential, as in release.yml. The
`.graphify_root` sidecar, which records the runner's absolute path, is ignored.

## Human actions requested (paper trail on the PR)

1. Add `ANTHROPIC_API_KEY` as an **environment secret** on `graphify` (Settings →
   Environments → graphify; GitHub creates the environment on the workflow's first run,
   or create it first) — not as a repository secret.
2. Restrict the `graphify` environment's **deployment branches** to `main` (closes abuse
   case 6).
3. Sign off this review on the pull request (risk tier 4).
