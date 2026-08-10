---
type: execution-log
workItem: issue-193
phase: needs-review
status: in-progress
---

# Execution Log: a default harness config for repositories that never adopted the-loop

> Append-only log for issue-193. Ticket:
> [#193](https://github.com/MadaraUchiha-314/the-loop/issues/193).

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-10 | @MadaraUchiha-314 (out of band) | The owner assigned this ticket directly to a cloud session rather than through the daemon, so no checklist was posted on the ticket and no `the-loop execute` reply exists. The full process was run — no phase was declared away, and the harness declared none. |
| requirements-definition | 2026-08-10 | | `requirements.md` locked — four requirements: the built-in default, the ingress adopting, the CLI's mutating verbs adopting, and the contribution loop never adopting its host. |
| design | 2026-08-10 | | `design.md` locked. One data file, one writer, two call sites, one carve-out; the load-bearing choice is adopting *after* the ownership proof and *before* the spec-directory gate, so the config is written even on the run whose graph is skipped. |
| test-planning | 2026-08-10 | | `testing-plan.md` locked — 13 rows, 6 `n/a` with reasons. |
| tasks-breakdown | 2026-08-10 | | `tasks.md` locked — 9 tasks, DAG drawn. |
| implementation | 2026-08-10 | | Tasks 1–8. |
| verification | 2026-08-10 | | Plan executed; results and evidence recorded. |
| needs-review | 2026-08-10 | | Self-review; awaiting the human gate on the PR. |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| MadaraUchiha-314/the-loop — `claude/github-issue-193-x96m3i` | the whole work item (tasks 1–9) | open |

## Progress entries

### 2026-08-10 — spec chain

- **Phase:** requirements-definition → design → test-planning → tasks-breakdown
- **Did:** Read the ticket, the harness-config read surface (issue-121/decision-044), the
  ingress→graph coupling and issue-185's uninitialized-repository rules, then wrote and
  locked the four spec artifacts. The design question that took the time: adopting a
  repository is exactly what PR #187 forbade for a *contribution*, so the two had to be
  told apart rather than reconciled — the carve-out is R4 and it is enforced at both call
  sites.
- **Checkpoint/tests:** none yet (no code).
- **Next:** implement tasks 1–8.

### 2026-08-10 — implementation

- **Phase:** implementation
- **Did:** Tasks 1–8. The packaged default (`cli/the_loop/harness-config.default.yaml`,
  a byte-for-byte copy of the `/the-loop:init` template); `defaults()`,
  `default_config_path()` and `scaffold()` in `harness_config.py` — the only writer, with
  the provenance header, the `ticketing.github` substitution and its allow-list; the
  `harness.config_scaffolded` event; `GraphLink._adopt` on the ingress path, with the
  outer-loop resolution hoisted so the contribution carve-out and the runtime build share
  one answer; `core.graphs._runtime(adopt=...)` passed by the four state-changing verbs
  and by no reader; the parity assertions (byte parity with the template, the schema via
  `scripts/validate_config.py`, the phase sequence via `test_graph_parity.py`'s
  parametrization, and the surviving per-key literals pinned to the packaged file); and
  the documentation, capability rows and decision-073.
- **Checkpoint/tests:** red→green on all 26 new tests (18 unit, 7 integration, 1 parity
  parametrization); `make test` — 1712 passed, 1 skipped. No existing test needed
  changing: adoption writes only where the ownership proof already passed, and the
  checkouts existing tests build either carry a config or are foreign.
- **Next:** verification (task 9).

### 2026-08-10 — self-review and the security gate

- **Phase:** needs-review
- **Did:** Three self-review rounds over the diff, then the security review. Round 1 found
  that adoption ran on **all four** `_guarded` actions, including `context` — which is
  documented as mutating nothing and runs before every delivery — and `clean`, which runs
  while the checkout is being released; bounded it to `{start, advance}` and added two
  scenarios. Round 2 replaced a duplicated path expression in the event with
  `config_path()`, and dropped a redundant `deepcopy` in `defaults()`. Round 3 found
  nothing new, so the rounds stopped there (`reviews.stopOnNoNewFindings`). The security
  review then found one real issue — see the gate below.
- **Checkpoint/tests:** `make test` 1715 passed, 1 skipped; `make lint format-check
  typecheck validate` clean.
- **Next:** the reviewer briefing on the PR, then the human gate.

### 2026-08-10 — verification

- **Phase:** verification
- **Did:** Executed `testing-plan.md` — every activity in the matrix, none replanned —
  and committed the evidence under `evidence/`.
- **Checkpoint/tests:** T1/T2/T7/T8/T10 targeted runs, `make test` (1712 passed, 1
  skipped), `make lint format-check typecheck validate` (ruff clean, 523 markdown files
  0 errors, pyright 0 errors, 7 configs VALID).
- **Next:** self-review, the security review gate, then the reviewer briefing on the PR.

### 2026-08-10 — PR review round 1

- **Phase:** needs-review
- **Did:** Three review comments from @MadaraUchiha-314 on the packaged default, all
  applied to **both** copies (`skills/the-loop/templates/harness-config.yaml` and
  `cli/the_loop/harness-config.default.yaml` — byte parity is the point of the pair):
  `repository.monorepo` `true → false`, `monorepoTool` `nx → none`, and the
  `externalTools` GitHub entry flipped so the **`gh` CLI** is the live default and the
  GitHub MCP server is the commented alternative. The first two also settle a
  contradiction the reference already carried — `reference/tooling.md` says "never assume
  a workspace tool exists" while the shipped default assumed Nx — so that bullet was
  corrected in the same commit.
- **Checkpoint/tests:** `make test` 1715 passed, 1 skipped; `make lint` 0 errors; all 7
  configs `VALID`. The scope note: these edits change what `/the-loop:init --defaults`
  writes for **every** project, not only what a scaffolded repository gets.
- **Next:** the human gate on the PR.

## Verification results

> Only when this work item declared `test-planning` away. It did not: the results live in
> [`testing-plan.md`](testing-plan.md) § Verification results, against the matrix rows
> that planned them.

## Design critic review

> Not selected. `design-critic-review` is opt-in (issue-188) and this work item did not
> tick it.

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | the-loop (this session) | new findings — adoption ran on the read-only `context` action and on `clean`; bounded to the two actions that drive the graph, two scenarios added | [`design.md` § graphlink](design.md) |
| 2 | self | the-loop (this session) | new findings — the event duplicated the config path expression (now `config_path()`); a redundant `deepcopy` in `defaults()` | commit `dc319ba`+ |
| 3 | self | the-loop (this session) | zero (converged) — rounds stopped here per `reviews.stopOnNoNewFindings` | — |
| 4 | critic | — | unavailable — `reviews.critics` is empty in this project's config, so no critic harness is configured to run. Does NOT count toward `reviews.criticReviewCount` | [`.the-loop/harness-config.yaml`](../../../.the-loop/harness-config.yaml) |
| 5 | security | the-loop `security-review` skill | new findings — one MEDIUM (see the gate below), fixed with `_inside()` and a negative test; re-run clean | [`design.md` § Security design](design.md) |

## Security review (gate)

- **Mechanism:** the built-in `security-review` skill (`security.review.mechanism: auto`
  resolves to it when available). Its prescribed sub-agent fan-out was not used — this
  session runs under an environment rule against spawning agents — so the analysis was
  performed directly over the work item's diff, which is the same diff the fan-out would
  have read.
- **Outcome:** **findings fixed.** One MEDIUM: `scaffold()` wrote to
  `<root>/.the-loop/harness-config.yaml` without resolving it. The *name* is a constant,
  but a cloned checkout carries whatever its contributors committed — a `.the-loop`
  committed as a **symlink** would have redirected `mkdir(exist_ok=True)` + `write_text`
  to a directory the repository chose, planting a `harness-config.yaml` outside the
  checkout. Fixed by `harness_config._inside()`, which resolves both paths and fails
  closed, mirroring `graphlink._is_contained`; pinned by
  `test_scaffold_refuses_a_the_loop_directory_that_escapes_the_checkout` and recorded as
  requirements abuse case 5. Nothing else reached the reporting bar: the write target has
  no payload-derived path component, `owner`/`repo` are allow-listed against GitHub's
  charset and dropped rather than escaped, an existing config is never opened, and the
  written content is the-loop's own packaged bytes.
- **Human sign-off:** n/a — risk tier 3, below `security.review.humanSignOffMinTier: 4`

## Final validation evidence

Every acceptance criterion is met and proved by a committed run under
[`evidence/`](evidence/); [`testing-plan.md`](testing-plan.md) § Verification results maps
each activity to its command, outcome and evidence file.

| Requirement | Proved by |
|---|---|
| R1 — one built-in default, shipped in the package, equal to the `/the-loop:init` template and valid against the schema | `test_defaults_reads_the_packaged_configuration`, `test_the_packaged_default_is_the_shipped_template`, `test_the_packaged_default_agrees_with_the_per_key_fallbacks`, `test_p4_the_graph_defines_the_phase_sequence[packaged-default]`, and `scripts/validate_config.py` reporting it `VALID` in its own right |
| R2 — the ingress adopts, names the repository, records the event, never overwrites, never fails a delivery | `test_the_ingress_adopts_a_repository_that_never_ran_the_setup`, `test_a_repository_is_adopted_even_when_its_graph_is_skipped`, `test_an_adopted_repository_is_left_alone_on_every_later_event`, `test_scaffold_degrades_when_it_cannot_write` |
| R3 — mutating graph verbs adopt; reads do not | `test_a_mutating_graph_verb_adopts_the_repository`, `test_a_read_only_command_writes_nothing`, plus the two self-review scenarios for `context` and `clean` |
| R4 — a contribution never adopts its host repository | `test_a_contribution_never_adopts_its_host_repository`, with issue-185's own suite still green in `make test` |
| Abuse cases 1–5 | the T8 selection — 10 tests, all passing |

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`webhook-triggers.md`](../../capabilities/webhook-triggers.md) | New *Current behaviour* bullet under the graph-coupling section: the ingress adopts an unconfigured repository — where in the gate order, what it writes, and the three limits (after the ownership proof, before the spec-directory gate, never for a contribution) | `issue-193` row added at the top of § History |
| [`process-graph.md`](../../capabilities/process-graph.md) | Two edits: the CLI half — state-changing graph verbs adopt, reads never do — as a new bullet under *What drives the graph*, and the contribution loop's *need not have adopted the-loop* bullet now says explicitly that it must not adopt it either | `issue-193` row added at the top of § History |

