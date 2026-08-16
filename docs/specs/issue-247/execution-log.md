---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#247"
phase: needs-review          # not-started | brainstorming | requirements-definition | design | test-planning | tasks-breakdown | implementation | verification | needs-review | complete
status: in-progress          # in-progress | complete
---

# Execution Log: record-feedback writes markdown that fails the project's own markdownlint

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-16 | @MadaraUchiha-314 | Declared by the owner filing [#247](https://github.com/MadaraUchiha-314/the-loop/issues/247) with a diagnosis, a suggested fix and a designated branch, then pointing a cloud session at it. `brainstorming` skipped — the ticket *is* the diagnosis; `design-critic-review` not selected (no critic is configured in this repository, `reviews.critics: []`). See *Deviations from the standard gates*. |
| requirements-definition | 2026-08-16 | pending — this branch's PR | `bugfix.md` (a bug). Three requirements: lint-clean output, an unrewritten paper trail, and a regression test that does not depend on Node. |
| design | 2026-08-16 | pending — this branch's PR | Two branches in one hook. Three candidate shapes measured against the pinned linter before choosing; the ticket's own suggestion is among the two rejected, with the reason. |
| test-planning | 2026-08-16 | pending — this branch's PR | 13 rows, 5 in scope; every `n/a` carries a reason. Two rows added to the catalogue: linter conformance, repository gates. |
| tasks-breakdown | 2026-08-16 | | 9 tasks, one red root of three. |
| implementation | 2026-08-16 | | TDD: the red run captured and committed before the fix. |
| verification | 2026-08-16 | | Every planned activity ran; nothing replanned, nothing skipped. Two lint findings in this work item's *own* artifacts, fixed before T13 was ticked. |
| needs-review | 2026-08-16 | | 3 self-review rounds; no critic configured. |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| this branch's PR | The whole work item — the spec chain and the fix. | open |

## Progress entries

### 2026-08-16 — measured the linter before designing against it

- **Phase:** requirements-definition → design
- **Did:** reproduced MD036 against the repository's own `.markdownlint-cli2.jsonc` with
  the pinned `markdownlint-cli2@0.18.1`, then ran all three candidate shapes through it
  rather than reasoning about the rule.
- **Found, and it changed the design:** the ticket's blockquote suggestion passes — but
  only because MD036 does not descend into blockquotes. That is a linter implementation
  detail, not a documented promise, so the fix would rest on a rule *not* firing. The
  chosen shape (`**@handle** wrote:`) fails MD036's premise outright instead.
- **Also found:** blockquoting the *body* is not a defence at all. MD025, MD004 and MD010
  all still fire inside a blockquote, and the quoting adds MD027 of its own — which
  is why the fix is confined to the text the harness itself authors, and why "lint the
  reviewer's words" is out of scope rather than merely unimplemented.
- **Checked before assuming:** `record-feedback` is the only `write_text` under
  `cli/the_loop/graph/hooks/`, so the defect has one site. The one other place the harness
  writes emphasis (`sideeffects.py:96`) posts to GitHub, not to a linted file, and carries
  trailing text anyway.
- **Next:** the red root — three tests, one failing run.

### 2026-08-16 — red, then two branches, then the linter itself

- **Phase:** tasks-breakdown → implementation → verification
- **Did:** wrote the three tests, captured the failing run as
  [`evidence/red.md`](evidence/red.md), then replaced the block assembly with the two
  branches from the design. The existing gate scenario was strengthened at the same time:
  it asserted `"tighten the nit" in text`, which a reflowing recorder would also satisfy,
  and now asserts the body verbatim.
- **One thing worth stating:** the regression is caught by asserting the emitted **shape**
  (no line is emphasis and nothing else), not by shelling out to markdownlint. The suite
  runs without Node, and a test that skips when `npx` is missing would have stopped
  guarding this the first time it ran in a Python-only environment. The real linter runs
  once, at verification, as evidence — [`evidence/shapes.md`](evidence/shapes.md).
- **Caught by the gate this ticket is about:** the first whole-repository `markdownlint`
  run failed on **this work item's own artifacts** — an `MD038` in `bugfix.md` and an
  `MD010` in the evidence file, where the captured linter output quotes a hard tab back at
  us. Fixed and disabled-with-a-reason respectively, before T13 was ticked.
- **Checkpoint/tests:** 2225 passed, 1 skipped; ruff, ruff format, pyright and
  `validate_config` clean; markdownlint 0 errors over every `**/*.md`. Evidence in
  [`evidence/`](evidence/).
- **Next:** capability doc, decision-089, the PR and its briefing.

## Verification results

> **Only when this work item declared `test-planning` away** (issue-179). This item kept
> the plan, so its results live in [`testing-plan.md`](testing-plan.md) §Verification
> results and this section stays as the template left it.

| What was verified | Command | Outcome | Evidence |
|-------------------|---------|---------|----------|
|                   |         | pass \| fail | link or `evidence/<file>` |

## Design critic review

> **Only when this work item selected the opt-in `design-critic-review` phase** (issue-188).
> Not selected: `reviews.critics` is empty in this repository, so no second harness is
> configured to read the locked design.

| Round | Critic (`<harness>/<model>`) | Outcome | Findings → disposition | Link |
|-------|-----------------------------|---------|------------------------|------|
|       |                             | new findings \| zero (converged) \| escalated \| unavailable | | |

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | the-loop | new findings — the shape assertion's regex flagged `**a** and **b**`, which MD036 leaves alone, so the helper now checks the delimiter is not repeated inside; the two helpers moved above their first use | this branch |
| 2 | self | the-loop | new findings — `bugfix.md` asserted MD012 for the empty-body case without ever running the linter on it. Measured (both mid-file and at EOF) and added as [`evidence/shapes.md`](evidence/shapes.md) §4; the claim held, but it was a claim | this branch |
| 3 | self | the-loop | zero (converged) — artifact gates re-read against the shipped graph: `## Requirements` + `## Security considerations` in `bugfix.md`, `## Security design` in `design.md`, the four gated sections in `testing-plan.md`, `## Capability docs` and `## Documentation` here | this branch |
| — | critic | n/a | unavailable — `reviews.critics` is empty in this repository, so no second harness is configured. Does not count toward `reviews.criticReviewCount` | [harness-config](../../../.the-loop/harness-config.yaml) |
| 4 | security | the-loop checklist | pass — see the gate below | this branch |

## Security review (gate)

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`)
- **Outcome:** pass. The change is string assembly between an existing `read_text` and an
  existing `write_text`, behind an authorization boundary it does not touch:
  `_authorized_comments` still decides whose text is read at all, the self-authored marker
  still drops the harness's own comments, and no new value is interpolated from the event —
  the only text added is two literals. The untrusted comment body was, and remains, written
  verbatim into a checked-in file; that is the paper trail working as designed
  ([decision-042](../../decisions/decision-042.md)), and this work item deliberately did not
  narrow it, because narrowing it means rewriting a human's words. Both negative tests
  guarding the boundary were re-run and pass.
- **Human sign-off:** n/a — risk tier 2 (a single hook's output formatting; no path in
  `autonomy.sensitivePaths` is touched), below `security.review.humanSignOffMinTier: 4`

## Final validation evidence

Every acceptance criterion has a run behind it, in
[`testing-plan.md`](testing-plan.md) §Verification results.

| Criterion | Proved by |
|-----------|-----------|
| R1.1 — the attribution is not emphasis alone | `test_a_recorded_review_never_writes_emphasis_alone_on_a_line`, red in [`evidence/red.md`](evidence/red.md) and green in [`evidence/green.md`](evidence/green.md); the real linter in [`evidence/shapes.md`](evidence/shapes.md) §1–2 (2× MD036 before, 0 after) |
| R1.2 — an empty body records no blank-line pair | `test_a_comment_with_no_body_is_recorded_without_a_blank_line_pair`; [`evidence/shapes.md`](evidence/shapes.md) §4 shows the MD012 it replaces |
| R1.3 — the recorded artifact passes markdownlint | [`evidence/shapes.md`](evidence/shapes.md) §2, and `make lint` over every `**/*.md` in [`evidence/check.md`](evidence/check.md) |
| R2.1, R2.2 — handle kept, body verbatim | the strengthened gate scenario, which now asserts the body verbatim rather than as a substring |
| R2.3 — still append-only under `## Review comments` | the same scenario, unchanged in that respect |
| R3.1 — a regression test that fails before and passes after | [`evidence/red.md`](evidence/red.md) → [`evidence/green.md`](evidence/green.md), same tests, only the hook between them |
| R3.2 — no Node dependency in the suite | the assertion is on the emitted shape; the linter runs once at verification, as evidence |

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [process-graph.md](../../capabilities/process-graph.md) | The `record-feedback` behaviour statement in §Shipped hooks now states what the hook writes, not only that it writes: the `**@handle** wrote:` attribution and why, the empty-body line, and the rule that the reviewer's body is never rewritten to satisfy a linter | `issue-247`, linking this spec and [decision-089](../../decisions/decision-089.md) |

## Documentation

| Document | What changed |
|----------|--------------|
| none | No user-facing document described the recorded block's format, so none was made wrong by changing it. Checked: `README.md` does not mention `record-feedback`; the skill's `reference/testing.md` mentions it only to say `design-approval` records into both artifacts, which is unchanged; the five bundled templates carry a `## Review comments` blurb that describes the *guarantee* (append-only, attributed) rather than the markup, and it stays true. The durable rule this work item established is a decision, not a doc page — [decision-089](../../decisions/decision-089.md) |

## Deviations from the standard gates

- **`phase-selection` was answered by the ticket, not by the checklist comment.** This work
  started from a cloud session pointed at [#247](https://github.com/MadaraUchiha-314/the-loop/issues/247)
  rather than from `the-loop start`, so no checklist was posted and no `the-loop execute`
  reply exists. The owner's ticket — which names the defect, the file, the line and the
  suggested fix — is the authorization, and it is quoted in the table above. The spec chain
  exists in full rather than being skipped.
- **The artifacts are `in-review`, not `approved`.** Nothing here has been through a human
  gate yet; the pull request carries the whole chain for review in one place. No phase
  claims an approval it does not have.
- **The `loop:<phase>` label is applied by this session, not by the harness.** A cloud
  session working the-loop's own repository has no daemon
  ([#73](https://github.com/MadaraUchiha-314/the-loop/issues/73)), so `set-phase-label`
  never runs; the label on #247 is set through the GitHub API at each transition instead,
  and this file remains the authoritative phase state.
