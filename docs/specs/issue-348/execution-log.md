---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#348"
phase: needs-review
status: in-progress
---

# Execution Log: one top-level `repositories` bounds every ingress

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-09-11 | — | Tier 4: `autonomy.sensitivePaths` matches `**/*schema*`, so `human-approves-pr` **and** `security.review.humanSignOffMinTier: 4` — a named human security sign-off, recorded as outstanding. Brainstorming skipped: the ticket carries the ask, the shape (decided on PR #347), the current code and the reasoning. No authorized `the-loop execute` reaches this cloud session, so the selection is recorded here and every remaining phase is walked |
| requirements-definition | 2026-09-11 | | [`requirements.md`](requirements.md) — five requirements, nine abuse cases, a before/after threat model of the receiver |
| design | 2026-09-11 | | [`design.md`](design.md) — `the_loop/repos.py`, the router bound, the poller seam, the migration; [`decision-121`](../../decisions/decision-121.md) |
| test-planning | 2026-09-11 | | [`testing-plan.md`](testing-plan.md) — sixteen rows, eight applicable |
| tasks-breakdown | 2026-09-11 | | [`tasks.md`](tasks.md) — eleven tasks |
| implementation | 2026-09-11 | | On `claude/github-issue-348-vx9u2l` |
| verification | 2026-09-11 | | [`evidence/verification.md`](evidence/verification.md) — rows T1–T5, T11, T13, T15; [`evidence/security-review.md`](evidence/security-review.md) — nine abuse cases, nine closed |
| needs-review | 2026-09-11 | | PR raised; awaiting the owner (tier 4: PR approval **and** a named security sign-off) |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| (raised on push) | tasks 1–11: the whole work item | open |

## Progress entries

### 2026-09-11 — implemented, verified, ready for review

- **Phase:** implementation → verification → needs-review
- **Did:** tasks 1–11, red first (`test_repositories.py` did not collect against
  `35a08cf`). `channels/repos.py` → `the_loop/repos.py`, reading the top-level
  `repositories` and nothing else, with a new `repository_bounds` that tells *"declared
  nothing"* from *"declared, and this is not in it"*; the module now imports no channel,
  which is what lets the router read it. `webhook/router.py`: a `repositories` field, a
  `repository_key(payload)` helper, and one check in `route()` above the actor guard —
  the delivery's own repository, then the work items it names — both dropping as
  `undeclared-repository`. `webhook/daemon.py` builds and hot-swaps it and warns once when
  it is `None`. The poller's `from_source` / `build_provider` take `repositories` from the
  caller and refuse a source still carrying `repos`; `poller/daemon.py` passes the
  operator's own declared strings. `migrations.py`: version `0.8.0`, the promotion
  (sources + `kickoff.repo`, ordered and deduplicated, top-level entries first), the
  `needs_migration` and `assert_current` arms. Both schema copies, this repository's own
  CLI config (now bounded to itself), the shipped template, a new
  `docs/config/cli/repositories-options.md` and six other option/guide pages, the
  `webhook-triggers` and `channels` capability docs with history rows, and
  `decision-121`.
- **Checkpoint/tests:** `make check` — 3471 passed, 1 skipped; ruff, markdownlint (1065
  files), format, pyright and config validation clean. See
  [`evidence/verification.md`](evidence/verification.md), which also lists every existing
  assertion that changed and why.
- **Self-review:** three passes over the diff.
  - Pass one found a real gap: with the repository list out of `polling.sources`, a poll
    source can be *fully configured* and still have nothing to poll, which the plan-time
    "misconfigured" check did not cover — an operator would have got a poller looping on
    a per-cycle provider error instead of a line on their terminal. Added to
    `core/lifecycle.py` and `api/ingress.py` beside the existing empty-`sources` check.
    It also found the ref filter partitioning by object equality (`w not in kept`);
    rewritten to partition by key in one pass.
  - Pass two verified four design claims against the code: the bound is checked above
    `is_authorized` and above the bus publisher (asserted by a recorded drop carrying
    `repository` and no `actor`, and by a publisher that records nothing); a dropped
    delivery is never marked processed, so a redelivery after the repository is declared
    routes; what reaches `gh --repo` is `DeclaredRepo.declared`, the operator's own
    string; the poller constructs `RoutedEvent` directly and never a `Router`, so its own
    events are bounded by what it polls rather than filtered twice.
  - Pass three read the docs against the code and corrected three drifts: the design
    quoted a shortened form of the start-up warning and said `204` where the receiver
    answers `202 accepted`; the testing plan's trace named four tests that had been
    renamed during implementation; and `cli.md`, `control-plane.md`, `supervision.md` and
    `start.md` still described `polling.sources` as the only `misconfigured` case.
- **Open judgement recorded:** what an **empty** `repositories` should mean. Fail-closed
  is the instinct and is wrong here: it would stop every webhook-only instance on
  upgrade, this repository's own config included (`polling.sources: []` today,
  receiver-driven). Resolved as [decision-121](../../decisions/decision-121.md) D4 —
  empty bounds nothing, warned at start, stated in the schema and on the options page —
  with the consequence recorded as residual risk 1 in the security review, and the
  observation (residual risk 2) that a broken section's fail-closed narrowing lands on
  exactly that value. This is the one thing on which a reviewer might reasonably
  disagree, and reversing it is a one-line change plus a migration.
- **Next:** the owner's review, and the named security sign-off tier 4 requires.
- **Blockers:** none.

## Design critic review

> Not selected for this work item (`reviews.critics: []` — no external critic is
> configured, so the three self-review passes above are the review).

## Capability docs

- [`docs/capabilities/webhook-triggers.md`](../../capabilities/webhook-triggers.md) — a
  new *Current behaviour* clause for the repository bound (what is dropped, where the
  check sits, what an empty list means, what the bound is not), plus a history row.
- [`docs/capabilities/channels.md`](../../capabilities/channels.md) — the kickoff and the
  slash command now name the top-level `repositories`; a new clause for the fallback that
  points outside the declared set; a history row.
- [`docs/capabilities/cli.md`](../../capabilities/cli.md),
  [`docs/capabilities/control-plane.md`](../../capabilities/control-plane.md) — the
  second `misconfigured` / `ingress.hosted_failed` reason. Text only: a one-condition
  addition to an existing clause does not earn a history row of its own.

## Documentation

- **New:** [`docs/config/cli/repositories-options.md`](../../config/cli/repositories-options.md)
  — the key, who reads it, what an empty list means, what it is not, and the migration;
  registered in the VitePress sidebar.
- **Changed:** `docs/config/cli/polling-options.md` (the `sources[].repos` section
  replaced by *Which repositories are polled*, the failure-isolation prose kept where it
  belongs), `index.md` (version `0.8.0`, the no-fallback danger box, the removed-key
  list), `channels-options.md`, `integrations-options.md`, `docs/guide/slack.md`,
  `docs/cli/commands/start.md`, `docs/cli/commands/migrate-config.md` (a section for the
  new migration), `docs/cli/supervision.md`, `docs/reports/gh-queries.md`,
  `docs/decisions/decisions.md`.
- **Not changed, with the reason:** `README.md` — it describes the loop and the plugin,
  and names no CLI-config key this work item touches. `skills/the-loop/reference/*` —
  the references describe the process, not the daemon's config surface; the two `repos:`
  mentions there are the execution log's front matter, an unrelated key.
