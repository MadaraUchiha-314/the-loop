---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#279"
phase: implementation
status: in-progress
---

# Execution Log: a first-class PR review workflow

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-08-24 |  | `requirements.md` derived from the ticket |
| design | 2026-08-24 |  | `design.md` |
| test-planning | 2026-08-24 |  | `testing-plan.md` |
| tasks-breakdown | 2026-08-24 |  | `tasks.md` |
| implementation | 2026-08-24 |  | tasks 1–10 |
| verification | 2026-08-24 |  | every activity in `testing-plan.md` ran; results and evidence recorded there |
| needs-review | 2026-08-24 |  | reviewer briefing posted on the pull request |
| complete |  |  |  |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| (see the ticket) | the whole work item — spec chain, the review loop and every surface it reaches, documentation and tests | open |

## Progress entries

### 2026-08-24 — the owner's ruling: a work item is reviewable too

- **Phase:** needs-review (the spec chain is `in-review`, so the artifacts were
  **edited**, not appended to — the reference-don't-duplicate rule)
- **The ask** ([the PR thread](https://github.com/MadaraUchiha-314/the-loop/pull/280)):
  review at work-item level as well — one review session across all the PRs delivering
  a work item; piggyback on the PR tracking the-loop already generates; when the item
  was not delivered by the-loop, ask for the associated PRs; differentiate the
  follow-up question between a PR review and a work-item review; suggest detected PRs
  automatically.
- **Did:** requirements gained R8 (six criteria); design §4 gained the work-item
  variant; two integration ops (`get-thread`, `linked-pulls` — GraphQL
  `closedByPullRequestsReferences`, on both transports); the template now asks for the
  PR scope on a work item, pre-filled from the spec directory's `pr-loops/` layouts
  and the provider's links, deduped and best-effort; `parse_brief` reads
  `Pull requests:` (alias `PRs:`); stated entries normalize to composed
  `github:owner/repo#n` refs with junk dropped; the frozen brief carries
  `pullRequests` and the confirmation echoes it. No new session machinery — the
  work-item binding already yields one session and the existing linkage forwards the
  linked PRs' events to it (R8.6). Seven new tests (62 in the suite now);
  decision-101 gained point 7; docs of record updated.
- **One judgement call a reviewer should check:** a PR list alone is deliberately
  **not** a brief — scope without content asks nothing, so the gate keeps waiting.
- **Next:** re-verification, then back to human review.

### 2026-08-24 — implemented and verified

- **Phase:** implementation → verification → needs-review
- **Did:** tasks 1–11. The constants first (`REVIEW` through `control.py`'s four
  vocabularies; `PDLC_REVIEW_LOOP` through `SHIPPED_LOOPS`/`OUTER_PATH_LOOPS`/
  `LOOP_FOR_CONTROL_COMMAND` plus the new `GUEST_LOOPS`), then the graph, then the
  brief gate (`graph/hooks/review.py` — `parse_brief`, `post-review-brief`,
  `classify-review-brief` — with the `brief` fold in `runtime.py` beside `goal`), the
  one dispatcher change (PR-first targeting for `REVIEW` in `_apply_control`, an
  explicit `target` on `_on_unmatched`), the guest carve-outs (`_write_default` and
  `core/graphs._runtime` now test `GUEST_LOOPS`), the `review-pr` command, the config
  surface (both schema copies, the sample config, the routing-options page), the UI
  treeless set (renamed from `ADHOC_LOOPS`, honestly), 55 new tests plus the cleanup
  parametrizations, and the documentation of record with decision-101.
- **Two things worth a reviewer's eye**, both argued in decision-101: the follow-up
  gate **reuses `classify-adhoc-reply`** (same default, same safety rules, a
  done-vocabulary that fits reviews better than ad-hoc tasks — pinned by a test so the
  odd-looking name in the YAML cannot be "cleaned up" silently), and the fill-in
  template **lives in the CLI hook, not in `skills/the-loop/templates/`** (the daemon
  posts it; a plugin-side copy would be a second source that drifts).
- **Checkpoint/tests:** `uv run pytest` — 2661 passed, 1 skipped (2600 on `main` at
  `b6bfda1`, +61; the last one is the security review's regression test). `ruff
  check`, `ruff format --check`, `pyright cli`, `validate_config`, markdownlint (870
  files), `bun run lint/test/build` (157 passed) — all clean. Evidence under
  `evidence/`.
- **Next:** review cycles, then human review.

### 2026-08-24 — spec chain written

- **Phase:** requirements-definition → design → test-planning → tasks-breakdown
- **Did:** derived the four spec artifacts from the ticket. The shape follows the
  issue's own sequence (template → filled brief → review → follow-ups → done) as a
  fifth shipped graph, `pdlc-review-loop`, armed by `the-loop review`. Three judgement
  calls worth a reviewer's attention, all argued in `design.md` §Trade-offs and
  decision-101: the follow-up gate **reuses** `classify-adhoc-reply` rather than
  minting a twin; the fill-in template is **posted by a CLI hook and therefore lives in
  code** (like the goal request), not in the plugin's templates directory; and the
  review **binds to the pull request itself** even when the PR links a ticket — the
  one dispatcher change this work item makes.
- **Next:** implementation.

## Verification results

Completed at the `verification` node — the full record (activities, outcomes,
evidence links) lives in [`testing-plan.md` § Verification
results](testing-plan.md#verification-results). Headline: the new suite 56/56, the
whole Python suite 2661 passed / 1 skipped (+61 over `main`), UI 157/157, lint /
format / types / config validation / markdownlint all clean.

## Review cycles

Three self-review passes over the full diff before requesting human review
(`reviews.selfReviewCount: 3`):

1. **Correctness pass** — re-read the dispatcher targeting change against issue-269's
   semantics (the non-review keywords keep linked-first; `record_owning` on the PR ref
   matches `_live_session_for`'s liveness semantics; the close path ends a review
   session when the reviewed PR merges/closes, because the session's own ref is the
   closing ref). Found and fixed before commit: the dispatcher tests leaked control
   records through the store's default shared path — isolated per test.
2. **Staleness sweep** — every "four loops"/"three loops" count in README, guides,
   how-it-works and the hooks example (`19` → `21`) updated; the two remaining
   "fourth shipped graph" mentions verified still true (they describe the ad-hoc
   loop).
3. **Edge pass** — `parse_brief` refuses the posted template quoted back (placeholder
   bullets), an inline `Questions: …` one-liner deliberately does not parse (the
   template teaches the bullet shape, and the waiting message restates it); empty
   exit chain on `review` confirmed to pass like the `complete` nodes'.

Critic review (`reviews.criticReviewCount: 3`, a different harness/model): **not run —
no critic is configured** (`reviews.critics: []` in this repository's harness config)
and no second harness is available in this environment. Recorded as a gap for the
human reviewer rather than silently skipped.

## Security review (gate)

Mechanism `auto` → the built-in security-review skill ran over the branch diff
(finder + false-positive filter, per the skill's procedure); risk tier 3 <
`humanSignOffMinTier: 4`, so no named human sign-off is required. The requirements'
abuse cases 1–6 are each covered by a negative test (evidence:
`evidence/unit-and-integration.md`). New attack surface, stated: one keyword added to
the fixed control vocabulary (same parser, same named-actor authorization), one
comment-parsing gate (authorized, non-self-authored text only, output frozen as a
fact), and a PR-first target derived from the router's own extraction — no payload
text reaches a path, an argv, or a routing decision.

**Verdict: pass — no finding cleared the reporting bar** (>80% confidence of actual
exploitability, HIGH/MEDIUM only). The reviewer verified: arming/briefing/steering all
sit behind the named-actor allowlist with the self-marker dropped first; the frozen
brief reaches no argv, path, prompt template or routing decision (the outcome token is
the constant `briefed` on a shipped edge); PR-first targeting is composed from
HMAC-verified structural payload fields and passes the same spawn-policy gates; and
`resolve_outer_loop` still confines the agent-writable `loop` field to shipped names.
Two sub-threshold observations, both recorded rather than dropped:

1. **Risk elevation, not new surface** — the review loop makes "spawn a harness
   session bound to a third-party PR" a first-class workflow, and arming via a
   `pull_request_review(_comment)` event seeds the worktree with the PR author's head
   branch (the ordinary `issue_comment` arming path checks out the default branch
   detached, and the session *reads* the head). The checkout-and-trust mechanism
   predates this work item (PR endpoints and unlinked-PR spawns), arming is
   human-gated, and requirements §Security states the risk and its mitigations — the
   same one every CI system carries.
2. **Template suppression via marker spoofing** — `_already_requested` counted the
   idempotence marker in *any* comment, so an unauthorized paste of the public marker
   string could mute the fill-in template (cosmetic: the gate still refuses to proceed
   without an authorized brief). **Fixed in this work item**: only a self-authored
   marker comment counts, with a regression test
   (`test_a_spoofed_marker_cannot_suppress_the_template`). The same pattern exists in
   `goal.py`'s `_already_requested` — pre-existing, spotted-not-fixed here to keep the
   PR narrow; worth its own tactical ticket.

## Final validation evidence

- [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) — the new
  suite, the walk scenarios, the abuse cases.
- [`evidence/full-suite.md`](evidence/full-suite.md) — the whole suite, contract
  parity, the behaviour-preserving generalization.
- [`evidence/ui-suite.md`](evidence/ui-suite.md) — UI lint/test/build.
- [`evidence/lint-and-types.md`](evidence/lint-and-types.md) — ruff, pyright,
  markdownlint, config validation.

## Capability docs

- [`docs/capabilities/process-graph.md`](../../capabilities/process-graph.md) — the
  fifth loop's normative block (§ The graph), the file list, the cleanup-node
  invariant, a History row.
- [`docs/capabilities/webhook-triggers.md`](../../capabilities/webhook-triggers.md) —
  the ninth keyword in the control vocabulary, a History row.
- [`docs/capabilities/control-plane.md`](../../capabilities/control-plane.md) — the
  Sessions screen's treeless set.

## Documentation

- `README.md` — "Four loops" → "Five loops", the review-loop bullet.
- `docs/guide/what-is-the-loop.md`, `docs/guide/how-it-works.md`,
  `docs/guide/quickstart.md` (§6, `#pr-reviews`) — the user-facing walkthrough.
- `docs/reference/commands.md` — the `/the-loop:review-pr` row.
- `docs/config/cli/routing-options.md` — `control.keywords.review`;
  `docs/config/harness-config.md` — the adopt-or-not row;
  `docs/cli/commands/graph.md` — the hooks-count example (19 → 21).
- `skills/the-loop/SKILL.md`, `reference/workflow.md` (§ The review loop),
  `reference/collaboration.md`, `reference/automation.md` — the operating model.
- `docs/decisions/decision-101.md` (+ index row) — the four calls a reviewer should
  check.
- `commands/review-pr.md` — the driving command (new page, discovered from the
  directory; no nav change needed).
