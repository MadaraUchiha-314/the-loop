---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#246"
phase: needs-review          # not-started | brainstorming | requirements-definition | design | test-planning | tasks-breakdown | implementation | verification | needs-review | complete
status: in-progress          # in-progress | complete
---

# Execution Log: the poller ignores PR reviews and review-thread comments

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-16 | @MadaraUchiha-314 | Declared by the owner's direct instruction to complete #246 in a cloud session (see the note under *Deviations from the standard gates*). Full process; `brainstorming` skipped — the issue names the fix; `design-critic-review` not selected (no critic is configured). |
| requirements-definition | 2026-08-16 | pending — PR #248 | `bugfix.md` (a bug). Five requirements; the four questions the issue flagged are settled in it, one is deferred to design on purpose. |
| design | 2026-08-16 | pending — PR #248 | Settled the deferred question: REST via `gh api --paginate`, with the GraphQL alternative recorded as rejected and why. |
| test-planning | 2026-08-16 | pending — PR #248 | 14 rows, 6 in scope; every `n/a` carries a reason. |
| tasks-breakdown | 2026-08-16 |  | 10 tasks, three independent red roots. |
| implementation | 2026-08-16 |  | TDD: the red run captured and committed before the fix. |
| verification | 2026-08-16 |  | Every planned activity ran. Two rows corrected after execution — see below. |
| needs-review |  |  |  |
| complete |  |  |  |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#248](https://github.com/MadaraUchiha-314/the-loop/pull/248) | The whole work item — the spec chain and the fix. | open |

## Progress entries

### 2026-08-16 — read the failing path, wrote the spec chain

- **Phase:** requirements-definition → design → test-planning → tasks-breakdown
- **Did:** traced the reported silence end to end — `GhClient.list_comments`
  (`cli/the_loop/poller/github.py:239`) → `Poller._process_item`
  (`cli/the_loop/poller/poller.py:655`) → the dedup ledger — and confirmed the report's
  diagnosis: the poller asks for one GraphQL connection and the other two are never
  requested, so the missing comments are *unknown* rather than dropped. Confirmed the
  webhook side already handles both (`router.event_actor` / `event_body` branch on
  `pull_request_review` and `pull_request_review_comment`), which made the fix's shape a
  parity question rather than a design question.
- **Checkpoint/tests:** baseline suite green before any edit (132 passed in the two poller
  files, 2124 across the repository).
- **Next:** write the red tests.
- **Blockers:** none.

### 2026-08-16 — red, then green

- **Phase:** implementation
- **Did:** wrote the unit and integration tests first and ran them against the unfixed tree
  (**10 failed**, [`evidence/red.md`](evidence/red.md)). Then the three edits the design
  names: `Comment.raw`, the three-surface fetch/merge with the per-kind event shapes, and
  the retained-id cap. `gh pr view --json comments` is left untouched, so no operator's
  ledger is invalidated on upgrade.
- **Checkpoint/tests:** 149 passed in the two poller files; `uv run pytest` 2124 passed,
  1 skipped, 0 failed; `ruff`, `ruff format`, `pyright` and `markdownlint` all clean
  ([`evidence/unit-and-integration.md`](evidence/unit-and-integration.md),
  [`evidence/lint-and-typecheck.md`](evidence/lint-and-typecheck.md)).
- **Corrected:** two claims the specs made before the code existed.
  1. `bugfix.md` § Security considerations said the per-comment gate is fail-closed for an
     author-less item. It is not — `is_authorized("")` **allows** it, by design, because an
     actor-less action is a CI event in the model that predicate was written for. The
     webhook path answers identically for the same object, so nothing here introduces it;
     corrected in place, with the residual recorded in `design.md` and pinned by a test.
  2. `testing-plan.md`'s T2 row expected two *deliveries*. What actually happens is one
     delivery and one endpoint spawn: a `pull_request_review*` payload names a pull
     request, so the dispatcher binds that PR as an endpoint and opens its inner loop with
     the instruction as its first prompt (`sessionPerPr`). That is the webhook path's
     behaviour too — the parity this item is for — so the test now asserts what the
     requirement actually says (conveyed exactly once, never again) rather than a location
     I had guessed at.
- **Found (not caused):** poll-path PR *conversation* comments do **not** reach the inner
  PR loop, because the poller labels them `issue_comment` while putting the PR under
  `payload["pull_request"]` — a shape `router._pr_entity` does not recognise (a real
  webhook carries `issue` with a `pull_request` key). Predates this change; left alone,
  because changing it moves where every polled PR comment is delivered. Recorded in
  `design.md` and worth its own ticket.
- **Next:** capability doc, user-facing docs, reviews.
- **Blockers:** none.

### 2026-08-16 — docs, self-review, security review

- **Phase:** verification → needs-review
- **Did:** updated the capability doc (a behaviour block naming the three surfaces, plus a
  history row) and `docs/config/cli/polling-options.md`; ran the self-review rounds and the
  security review recorded below.
