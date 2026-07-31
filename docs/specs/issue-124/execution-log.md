---
type: execution-log
workItem: issue-124
phase: needs-review       # not-started | brainstorming | requirements-definition | design | tasks-breakdown | implementation | needs-review | complete
status: in-progress          # in-progress | complete
---

# Execution Log: a bugfix-shaped work item cannot clear the gate its own process ships

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-07-31 | pending (PR) | Phase-1 artifact is `bugfix.md` **on purpose** — the-loop's own gate runs on every spec folder a PR touches, so this file passing CI is the regression test for the headline defect |
| design | 2026-07-31 | pending (PR) | Two halves: alternation in the `produces` contract, and the parity test that makes the disagreement impossible to reintroduce |
| tasks-breakdown | 2026-07-31 | pending (PR) | 11-task DAG, red-first |
| implementation | 2026-07-31 | pending (PR) | T1–T11 |
| needs-review | 2026-07-31 | pending | Tier 3 ⇒ `human-approves-pr`; completes when the PR merges |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#127](https://github.com/MadaraUchiha-314/the-loop/pull/127) | spec + T1–T11 | open |

## Progress entries

### 2026-07-31 — the decision, and two defects the ticket did not have

The ticket left the direction to the maintainer, so that was settled before any spec was
written ([paper trail](https://github.com/MadaraUchiha-314/the-loop/issues/124#issuecomment-5138098667)):
**Option 1**, teach the graph the alternative; and the five existing `bugfix.md` specs stay
as a historical record rather than being renamed.

Root-causing then turned up two more instances of the same mismatch that the ticket had
not seen, both found by walking the gate's code rather than reading the prose:

- **RC2 — the security check has been skipping for every bug.** The `design` node's
  `enforces-boundaries-from` hook names its upstream `requirements.md` literally. For a bug
  that file does not exist, so the hook took its `not up.is_file()` branch and returned
  **skip** — and a skip passes the chain. The check that every trust boundary raised in
  phase 1 is answered in `design.md` has therefore never run for a `bugfix.md` work item,
  while reporting success. Strictly worse than the ticket's defect, which at least failed
  loudly. The hook had **no tests at all**, which is how it survived.
- **RC3 — the bundled template cannot satisfy its own node.** The
  `requirements-definition` node requires a `Requirements` section;
  `templates/bugfix.md` offered `## Acceptance criteria (EARS)`. Fixing only the filename
  moves the block one line down. This is also what #119's workaround actually consisted
  of — not just renaming the file but *also* retitling its criteria — and neither half was
  written down.

Also filed **#125**: six review nodes (`self-review`, `critic-review`, `security-review`,
`evidence`, `capability-docs`, `reviewer-briefing`) declare `sections:` with no
`produces:`, so `validate-artifacts` returns `skipped("this node declares no artifacts")`
and those gates have never executed either. Same family as RC2. Kept out of this change
deliberately: it is a change to the node contract with its own blast radius, and folding it
in would bury this fix.

### 2026-07-31 — the reproduction

```console
$ uv run the-loop check issue-104 --recompute
issue-104: UNMET (at requirements-definition)
  BLOCK  requirements-definition
         · required artifact is missing (docs/specs/issue-104/requirements.md)
```

`docs/specs/issue-104/` is a complete, merged, shipped work item. It is blocked at phase 1
for the absence of a file the process told it not to write.

### 2026-07-31 — red, then green (T1–T9)

The two reds arrive in sequence, and the sequence is the finding:

1. **P1 red on the untouched tree** — `bugfix.md (manifest phase
   'requirements-definition'; that phase's node(s) accept ['requirements.md'])`.
2. Ten hook/model tests red for the documented behaviours (alternation, ambiguity,
   `enforces-boundaries-from` on a bug).
3. T3–T7 land the resolver, the two hooks and the graph. **P3 goes red** —
   `bugfix.md: node 'requirements-definition' requires a 'Requirements' section the
   template does not offer`. The test, not a person, discovered that the name fix moved
   the block one line down.
4. T8 fixes the template. All green.

### 2026-07-31 — the five historical bug specs, precisely

After the fix, `the-loop check issue-104 --recompute` resolves `bugfix.md` — the name
mismatch is gone — and blocks on the `## Acceptance criteria (EARS)` heading that spec was
written with in the pre-graph era. Per the maintainer's call those five specs (36, 78, 80,
93, 104) are left alone: they are closed work items and nothing re-runs their gates.

**The one consequence worth knowing:** the-loop's gate runs on spec folders a PR *touches*,
so a future PR that touches one of those five folders would block on its old heading. Not
worth pre-emptively rewriting five closed specs for; recorded here so the answer is on file
if it ever happens.

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self (behaviour delta on the untouched path) | the-loop session | Found one: resolving the downstream through *present* files alone silently turned "downstream declared but missing" from a block into a skip in `enforces-boundaries-from`. Unreachable in the shipped graph (the earlier `validate-artifacts` short-circuits the chain first), but a weakening in a hook whose whole defect this work item is about. Restored the original semantics — gate on what the node *declares*, read what is *present* — and pinned it | `test_a_declared_but_missing_downstream_still_blocks` |
| 2 | self (does the parity test measure what the gate measures?) | the-loop session | Found one: P3 extracted template headings with its own regex, while `validate-artifacts` uses `frontmatter.sections`, which ignores headings inside fences. A template could have been called compliant on the strength of a heading in an example block. P3 now uses the gate's own parser | `test_graph_parity.py` § P3 |
| 3 | self (is the new syntax the smallest thing that works?) | the-loop session | No change. Checked the three consumers of `produces` (`as_mapping` → `graph show --format json`, both hooks) and the alternatives in decision-045 § Alternatives considered. One note recorded rather than acted on: hook **params** (`upstream`, `sections`, `markers`) are not compile-validated for any hook, so a malformed `upstream: "a\|\|b"` would resolve silently where a malformed `produces` raises. Consistent with how every other param behaves today; a per-hook param schema is a contract change, not this fix | decision-045 § Alternatives considered |
| 4 | critic | — | **Not run: `reviews.critics: []`** — no critic harness is configured in this repository, so `the-loop critic run` has nothing to invoke. Recorded rather than silently skipped |
| 5 | human (PR approval) | @MadaraUchiha-314 | pending | PR #127 |

