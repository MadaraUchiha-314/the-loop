---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#331"
phase: needs-review
status: in-progress
---

# Execution Log: a poll source's bare `OWNER/REPO` is on the GitHub the-loop resolves

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-09-09 | — | Tier 3 (`human-approves-pr`; below `humanSignOffMinTier: 4`): no schema, workflow or config-key change; an already-validated host reaches one more constructor through the same grammar. Brainstorming skipped: the ticket's root cause is confirmed and it names both fix directions. No authorized `the-loop execute` reaches this cloud session, so the selection is recorded here and every phase is walked |
| requirements-definition | 2026-09-09 | | [`bugfix.md`](bugfix.md) — two requirements, four abuse cases |
| design | 2026-09-09 | | [`design.md`](design.md) — the host decided once, where the source is built; [`decision-114`](../../decisions/decision-114.md) |
| test-planning | 2026-09-09 | | [`testing-plan.md`](testing-plan.md) — thirteen rows, six applicable |
| tasks-breakdown | 2026-09-09 | | [`tasks.md`](tasks.md) — four tasks |
| implementation | 2026-09-09 | | On `claude/github-issue-331-ahsinr` — tasks 1–3 |
| verification | 2026-09-09 | | [`evidence/verification.md`](evidence/verification.md) — rows T1, T2, T8, T10, T12; [`evidence/security-review.md`](evidence/security-review.md) — four abuse cases, four closed |
| needs-review | 2026-09-09 | | PR raised; awaiting the owner (tier 3: `human-approves-pr`) |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| (raised from this branch — see the ticket) | tasks 1–4: the whole work item | open |

## Progress entries

### 2026-09-09 — implemented, verified, ready for review

- **Phase:** implementation → verification → needs-review
- **Did:** tasks 1–4, red first (the 17 new tests were run against the unchanged source
  and fail there — the red block in [`evidence/verification.md`](evidence/verification.md)).
  `RepoSpec.parse` / `parse_repos` take a `default_host` that a bare entry inherits
  through the one normalisation and the one grammar; `PollProvider.from_source` and
  `build_provider` carry it; the daemon's new `_build_providers(data, default_label=…)`
  resolves the host with `ghhost.github_host` over the loaded CLI config and serves the
  pre-flight, the first plan and the reloader; `describe()` spells `gh_repo`. The docs
  (polling options, integrations options, concepts, the config template comment), the
  capability doc's rule and history row, and decision-114.
