---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#311"
phase: needs-review
status: in-progress
---

# Execution Log: every link and every `gh` call names the GitHub it is on

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-09-02 | — | Tier 4 (`human-approves-pr` **plus** a named human security sign-off, `security.review.humanSignOffMinTier: 4`): the change adds a key to the CLI-config schema (`**/*schema*`), and a host string reaches a `gh` argument that selects a credential. Brainstorming skipped — the ticket asks for an audit and names the fix; the audit table is in `bugfix.md` |
| requirements-definition | 2026-09-02 | | [`bugfix.md`](bugfix.md) — the audit (13 sites, 7 to fix), six requirements, five abuse cases |
| design | 2026-09-02 | | [`design.md`](design.md) — one resolver, refs minted with the host, one `gh` spelling read back off the ref; [`decision-104`](../../decisions/decision-104.md) |
| test-planning | 2026-09-02 | | [`testing-plan.md`](testing-plan.md) — fourteen rows, ten applicable |
| tasks-breakdown | 2026-09-02 | | [`tasks.md`](tasks.md) — eight tasks |
| implementation | 2026-09-02 | | On `claude/github-issue-311-hp66sw` — tasks 1–8 |
| verification | 2026-09-02 | | [`evidence/verification.md`](evidence/verification.md) — `make check` clean, 2925 passed; [`evidence/security-review.md`](evidence/security-review.md) — five abuse cases, five closed |
| needs-review | 2026-09-02 | | PR raised; awaiting the owner **and** the named human security sign-off tier 4 requires |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#313](https://github.com/MadaraUchiha-314/the-loop/pull/313) | tasks 1–8: the whole work item | open |

## Progress entries

### 2026-09-02 — audit done, spec chain drafted

- **Phase:** requirements-definition → tasks-breakdown
- **Did:** grepped every `github.com`, `html_url`, `gh api`/`--repo` and ref-minting
  site in `cli/the_loop`, `skills/`, `commands/`, `hooks/` and the templates at
  `7748847`; classified each (keep / fix / the-loop's own home); wrote the four
  artifacts and the decision.
- **Checkpoint/tests:** none yet.
- **Next:** task 1 (the resolver), red first.
- **Blockers:** none.

### 2026-09-02 — implemented, verified, ready for review

- **Phase:** implementation → verification → needs-review
- **Did:** tasks 1–8, red first each. `ghhost.py` and `is_github_host`; `derive_ref`/
  `ref_for` take a host and the bootstrap resolves it once per runtime; one `gh`
  spelling (`comments.gh_host_args`, `WorkItemRef.path` / `RepoSpec.gh_repo`) in every
  writer and reader; both graph transports; the review brief; the schema (both copies),
  template, this repo's config, the docs and the capability docs; decision-104.
- **Checkpoint/tests:** `make check` — see `evidence/verification.md`. New tests: 37
  (resolver), 6 scenarios (end-to-end), and host cases in six existing files.
- **Self-review:** three passes over the diff. Fixed in place: the resolver's remote
  reader was bound at definition time (untestable seam → resolved at call time); a
  hosted slug (`github:host/o/r#n`) fell through the brief's normaliser and was dropped,
  so the-loop's own detected refs vanished on GHE (regex widened, refusal kept through
  `_pull_ref`); the PR listing's first `_list_prs` call had missed the host; a lazy
  `is_github_host` import beside top-level ones in the transport module; the kickoff
  `repo` schema description and doc still said `owner/repo`.
- **Next:** the owner's review and the tier-4 security sign-off.
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
| 1 | self | the-loop (this session) | new findings — the resolver seam, the hosted-slug drop, the PR-listing host: fixed | this log |
| 2 | self | the-loop (this session) | new findings — import tidy, kickoff `repo` wording: fixed | this log |
| 3 | self | the-loop (this session) | zero (converged) | this log |
| — | critic | — | unavailable — `reviews.critics` is empty in this repository's config; does not count toward `criticReviewCount` | — |
| 4 | security | the-loop checklist | pass; human sign-off pending (tier 4) | [`evidence/security-review.md`](evidence/security-review.md) |

## Security review (gate)

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`; no security-review
  skill is invocable from this session's plugin set)
- **Outcome:** pass — [`evidence/security-review.md`](evidence/security-review.md), five abuse cases closed
- **Human sign-off:** required (tier 4 ≥ `humanSignOffMinTier: 4`) — requested on the PR

## Final validation evidence

| Requirement | Proof |
|-------------|-------|
| R1 one resolver, five tiers, one grammar | `test_ghhost.py` (37), `test_ghhost_integration.py` |
| R2 configuration-minted refs carry the host | `test_graph_refs.py` host cases; `test_ghhost_integration.py::test_a_configured_host_reaches_the_link_and_the_argv`, `…::test_a_pull_request_loop_carries_the_host_too` |
| R3 the review brief | `test_graph_review.py::test_a_stated_pull_request_url_keeps_its_host`, `…::test_detected_pull_requests_carry_the_work_items_host` |
| R4 every `gh` call names the host | `test_comments.py`, `test_reactions.py`, `test_linkage.py`, `test_graph_integrations.py` host cases |
| R5 enterprise poll sources | `test_poller.py` host cases (`RepoSpec`, listings, comments, state, `owns`) |
| R6 the tier is logged | `test_ghhost.py::test_the_tier_is_logged` |
| A5 github.com unchanged | `test_ghhost_integration.py::test_github_com_mints_exactly_what_it_always_did` and the 2919 pre-existing tests |

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`cli.md`](../../capabilities/cli.md) | the ref rule gains the minting side (the resolver's five tiers) and the one `gh` spelling; poll `repos` accept `[HOST/]OWNER/REPO` | issue-311 row |
| [`channels.md`](../../capabilities/channels.md) | the notification's URL is derived from a ref that carries the host; a kickoff `repo` may name its host | issue-311 row |

## Documentation

| Document | What changed |
|----------|--------------|
| `docs/config/cli/integrations-options.md` | new `github.host` section (the five tiers); `github.api.baseUrl` cross-reference |
| `docs/config/cli/polling-options.md` | `sources[].repos` accepts `[HOST/]OWNER/REPO` |
| `docs/config/cli/routing-options.md` | `workspace.defaultHost` distinguished from `integrations.github.host` |
| `docs/config/cli/channels-options.md` | `slack.kickoff.repo` accepts `[host/]owner/repo` |
| `docs/cli/concepts.md`, `docs/cli/state.md` | where a ref minted in-session takes its host from |
| `skills/the-loop/reference/automation.md` | the checkout host vs. the GitHub the-loop talks to |
| `skills/the-loop/templates/cli-config.yaml`, `.the-loop/cli-config.yaml` | `integrations.github.host` shown, commented |
| `README.md`, `skills/the-loop/SKILL.md` | unchanged — neither describes hosts or the integrations block |
