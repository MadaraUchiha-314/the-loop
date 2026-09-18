---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#382"
---

<!-- Authored per the the-loop:writing skill. -->

# Final validation: the poll clocks are this machine's, not the repository's

> Testing-plan rows T8 and T14 — the whole toolchain the way CI runs it, and the property
> the ticket asked for, measured on this repository's own tracked state directory.

## T8 — `make check`

```text
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
Linting: 1216 file(s)
Summary: 0 error(s)
uv run ruff format --check cli hooks
319 files already formatted
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
3968 passed, 1 skipped in 195.12s (0:03:15)
```

Lint, format, types, config validation and the full suite, green. The skip is the suite's
existing one, unrelated to this work item.

## T14 — the dogfood

The ticket's complaint is about a working tree, so the proof is a working tree — this
checkout's own `.the-loop/`, which is where the-loop dogfoods its state.

Five `PollState` cycles over the repository's real portable directory, each with a new
clock a minute later, starting from a clean `git status`:

```text
after cycle 1 (the poller learned the thread):
.the-loop/portable/github-octo-repo-15.json | 8 ++++++++
 .the-loop/portable/index.json               | 3 ++-
 2 files changed, 10 insertions(+), 1 deletion(-)
  git status: M .the-loop/portable/github-octo-repo-15.json
 M .the-loop/portable/index.json

after four more cycles, each with a new clock:
.the-loop/portable/github-octo-repo-15.json | 8 ++++++++
 .the-loop/portable/index.json               | 3 ++-
 2 files changed, 10 insertions(+), 1 deletion(-)
  same diff as after cycle 1: True
  git status: M .the-loop/portable/github-octo-repo-15.json
 M .the-loop/portable/index.json

the clocks, meanwhile:
  { "clocks": { "github:octo/repo#15": { "lastPolledAt": "2026-09-18T10:05:00Z" } } }
  ignored by git: .gitignore:233:.the-loop/local/  .the-loop/local/poll-clocks.json
```

Cycle 1 changes the record because the poller genuinely learned something — it had never
seen this thread — and what it wrote carries no timestamp:

```json
"poll": {
  "seenComments": ["IC_1"],
  "commentAttempts": {},
  "spawn": {},
  "gaveUp": {}
}
```

Cycles 2 to 5 change **nothing**: the diff after the fifth is byte-identical to the diff
after the first, while `poll-clocks.json` advanced to `10:05:00Z` under a path git
ignores. Before this change every one of those four cycles would have rewritten the record
and the index with a new `lastPolledAt` — which is the annoyance
[issue-382](https://github.com/MadaraUchiha-314/the-loop/issues/382) reports.

The checkout was restored afterwards (`git checkout -- .the-loop/portable`, and the
generated clock file removed), so this work item's diff carries none of it.

**Not run, and why:** the planned form of T14 was two `the-loop poll --once` cycles. This
container has no `gh` binary and this repository declares `polling.sources: []` (it
dogfoods webhooks, not polling), so a live cycle cannot run here. The replanned form above
exercises the same code — `PollState` over the same directory, the same
`finalize`/`save` path a cycle takes — with the provider's answers left out, which is the
only part the property does not depend on. The provider-driven path is covered by T4's
integration scenarios against a fake GitHub.