- **Checkpoint/tests:** full suite and the whole lint set re-run after the doc edits.
- **Next:** the human PR gate (risk tier 3 → `human-approves-pr`).
- **Blockers:** none.

## Deviations from the standard gates

Two, both stated rather than quietly taken:

1. **`phase-selection` was not posted as a checklist and waited on.** This session was
   started by the owner directly against issue #246 with an instruction to complete it, in
   a cloud checkout with no poller, no daemon and therefore no way to receive the reply to
   such a post. The instruction is treated as the declaration (`the-loop execute` with the
   default phase set, `brainstorming` skipped). The gate the tier actually turns on —
   `human-approves-pr` — is **not** bypassed: the PR waits for review.
2. **The four spec artifacts are marked `approved` in one PR** rather than approved one at
   a time. Same reason: there is no ingress in this environment that could deliver a
   per-phase approval. The reviewer approves the chain and the code together on PR #248,
   and any correction lands as an edit to the artifact, not a new comment.

## Verification results

> This work item has a `testing-plan.md`, so the `verification` node records its results
> there, against the matrix rows it planned. This section stays as the template left it.

| What was verified | Command | Outcome | Evidence |
|-------------------|---------|---------|----------|
|                   |         | pass \| fail | link or `evidence/<file>` |

## Design critic review

> Only when this work item selected the opt-in `design-critic-review` phase (issue-188).
> Not selected: `reviews.critics` is empty in `.the-loop/harness-config.yaml`, so no
> different model is configured to read the locked design.

| Round | Critic (`<harness>/<model>`) | Outcome | Findings → disposition | Link |
|-------|-----------------------------|---------|------------------------|------|
|       |                             | new findings \| zero (converged) \| escalated \| unavailable | | |

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | the-loop session | new findings — the specs asserted two things the code disproved: a fail-closed claim about `is_authorized("")`, and the expected delivery shape for a review event. Both corrected in place, with the reasoning kept; the second one changed a test's assertions, not the requirement | this PR |
| 2 | self | the-loop session | new findings — traced every consumer of the changed shapes rather than re-reading the diff. `reactions.target_from_event` reacts on a `PRRC_` node id (correct: `PullRequestReviewComment` is `Reactable`) and falls back to the PR for a review (also correct: `PullRequestReview` is not). `Comment`'s new field is last and defaulted, so the positional call sites in the tests and the fake providers keep working. `_pr_head_ref` now finds a head ref on review events, which is what seeds the PR's worktree — desirable, and the reason the endpoint spawn lands in the right checkout | this PR |
| 3 | self | the-loop session | new findings — the failure surface. `_run_rest_list` refuses a non-list answer instead of iterating a dict's keys, and no path catches-and-continues, so a broken read stays loud (`poll.item_error`, retried) rather than reproducing this very bug with a new cause. The one untestable assumption here (`--paginate` merging array pages) is recorded under `testing-plan.md` § Residual risk with its failure mode | this PR |
| 4 | critic | — | **unavailable** — `reviews.critics: []`, so `the-loop critic list` reports none configured. Does **not** count toward `reviews.criticReviewCount` (`reference/reviewing.md`) | — |
| 5 | security | checklist (`reference/security.md`) | pass — see § Security review | this PR |

Rounds 1–3 each found something new, so the loop did not stop early; a fourth was not run
(`reviews.selfReviewCount` is 3, and the three rounds covered distinct surfaces — the
specs' own claims, the downstream consumers, and the failure paths).

## Security review (gate)

- **Mechanism:** the-loop's checklist (`security.review.mechanism: auto` prefers the
  built-in `security-review` skill; it is not available in this session, so the checklist
  was applied and is recorded here rather than being claimed as a skill run).
- **Scope:** this change **widens an untrusted ingress** — two new streams of
  attacker-controllable text now reach a prompt an agent acts on. "No new attack surface"
  is not claimed; what is claimed, and tested, is that both enter through the existing gate.

  | Question | Verdict |
  |---|---|
  | Can a review bypass the authorization gate? | No. Reviews arrive as `Comment` objects and are judged in `Poller._process_item` by the same `is_authorized`/`is_self_authored` pair, in the same order, before anything is enqueued. A provider that emitted events directly would have bypassed it — that is why the design routes them through `Comment`. |
  | Can the-loop's own review resume its own session? | No. `is_self_authored` reads the review body, and `router.event_body` returns `review.body` for `pull_request_review`, so the marker check works on the delivered event too. Both are tested. |
  | Does an unauthorized reviewer reach the session? | No — resolved and baselined, never forwarded. Tested end-to-end (`test_a_silent_approval_and_a_strangers_review_are_never_forwarded`). |
  | Does any comment text reach an argv, a path or a ref? | No. `path` and `line` are JSON values in a payload; nothing opens them, joins them or passes them to a subprocess. The only strings this change puts in an argv are the owner, repo and number the poller already had. |
  | Can a huge review body crowd out the prompt? | Bounded by `_PAYLOAD_EXCERPT_MAX_CHARS` as before, and the design carries fewer fields than GitHub returns — the diff hunk is excluded for exactly this reason. The inline anchor is emitted **before** the body so truncation cannot take it. |
  | New credentials or network paths? | None. Both new reads go through the operator's existing `gh`; no config key, no env var, no token. |
  | Residual | A review GitHub attributes to nobody (`user: null`) is allowed, because `is_authorized` allows actor-less actions by design. Identical on the webhook path — inherited, not introduced — and pinned by a test so narrowing it later is a visible decision. Recorded in `design.md` § Security design. |

