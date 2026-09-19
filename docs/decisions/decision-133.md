# Decision 133: the knowledge graph is built headless in CI with an API key and committed to `main` — no Claude Code in the job

- **Status:** proposed
- **Date:** 2026-09-19
- **Work item:** [issue-385](https://github.com/MadaraUchiha-314/the-loop/issues/385)
- **Deciders:** the-loop (design); MadaraUchiha-314 (owner, at the PR)
- **Relates to:** [decision-006](decision-006.md) (CI runs what the developer runs),
  [decision-019](decision-019.md) (the release workflow commits to `main` with
  `GITHUB_TOKEN`)

## Context

[Issue-385](https://github.com/MadaraUchiha-314/the-loop/issues/385) asks for
[graphify](https://github.com/Graphify-Labs/graphify) to run on every merge to `main` and
for the asset `/graphify .` produces to be pushed back into the repository, and asks three
questions: how to get Claude or Codex into a GitHub Actions job, how to provide the token,
and how the generated files get back into the repository.

graphify's README and its source disagree about what the tool can do, so the decisions
below rest on the source of `graphifyy` 0.9.64 and on running it against this tree:

- `/graphify .` is a **skill** — a markdown script the assistant follows, dispatching
  subagents for the document extraction. Underneath it is a Python library with a
  **headless CLI**: `graphify extract <path> --backend claude` runs the same pipeline
  end to end, calling the Anthropic Messages API through the official SDK with
  `ANTHROPIC_API_KEY`. The skill's own text says it "does not read `ANTHROPIC_API_KEY`";
  that sentence is about the interactive path and is false for the CLI.
- code is extracted by tree-sitter with no model; documents and images need one. This
  repository is 405 code files and 1,273 documents (2.4 million words) plus 77 images.
- the output is large and unstable: `graph.json` is 19–32 MB and community detection
  renumbers on every run, so a rebuild rewrites most of it (about 0.4 MB of git pack per
  run after delta compression).
- `graphify extract` is incremental against a committed `graph.json` + `manifest.json`,
  and additionally against a semantic cache under `graphify-out/cache/`.

## Decision

| # | What was chosen | Why |
|---|-----------------|-----|
| D1 | **Headless `graphify extract` in the job, `--backend claude`, no Claude Code or Codex CLI installed.** | It is the same library the skill drives, minus the assistant in the middle: one deterministic process, one credential, exit codes a workflow can act on. Installing Claude Code to run `/graphify .` would add a second install, a second authentication path, an agent whose steps are prose, and subagent fan-out billed per turn — for the same graph. The recipe for that path is recorded below for anyone who wants it. |
| D2 | **The credential is `ANTHROPIC_API_KEY`, from a secret on a GitHub environment named `graphify`, read by one job that runs only on `push` to `main` and `workflow_dispatch`.** | An environment secret can be restricted to deployments from `main`, which a repository secret cannot; and a job that never runs for `pull_request` cannot be made to leak the key by a pull request that edits the workflow — GitHub's rule that fork pull requests receive no secrets stands behind that. |
| D3 | **The asset is committed to `main` by the job, through `scripts/graphify-commit.sh`, with `GITHUB_TOKEN`.** | It is what the ticket asked for, and it is how the release workflow already lands its `bump:` commit. A `GITHUB_TOKEN` push starts no workflow, so the commit triggers neither CI, nor the release, nor another rebuild — the loop-safety property comes from the platform, not from a marker in the commit message. The script rebases onto the remote tip and retries with backoff because the release workflow pushes to `main` on its own schedule; it never forces and it fails on a real conflict. |
| D4 | **The tracked files are `graph.json`, `GRAPH_REPORT.md`, `graph.html`, `manifest.json` and the community labels; the AST cache, the machine-naming sidecars and the dated backups are ignored; the semantic cache rides GitHub's Actions cache, not git.** | The tracked set is what a reader or a query needs and what the next run needs as its baseline. The AST cache is regenerated in forty seconds, the sidecars carry absolute runner paths, and a backup copy of a 30 MB file per run is the one thing a repository must not accumulate. The semantic cache holds the model's answers per content hash — worth keeping between runs, not worth a commit each. |
| D5 | **The model is pinned explicitly (`GRAPHIFY_MODEL`, `claude-opus-5`) rather than left to graphify's default.** | graphify's default is a previous-generation id; an explicit pin makes a model change a reviewed one-line diff, and the cost estimate in the spec is for a named model. Sonnet 5 is the same edit at about a third of the cost. |
| D6 | **A pull request that changes the pipeline rehearses the no-model half; every other pull request runs nothing.** | The workflow cannot otherwise be exercised before it reaches `main`. Running graphify on every pull request would add forty seconds to each and prove nothing new. |
| D7 | **The generated report is excluded from markdownlint; the source is linted, not the output.** | The same rule the synced reference copy already follows. |

## Consequences

**Good.** Every merge to `main` leaves a current graph behind and nobody runs anything;
`graphify query` works on any fresh checkout; the questions the ticket asked have
answers in the repository. The credential and the write grant sit in one job on one event.

**Costs, accepted.** The repository grows by roughly 0.4 MB of pack per merge and every
checkout carries a 20–30 MB JSON file. The first full run costs on the order of $20–30
of Opus 5 tokens (a third on Sonnet 5), later runs the changed documents. `main`'s tip
is a bot commit after every merge, so "the last commit on main" is no longer the merged
change — the merge is one behind. The rebuild job has write access to `main`; it is
scoped to `graphify-out/` by the script, not by the platform.

## Alternatives considered

| Alternative | Why not |
|-------------|---------|
| **Install Claude Code in the job and run `claude -p "/graphify ."`** — `curl -fsSL https://claude.ai/install.sh \| bash` (or `npm install -g @anthropic-ai/claude-code`), then `claude --bare -p "/graphify ." --allowedTools "Bash,Read,Write" --permission-mode dontAsk --max-turns 50 --output-format json` with `ANTHROPIC_API_KEY` (a Console key) or `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`, a one-year subscription token) in the environment; or the official `anthropics/claude-code-action@v1` with `anthropic_api_key:` and a `prompt:`. | It runs the same library through an agent reading a markdown script, with subagent fan-out for the documents. Non-deterministic step count, per-turn billing on top of the extraction tokens, and a second toolchain to pin. The CLI path is the library's own headless mode, documented for exactly this ("Headless full-pipeline extraction for CI / scripts", cli.py). Recorded here because it is the literal reading of the ticket and it does work. |
| graphify's `claude-cli` backend (`--backend claude-cli`, routes each chunk through `claude -p` and a subscription) | The same second toolchain, for subscription billing that CI cannot log in to without a long-lived token. |
| Commit the graph to an orphan branch (`graphify`), force-pushed, one commit deep | Keeps `main`'s pack from growing and the working tree small, at the price of the graph not being in a checkout — `graphify query` and the skill's fast path both look for `graphify-out/graph.json` in the working directory, and a contributor would have to fetch a branch to get it. The ticket asked for the asset in the repository; this is the fallback if the pack growth becomes a problem. |
| Publish to GitHub Pages instead of git | `graph.html` and the report would be one URL, but nothing on disk for queries, and the docs deployment is path-filtered and single-artifact (docs.yml) — a third build in it is its own work item. Listed as a follow-up. |
| A workflow artifact or a release asset | Expires (artifacts) or is bound to a version (releases); neither is "the graph for this commit of main". |
| Commit the semantic cache too | 4 MB of model answers per run, on top of the graph. `actions/cache` keeps it between runs at no cost to the repository; if it expires, the manifest still gates re-extraction and the worst case is one fuller run. |
| `--code-only` on `main` too (no model, no key, no cost) | Leaves 1,273 documents — the bulk of this repository — out of the graph. The ticket's premise is that the LLM pass is the point. |
| Skip the `pull_request` rehearsal | A workflow that can only be tested by merging it is the class of change that ships broken. |
