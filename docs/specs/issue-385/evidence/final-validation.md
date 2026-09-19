---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#385"
---

<!-- Authored per the the-loop:writing skill. -->

# Final validation: the repository carries its own knowledge graph

> Testing-plan rows T6, T7 and T8 — the whole toolchain the way CI runs it, the
> rehearsal job on this pull request, and the one activity that cannot run before merge.

## T8 — `make check`

```text
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
Linting: 1249 file(s)
Summary: 0 error(s)
uv run ruff format --check cli hooks
321 files already formatted
uv run pyright cli
0 errors, 0 warnings, 0 informations
uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
uv run --project cli python -m pytest -q cli
4005 passed, 1 skipped in 181.77s (0:03:01)
```

Lint (including the 1,249 markdown files, the new ones among them), format, types,
config validation and the full suite, green. The skip is the suite's existing one,
unrelated to this work item. The seventeen new tests are the two suites in
`evidence/unit.md` and `evidence/integration.md`.

The documentation site was built as well, since the Pages workflow only runs on `main`:

```text
cd docs && bun install --frozen-lockfile && bun run docs:build
build complete in 133.37s.
```

One lint round was red on the way: the `du -sh` output pasted into `evidence/pipeline.md`
carried hard tabs (MD010), replaced with spaces.

**A defect of this session's own, found and undone:** the pipeline evidence was first
written through an unquoted shell heredoc, and one unescaped backticked phrase in it —
`graphify update .` — ran as a command substitution in the repository root, leaving a
70 MB `graphify-out/` behind (the generated files, exactly the tracked set the design
describes, plus the cache). The directory was removed before the commit; the evidence
file was restored to the intended text; nothing generated is in this pull request.

## T6 — the `dry-run` job on this pull request

The workflow's own `pull_request` trigger fires for this PR because it changes both
pipeline files. The job installs the pinned `graphifyy` with the Anthropic SDK on
`ubuntu-latest`, runs `graphify extract . --code-only` and `graphify cluster-only .
--no-label`, and uploads `GRAPH_REPORT.md` as a workflow artifact. Its result is the
*Knowledge graph / Rehearse (AST only, nothing pushed)* check on the pull request; it is
recorded here once it completes.

**Result:** passed on the pull request's first head (run
[35455212839](https://github.com/MadaraUchiha-314/the-loop/actions/runs/35455212839),
job *Rehearse (AST only, nothing pushed)*, 16:31:41 → 16:32:20 UTC, 39 s), while the
`rebuild` job for the same event reported *skipped* — the `pull_request` condition
holding on a real runner. The `checks` job on that head was red for two reasons recorded
in `evidence/unit.md` (the runner's `GITHUB_SHA` reaching the scenarios; `main`'s stale
`uv.lock`), both fixed in the next push.

## T7 — the first real rebuild on `main`

**Not executed here.** The job runs on `main` only, by design (requirement 3.1), with a
secret this container does not hold and only the owner can add. The step that verifies
it, after merge:

1. Settings → Environments → `graphify` (created on the workflow's first run, or create
   it) → add the environment secret `ANTHROPIC_API_KEY`; restrict deployment branches
   to `main`.
2. Actions → *Knowledge graph* → *Run workflow* on `main`.
3. Expect: a `chore(graphify): rebuild the knowledge graph for <sha>` commit on `main`
   carrying `graphify-out/`; the job log's last lines name the token count and cost
   estimate. A red job leaves `main` untouched.

What stands in for it until then is T5 (`evidence/pipeline.md`): the same two commands on
a clone of this tree against a fake of the Messages API — three runs, the incremental
claim measured rather than asserted.