## Documentation

| Document | What changed |
|----------|--------------|
| [`docs/config/harness-config.md`](../../config/harness-config.md) | New section *When a repository has no config*: what the built-in default is, the table of which surfaces adopt and which do not, the provenance header and the event, that an existing config is never opened, and that nothing about the repository is detected |
| [`skills/the-loop/reference/automation.md`](../../../skills/the-loop/reference/automation.md) | New bullet in the CLI-companion section — the rule as an agent working under the-loop meets it, with its three limits |
| [`skills/the-loop/SKILL.md`](../../../skills/the-loop/SKILL.md) | Two sentences in § Configuration: an unconfigured repository is worked under the built-in default, which is written to disk rather than assumed |
| [`docs/decisions/decision-073.md`](../../decisions/decision-073.md) + [`decisions.md`](../../decisions/decisions.md) | New decision record and its index row |
| [`skills/the-loop/reference/tooling.md`](../../../skills/the-loop/reference/tooling.md) | The monorepo bullet no longer says the default is Nx — the shipped default is now `monorepo: false` / `monorepoTool: none` (PR #195 review), which is what the next bullet's "never assume a workspace tool exists" always implied |
| `README.md`, the rest of the docs site | Unchanged, and deliberately: the front page describes the loop's *process*, which this work item does not touch — it changes what happens in a repository that has not configured that process |