- **Checkpoint/tests:** `make check` — see `evidence/verification.md`. Existing
  assertions changed: none. Two test helpers gained a parameter
  (`test_poller_integration.py`'s `_make(default_host=…)` and `GhState.argv`).
- **Self-review:** three passes over the diff. Pass one: the daemon helper read the
  config file itself, so `build_plan()` read it twice per plan and the test needed a
  temp file — it now takes the loaded mapping (pure, one read per call site); a
  redundant `!= github.com` clause beside `is_github_host` (which already matches it);
  a docstring reference split across a line. Pass two: two pyright findings in the new
  test (an inferred dict type, `repos` on the base class) — fixed. Pass three: nothing
  new. Observation, out of scope: the full suite leaves a fixture record under
  `.the-loop/portable/` in the checkout (a pre-existing leak from a test that uses
  `RoutingConfig`'s default portable directory); removed before committing, not fixed
  here.
- **Next:** the owner's review.
- **Blockers:** none.

### 2026-09-09 — spec chain drafted

- **Phase:** requirements-definition → tasks-breakdown
- **Did:** read `RepoSpec` / `parse_repos` / `from_source` / `owns` / `_scope` /
  `scope_of` in `poller/github.py`, `PollProvider.from_source` / `build_provider` in
  `poller/base.py`, `_reconcile_closures` in `poller/poller.py`, the daemon's
  pre-flight and `build_plan()` in `poller/daemon.py`, and `ghhost.github_host` at
  `6035e50`; confirmed the ticket's root cause and its second, quieter consequence (a
  source configured through `integrations.github.host` alone listed github.com). Wrote
  the four artifacts and the decision.
- **Checkpoint/tests:** baseline — `test_poller.py` green (187).
- **Next:** task 1, red first.
- **Blockers:** none.

## Verification results

> Only when this work item declared `test-planning` away. It did not: results live in
> [`testing-plan.md`](testing-plan.md).

| What was verified | Command | Outcome | Evidence |
|-------------------|---------|---------|----------|
| — | — | — | see `testing-plan.md` |

## Design critic review

> Not selected for this work item.

| Round | Critic (`<harness>/<model>`) | Outcome | Findings → disposition | Link |
|-------|-----------------------------|---------|------------------------|------|
| | | | | |

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self (diff) | the-loop (this session) | new findings — the daemon helper's double read and file-bound test, a redundant clause, a split docstring: fixed | this log |
| 2 | self (diff + types) | the-loop (this session) | new findings — two pyright errors in the new test: fixed | this log |
| 3 | self (diff) | the-loop (this session) | zero (converged) | this log |
| — | critic | — | unavailable — `reviews.critics` is empty in this repository's config; does not count toward `criticReviewCount` | — |
| 4 | security | the-loop checklist | pass — four abuse cases, four closed | [`evidence/security-review.md`](evidence/security-review.md) |

## Security review (gate)

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`; no security-review
  skill is invocable from this session's plugin set)
- **Outcome:** pass — [`evidence/security-review.md`](evidence/security-review.md)
- **Human sign-off:** n/a (tier 3, below `security.review.humanSignOffMinTier: 4`)

## Final validation evidence

| Requirement | Proof |
|-------------|-------|
| R1.1, R1.3 a bare entry inherits; a written host wins | `test_repospec_inherits_a_default_host_unless_it_names_its_own`, `test_provider_from_source_binds_bare_repos_to_the_default_host`, `test_build_provider_carries_the_default_host` |
| R1.2 github.com unwritten, byte-identical | `test_a_github_com_default_leaves_the_spec_unwritten`; the issue-311 host tests and every pre-existing poller test unchanged |
| R1.4 every read, the scope and `owns()` name the inherited host | `test_a_bare_repos_reads_go_to_the_inherited_host`, `test_a_bare_repo_inherits_the_default_host_and_owns_its_refs` |
| R1.5 resolved at start and on reload | `test_the_daemon_binds_sources_to_the_resolved_host` ×4 (one helper, called by the pre-flight, `build_plan()` and the reloader) |
| R1.6 the description names the host | `test_describe_names_the_host_a_source_is_bound_to` |
| R2.1 the ticket's regression | `test_a_bare_repo_inherits_the_default_host_and_owns_its_refs` (red before the fix) |
| R2.2 end to end through `poll_once` | `test_a_closed_item_on_a_bare_enterprise_source_is_reconciled` |
| A1–A3 | `evidence/security-review.md` |

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`cli.md`](../../capabilities/cli.md) | the ref rule: a poll source's bare `OWNER/REPO` is on the host the one resolver answers, decided when the source is built, at start and on every reload | issue-331 row |

## Documentation

| Document | What changed |
|----------|--------------|
| `docs/config/cli/polling-options.md` | `sources[].repos`: what a bare `OWNER/REPO` is on, and that the startup line shows it |
| `docs/config/cli/integrations-options.md` | `github.host` also answers for a poll source's bare entries |
| `docs/cli/concepts.md` | one sentence: a poll source's bare entry is on the same resolved host |
| `skills/the-loop/templates/cli-config.yaml` | the `repos` comment: `[HOST/]OWNER/REPO`, and where a bare entry is |
| `docs/decisions/decision-114.md`, `decisions.md` | the decision and its index row |
| `README.md`, `skills/the-loop/SKILL.md` | unchanged — neither describes poll sources or hosts |
