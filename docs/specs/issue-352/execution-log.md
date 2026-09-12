---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#352"
phase: needs-review
status: in-progress
---

# Execution Log: the harness config is the agent's alone — the CLI reads no key of it

> Append-only log for issue-352. Ticket:
> [#352](https://github.com/MadaraUchiha-314/the-loop/issues/352). Pull request:
> [#353](https://github.com/MadaraUchiha-314/the-loop/pull/353).

## How this session ran the loop

One cloud session, two passes. The first pass was the **audit** the ticket asked for
(tier 2, documentation only): `docs/reports/harness-config-audit.md`, a requirements
record, this log. The owner's review of that PR redirected the work item into a
**breaking change** — *"the CLI shouldn't read any of the harness config … Make this
breaking change"* — and the second pass is that change, re-tiered to **4**. No
authorized `the-loop execute` reaches a cloud session, so `phase-selection` was recorded
on the ticket and on the PR rather than answered as a gate; the owner's review is the
human decision the loop records.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-09-11 | — | Pass 1: tier 2, audit only. Pass 2 (2026-09-12): tier 4 after the owner's review on PR #353; full chain, named security sign-off = the owner's PR approval |
| requirements-definition | 2026-09-11 / 2026-09-12 | | [`requirements.md`](requirements.md) — rewritten for the breaking change: five requirements, six abuse cases |
| design | 2026-09-12 | | [`design.md`](design.md) — thirteen design points; [`decision-123`](../../decisions/decision-123.md) supersedes decision-044 |
| test-planning | 2026-09-12 | | [`testing-plan.md`](testing-plan.md) — thirteen rows, eleven applicable |
| tasks-breakdown | 2026-09-12 | | [`tasks.md`](tasks.md) — twelve tasks |
| implementation | 2026-09-12 | | On `claude/github-issue-352-un79kv` |
| verification | 2026-09-12 | | [`evidence/verification.md`](evidence/verification.md); [`evidence/security-review.md`](evidence/security-review.md) — six abuse cases, six closed |
| needs-review | 2026-09-12 | | PR #353 updated; awaiting the owner (tier 4: PR approval is the sign-off) |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#353](https://github.com/MadaraUchiha-314/the-loop/pull/353) | pass 1 (the audit) and pass 2 (tasks 1–12, the whole work item) | open |

## Progress entries

### 2026-09-11 — orientation and the audit

- **Phase:** requirements-definition → implementation → needs-review (pass 1)
- **Did:** read the ticket, `CLAUDE.md`, the skill, `harness_config.py` and its test,
  decision-032 and decision-044, the config reference, the schema's onboarding groups,
  the five shipped graphs, the hooks and the Cursor rule. Searched the skill, the commands
  and the CLI for every top-level schema key. Wrote the audit report with a 34-row per-key
  verdict table; registered it in the reports index and sidebar; raised PR #353.
- **Findings that mattered later:** the CLI read exactly eight keys through one module;
  `workflow.phases` was a mirror the parity test kept faithful; `reviews.critics[]`
  described the operator's machine; the CLI validated a repository's file against nothing
  at run time; the Cursor rule still looked for the pre-rename filename.

### 2026-09-12 — the owner's review, and the breaking change

- **Phase:** needs-review → requirements-definition → … → needs-review (pass 2)
- **Decision recorded:** the owner's review on PR #353 — remove most of the harness
  config, the CLI reads none of it, the skill tells the harness, make it breaking — with
  six inline rulings on the per-key table. Acknowledged on the PR with the key-by-key
  disposition before any code changed.
- **Did (tasks 1–12):**
  - Deleted `harness_config.py`, `harness-config.default.yaml`, adoption
    (`graphlink.adopt/_adopt/_write_default`, the dispatcher's calls, the scaffold in
    `core.graphs`) and `harness.config_scaffolded`.
  - `graph/bootstrap.py`: `resolve_spec_root`, `load_cli_config_best_effort`,
    `build_runtime(origin_repo=…)`, `guestLoop`, `originRepo` from the argument or
    `ghhost.origin_repo`; `PHASE_LABEL_PREFIX` constant; `notify` roles from params.
  - `graph/extensions.read_declaration` on `routing.graph.hooks`;
    `load_graph(declaration=…)`; `graph hooks` reports the CLI config.
  - `critics.load_critics(config_path)` from the CLI config, strictly; `core.repo`
    rewritten; `scenarios --glob`, `instructions --doc`/`--on-missing` (path or JSON);
    `--spec-dir` on `check`/`graph` through core, API bodies and the SDK.
  - Schemas: harness minus nine keys, groups rewritten, `0.3.0`; CLI with `critics`,
    `routing.graph.hooks`, `specDir` default, no `repoHooks`, `0.9.0`; packaged copies;
    `migrations._retire_repo_hooks`.
  - Configs, templates, `validate_config.py`, `hooks.json`, `rules/the-loop.mdc`.
  - Tests: two files deleted, twenty-three rewritten or touched; fixtures to `0.9.0`.
  - Skill and commands: `SKILL.md` § Configuration (the key → flag table), seven
    reference files, nine commands including `init` (labels from the graph) and
    `upgrade-the-loop` (the `0.3.0`/`0.9.0` migration).
  - Docs: the config reference rewritten, `critics-options.md`, `routing-options.md`,
    `migrate-config.md`, five command pages, the hooks guide, CLI concepts and index,
    six capability docs with history rows, decision-123, decision-044 superseded, the
    audit's outcome note, `cli/README.md`, the labels report.
- **Checkpoint/tests:** `make check` green on the PR head — 3492 passed, 1 skipped; ruff,
  pyright and markdownlint clean (`evidence/verification.md`).
- **Capability docs:** `cli`, `process-graph`, `review-loop`, `webhook-triggers`,
  `spec-workflow`, `testing-and-contracts`, `channels` updated in this PR.
- **Next:** the owner's review of PR #353 (tier 4: their approval is the sign-off).
- **Blockers:** none.