## Security review (gate)

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`).
- **Outcome:** pass, and the change moves the security posture **forward** rather than
  leaving it flat.
  - **No new input reaches the changed code.** `produces` and `upstream` come from
    `pdlc.yaml`, which ships with the CLI; a repo-supplied graph is ignored with a warning
    (R1.4). Every alternation entry is authored by the-loop's maintainers and reviewed as
    code. No payload text, no network input, no user-supplied path.
  - **The filesystem boundary is unchanged.** `resolve_produces` joins names to
    `work_item.spec_dir` exactly as the single-name path did, and the name set is fixed at
    compile time, so the resolver cannot be steered to a path outside the spec folder.
  - **The one real abuse case — weakening a gate to get green — is answered twice.**
    Ambiguity **fails closed**: two artifacts filling one slot block, never a lucky pick,
    so nobody clears a gate against a stale artifact sitting beside the live one. And every
    alternative runs the full validation (`locked`, `frontMatter`, `sections`,
    `checkmarks`) unchanged — the name became flexible, the standard did not move.
  - **Message construction is unchanged in kind:** `Message.text` still interpolates only
    the-loop's own vocabulary plus paths and artifact names that came from the shipped
    graph, never payload text (R3.6).
  - **A previously inert gate is now enforced.** RC2's fix means a bug spec naming a trust
    boundary its design ignores now blocks where it used to pass. "No new attack surface"
    is accurate, and one existing gate goes from advisory to real.
- **Human sign-off:** not required — risk tier 3 < `security.review.humanSignOffMinTier: 4`.

## Final validation evidence

- **Test suite:** 868 passed, 1 skipped (867 before; +19 tests, of which 3 are the new
  parity assertions and 5 are the first tests `enforces-boundaries-from` has ever had). No
  pre-existing test was modified.
- **Toolchain:** `ruff check` / `ruff format --check` clean, `pyright` 0 errors,
  `markdownlint-cli2` 0 errors across all markdown.
- **The reproduction, inverted:**

  ```console
  $ uv run the-loop check issue-124 --recompute
  issue-124: UNMET (at requirements-approval)
    WAIT   requirements-approval
           · no authorized feedback yet
  ```

  A work item whose phase-1 artifact is `bugfix.md` clears `requirements-definition` and
  parks at the human gate — the correct state for an open PR.
- **AC coverage:**
  - R1.1–R1.3 — `TestProducesNamesAnArtifactNotAFile` in `test_graph_model.py`: splitting,
    whitespace, the five malformed forms, node+entry named in the error, the entry kept
    verbatim in `as_mapping()`, and `test_a_single_name_node_reports_missing_exactly_as_before`
    pinning the unchanged single-name message.
  - R2.1–R2.4 — `test_a_bugfix_spec_satisfies_the_phase_one_gate`,
    `test_a_requirements_spec_still_satisfies_the_phase_one_gate`,
    `test_an_alternative_is_held_to_the_same_standard`,
    `test_neither_name_present_blocks_and_lists_every_accepted_name`,
    `test_both_names_present_blocks_as_ambiguous`.
  - R3.1/R3.2 — `test_a_boundary_named_in_a_bugfix_is_enforced_in_the_design`,
    `test_a_boundary_a_bugfix_raises_and_the_design_drops_blocks`,
    `test_a_requirements_upstream_still_blocks_on_a_dropped_boundary`,
    `test_a_genuinely_absent_upstream_is_still_skipped`,
    `test_a_declared_but_missing_downstream_still_blocks`.
  - R4.1/R4.2 — `templates/bugfix.md` now carries `## Requirements` with the EARS criteria
    nested under it; reproduction / expected-vs-actual / root-cause untouched. Asserted by
    P3.
  - R5.1–R5.4 — `cli/tests/test_graph_parity.py` P1/P2/P3; both went red before the fix,
    in the order recorded above.
  - R6.1 — every test above fails on the pre-fix tree.
  - R6.2 — `bugfix.md` retired from nothing: SKILL.md, `reference/workflow.md`, the
    manifest, `commands/work-on.md` and `commands/work-status.md` all still bless it, now
    stating that both names clear the same gate and only one may be present.
  - R6.3 — `docs/capabilities/process-graph.md` § "What a node `produces`" and
    `docs/decisions/decision-045.md`.
- **Regression check:** a single-name `produces` behaves bit-identically — same resolution,
  same message text, same `path`, same aggregation. The only nodes whose behaviour changes
  are `requirements-definition` (now accepts `bugfix.md`) and `design` (its boundary check
  now runs for bugs instead of skipping).

## Capability docs

- [`docs/capabilities/process-graph.md`](../../capabilities/process-graph.md) — new
  § "What a node `produces`" (the artifact-not-filename rule, the three slot outcomes,
  compile-time validation, verbatim reporting, `upstream`, and the parity requirement);
  issue-124 history row.
- [`docs/capabilities/spec-workflow.md`](../../capabilities/spec-workflow.md) —
  `requirements.md`/`bugfix.md` stated as two names for one artifact, both-present blocks,
  and that the choice is about which shape fits the work rather than which one passes;
  issue-124 history row.
