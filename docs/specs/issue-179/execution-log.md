---
type: execution-log
workItem: issue-179
phase: needs-review          # not-started | brainstorming | requirements-definition | design | test-planning | tasks-breakdown | implementation | verification | needs-review | complete
status: in-progress          # in-progress | complete
---

# Execution Log: every phase is selectable — the floor moves from the graph to the human

> Append-only log of progress for the user's visibility. Checked in alongside the spec at
> `docs/specs/issue-179/execution-log.md`.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-08 | @MadaraUchiha-314 | selection made in-session on the ticket's own terms: the full chain, because this change moves a security boundary |
| requirements-definition | 2026-08-08 | pending (PR) | first draft scoped to `test-planning` (the ticket's literal ask); rewritten after the owner's direction to make **every** phase selectable |
| design | 2026-08-08 | pending (PR) | one invariant replaces the floor; `onlyWhenSkipped` so a kept gate keeps a subject — decision-068 |
| test-planning | 2026-08-08 | pending (PR) | reviewed with the design, one gate for both (decision-060 D2) |
| tasks-breakdown | 2026-08-08 | pending (PR) | 7 tasks: T1/T2 → T3 → T4 → T5 → T6 → T7 |
| implementation | 2026-08-08 | — | T1–T6 |
| verification | 2026-08-08 | — | T7; every activity ran, red-then-green recorded |
| needs-review | 2026-08-08 | pending | 3 self-review rounds; critic rounds unavailable (no critic configured in `reviews.critics`) |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#180](https://github.com/MadaraUchiha-314/the-loop/pull/180) | the whole work item — T1–T7 | open |

## Progress entries

### 2026-08-08 — spec chain written, then rewritten to the owner's scope

- **Phase:** requirements-definition → tasks-breakdown
- **Did:** wrote `requirements.md` and `design.md` for the ticket as filed — make
  `test-planning` selectable — including the piece that ask implies but does not state:
  `verification` gates `testing-plan.md`, so once the plan can be declared away the gate
  needs its subject moved rather than lost. Mid-phase the owner directed that **all**
  phases be selectable and skippable, and chose "everything except the selection gate
  itself" over the two narrower options offered. Rewrote `requirements.md` (R1 widened,
  risk tier raised to 5, the security section rewritten around a *dismantled* boundary),
  `design.md`, `testing-plan.md` and `tasks.md` to that scope.
- **Checkpoint/tests:** none yet — spec phase.
- **Next:** implement T1–T2.
- **Blockers:** none. The scope question was resolved by asking the owner directly rather
  than by inferring it; that exchange is the paper trail for the reversal.

### 2026-08-08 — implementation (T1–T6)

- **Phase:** implementation
- **Did:** ten `skippable: true` markers and ten `on: skipped` edges in
  `pdlc-work-item-loop.yaml`; `required: true` traded off `security-review` and
  `human-approval` (a node cannot be both) and kept on `phase-selection`; `spec-chain`
  extended with `test-planning` and a new `review-chain` set; `validate-artifacts` gained
  `onlyWhenSkipped:` and `verification` a conditional second entry over the execution log;
  `## Verification results` added to `templates/execution-log.md`; the `phase-selection`
  checklist copy rewritten for a loop that protects nothing but the gate. Docs, the
  decision record and the pointers back from decisions 063 and 067 followed.
- **Checkpoint/tests:** `uv run --directory cli pytest -q` → 1480 passed, 1 skipped.
- **Next:** verification (T7).
- **Blockers:** none.

### 2026-08-08 — verification (T7)

- **Phase:** verification
- **Did:** ran the testing plan. Reverted the four changed source files to `HEAD` with the
  new tests in place to record the red (11 failures), restored them for green, and ran the
  parity red in isolation because `test_p5c` can only fail once the graph gates the new
  section. Scripted the ticket's scenario against the **shipped** graph — the operator verb,
  the selection gate, `check`, the `verification` node both ways, and a forged declaration
  on `phase-selection`.