- **Human sign-off:** n/a. Risk tier 3 (`autonomy.defaultTier`; no `sensitivePaths` glob
  matches — no schema, no `.the-loop/` config, no workflow file), below
  `security.review.humanSignOffMinTier: 4`.

## Final validation evidence

| Criterion | Met by |
|---|---|
| **R1.1 / R1.2** a review body forwarded exactly once, never again | `test_a_pr_review_and_an_inline_comment_reach_the_session_once_each` — three cycles, each instruction conveyed once across spawn prompts and deliveries. |
| **R1.3** author, body, timestamp, URL and state delivered | `test_provider_review_event_is_shaped_like_the_webhook_one`, which also asserts `event_actor`/`event_body` resolve on the produced payload. |
| **R1.4 / R1.5** an empty approval and a `PENDING` review forward nothing | `test_gh_review_carrying_no_instruction_is_not_a_comment` (three parametrized cases) and the integration negative. |
| **R2.1 / R2.2** an inline comment forwarded once, with its anchor | The integration test asserts the file and line are in the conveyed prompt; `test_provider_review_comment_event_carries_its_file_and_line` pins the payload shape and the anchor's position ahead of the body. |
| **R2.3** an outdated comment keeps its original line | `test_gh_review_comment_on_an_outdated_line_keeps_its_original_anchor`. |
| **R2.4** a review and its inline comments are separate deliveries | Structural — distinct node ids, distinct `delivery_id`s — and observed as two conveyances in the integration test. |
| **R3.1 / R3.2** unauthorized and self-authored reviews are ignored | `test_a_silent_approval_and_a_strangers_review_are_never_forwarded`, `test_a_self_authored_review_never_leaves_the_poller`. |
| **R3.3** a control keyword in a review body behaves as in a comment | `event_body("pull_request_review", …)` returns the review body — asserted in the event-shape test; the dispatcher's own path is unchanged and already covered. |
| **R3.4** no new credential or network path | Code review: the new calls are `gh api …` through the same `_run_json`; no config key was added (`test_docs_parity.py` would fail on an undocumented one). |
| **R4.1** issue polling unchanged | `test_gh_list_comments_on_an_issue_is_one_call_exactly_as_before` asserts one call and no `gh api`. |
| **R4.2** the extra reads are bounded and paginated | `test_gh_list_comments_on_a_pr_reads_all_three_surfaces` asserts `--paginate` on both. |
| **R4.3** the cap accounts for all three streams | `test_the_id_ledger_holds_a_whole_merged_thread` — 700 mixed ids survive a `finalize`; it fails at the old cap of 500. |
| **R4.4** a failed read is not swallowed | `test_gh_review_fetch_failure_is_not_swallowed_into_no_comments`. |
| **R5.1 / R5.2** red-then-green, with a Gherkin integration test | [`evidence/red.md`](evidence/red.md); both new integration tests carry `Feature:`/`Scenario:`/Given-When-Then docstrings with a `Requirement:` link. |
| **R5.3** the parity is stated in the capability doc | `docs/capabilities/webhook-triggers.md` § Current behaviour — the three-surface table and its rules. |

**Not claimed:** that this was observed against real GitHub. No `gh` binary and no
credentials exist in this environment, so the subprocess boundary is faked at the seam the
module ships for it. The one assumption that leaves untested is named in `testing-plan.md`
§ Residual risk, with its failure mode (a loud, retried `GhError` — never silence).

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`webhook-triggers.md`](../../capabilities/webhook-triggers.md) | New behaviour block under *Current behaviour*: **both ingresses read the same three comment surfaces**, with the object → event → payload table, the exactly-once and anchor rules, the two reviews that carry no instruction, the unchanged guard order, and the promise that an issue costs the request it always did. | issue-246 |

## Documentation

| Document | What changed |
|----------|--------------|
| [`docs/config/cli/polling-options.md`](../../config/cli/polling-options.md) | New info block under `sources[].monitor.pullRequests`: which surfaces a polled PR is read on, what is not forwarded (empty approval, `PENDING`), and the request cost — two extra paginated reads per PR, none per issue. |

`README.md` and the operating-model skill were checked and needed no change: neither
describes which comment objects an ingress reads. Verified by grepping both for
`pull_request_review`, `review comment` and `list_comments` — the only hits outside
`docs/specs/` were the capability doc and the config page listed above.