- **Checkpoint/tests:** full suite 1480 passed / 1 skipped; ruff, ruff format, pyright,
  markdownlint and `validate_config.py` all clean. Evidence under `evidence/`.
- **Next:** review chain.
- **Blockers:** none.

## Verification results

> This work item **kept** `test-planning`, so its results live in
> [`testing-plan.md`](testing-plan.md) § Verification results, against the matrix rows they
> were planned from. This section stays as the template offers it — which is itself the
> shape issue-179 introduced.

## Review cycles

> Outcome is one of: new findings · zero (converged) · escalated · **unavailable** (the
> configured critic could not run — it does NOT count toward `reviews.criticReviewCount`).

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | agent | new findings — the `verification` node would have asserted **nothing** once `test-planning` became selectable (issue-177's planned-absence branch returns `skipped`, and a skip is not a decision). Fixed by `onlyWhenSkipped` + the execution-log fallback, with the block pinned by an integration test | this PR |
| 2 | self | agent | new findings — the checklist's closing line still read "a doc fix usually needs **none** of the selectable phases", which after the widening reads as "skip implementation and verification too". Reworded to "little more than implementation and verification". Also: `test_p5c` would have blocked every work item authored from the bundled template if the section had not been added — caught by running the parity test in isolation rather than assuming | this PR |
| 3 | self | agent | new findings — `graph force`'s "bypasses a required node" warning is driven by `node.required`, so trading the two markers silently narrows it to `phase-selection`. Not a defect to fix (restoring the warning means restoring the marker) but a consequence that must be *written down*: recorded in decision-068 § Consequences | this PR |
| 4 | critic | — | **unavailable** — `reviews.critics` is empty in this repository's `harness-config.yaml`; no external critic could be run | — |

## Security review (gate)

> Required before ready-to-ship (`security.review.required`). See `reference/security.md`.

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`; no built-in
  security-review skill was available in this session, so the checklist is the mechanism).
- **Outcome:** pass, with the residual named rather than mitigated. This work item
  *widens* a security boundary by design, so the review is about what remains:
  1. **Trust boundaries enforced where the design says** — the vocabulary is still shipped
     package data (a repo-supplied graph is ignored); `Runtime.declared_skips` still
     re-filters every declaration through the compiled `skippable` set on every read;
     `phase-selection` is `required: true` and refused by `expand_skip_tokens` (proved in
     the walkthrough, both via the CLI verb and via a hand-written state file).
  2. **Untrusted input** — no new input surface. The selection gate's parsing,
     authorization and freezing are untouched.
  3. **Untrusted content cannot steer privileged behaviour** — the agent still has no
     channel: self-marked comments are dropped before authorization, it is not in
     `authorizedUsers`, and the prohibition is restated in `SKILL.md`,
     `reference/workflow.md` and `reference/security.md`.
  4. **AuthZ fails closed** — unchanged: no authorized reply → no phase runs at all.
  5. **Least privilege / secrets** — nothing added; no credentials, no network, no new
     dependency.
  6. **Abuse cases have negative tests** — the gate's inertness against a forged
     declaration (`test_a_forged_skip_on_a_protected_node_is_inert_and_surfaced`, plus the
     walkthrough's step 5); `onlyWhenSkipped`'s three dormancy tests, which are what stop a
     conditional gate from becoming a switched-off one; the hollowed-`verification` case.
  7. **The residual, stated:** in-repo enforcement is now *audit alone*, not audit + floor.
     A human may legitimately declare the security review and the approval gate away.
     Written into `requirements.md` § Security considerations, `decision-068` §
     Consequences and `reference/security.md` — the mitigation is attribution and
     visibility, and it should be read before this is relied on at a high risk tier.
- **Human sign-off:** pending — risk tier 5 is above
  `security.review.humanSignOffMinTier: 4`, so this needs @MadaraUchiha-314's named
  sign-off on the PR review. The widening itself is already the owner's directive on the
  ticket; the sign-off being recorded here is what closes the gate.

## Final validation evidence

Acceptance criteria, mapped onto what was run (raw output in [`evidence/`](evidence/)):

| Requirement | Proved by |
|---|---|
| R1.1, R1.2 (the vocabulary and the invariant) | `test_shipped_outer_loop_marks_every_phase_but_the_gate_skippable`, `test_the_selection_gate_itself_can_never_be_declared_away`; walkthrough step 1 (16 selectable rows) and step 5 (a forged declaration on the gate is inert) |
| R1.3 (`required` traded) | `test_the_former_floor_is_now_declarable_and_carries_no_required_marker` |
| R1.4 (routing authored, forward) | `test_every_skippable_node_routes_forward_on_skipped` + compile-time validation |
| R1.5 (skip sets) | `test_shipped_skip_sets_name_the_two_chains`, `test_skip_declares_against_the_shipped_vocabulary` |
| R1.6 (inner loop untouched) | `test_shipped_pr_loop_declares_no_skippable_node`, `test_graph_loops.py` (inner `security-review` still required) |
| R1.7 (checklist copy) | `test_the_checklist_says_so_when_nothing_is_protected`, `test_the_shipped_checklist_offers_every_phase_the_item_walks` |
| R1.8 (routing, recording, reporting) | `test_declaring_every_phase_away_walks_the_item_to_its_terminal`; walkthrough steps 2–3 |
| R2.1–R2.4 (a kept gate keeps a subject) | the three new `test_graph_verification_integration.py` cases; walkthrough step 4 |
| R2.5 (template offers the section) | `test_p5c_every_validated_section_exists_in_that_artifacts_template`, red in isolation before the section existed |
| R3.1–R3.3 (`onlyWhenSkipped` narrows only) | the four `only_when_skipped` cases in `test_graph_hooks.py` |
| R4.1–R4.4 (the paper trail) | `decision-068.md` + index; pointers in `decision-063.md` and `decision-067.md`; `SKILL.md`, `reference/workflow.md`, `reference/security.md`, `docs/capabilities/process-graph.md`, `docs/cli/commands/graph.md`, `commands/verify-work.md`, `docs/guide/what-is-the-loop.md` |

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`docs/capabilities/process-graph.md`](../../capabilities/process-graph.md) | Declared skips: the vocabulary is now every node but `phase-selection` and the terminals; `required` in the outer loop means exactly one node; `onlyWhenSkipped` and the `verification` fallback added as behaviour; the `test-planning`/`verification` section says what happens when the plan was declared away | `issue-179` row added at the top of § History |

## Documentation

| Document | What changed |
|----------|--------------|
| `skills/the-loop/SKILL.md` | The declared-skips rule now says every phase is selectable and names the `phase-selection` invariant as the floor |
| `skills/the-loop/reference/workflow.md` | § Declared skips rewritten: the widened vocabulary, the two skip sets, the invariant, the kept-gate fallback; the inner-loop paragraph corrected |
| `skills/the-loop/reference/security.md` | A note at the security-review gate: the node is selectable by an authorized human, never by a session, and the tier sign-off policy is now upheld by the person |
| `skills/the-loop/templates/execution-log.md` | New `## Verification results` section, used when `test-planning` was declared away |
| `commands/verify-work.md` | Step 1 tells `verify-work` what to do with no `testing-plan.md` — verify on the merits and record in the execution log, never re-author the artifact a human declared away; step 5 follows |
| `docs/cli/commands/graph.md` | `skip` documents `review-chain`, the widened vocabulary and the one token it always rejects |
| `docs/guide/what-is-the-loop.md` | The "security review that cannot be skipped at any risk tier" line corrected to what is now true |
| `docs/decisions/decision-068.md` (+ `decisions.md`, pointers in 063 and 067) | The reversal, the invariant, the residual and the `force`-warning consequence |
