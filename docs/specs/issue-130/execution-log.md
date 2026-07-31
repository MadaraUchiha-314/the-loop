---
type: execution-log
workItem: issue-130
phase: needs-review       # not-started | brainstorming | requirements-definition | design | tasks-breakdown | implementation | needs-review | complete
status: in-progress          # in-progress | complete
---

# Execution Log: an index for `portable/`, and a ref you can click

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-07-31 | pending (PR) | Two asks, both navigability: a list of what `portable/` holds, and a clickable ref. The interesting part is what the index must *not* become |
| design | 2026-07-31 | pending (PR) | Three pieces: a property on `WorkItemRef`, index maintenance inside the store's single write funnel, and the `GENERATED_PATHS` classification that drags the docs along |
| tasks-breakdown | 2026-07-31 | pending (PR) | 8-task DAG |
| implementation | 2026-07-31 | pending (PR) | T1–T8 |
| needs-review | 2026-07-31 | pending | Tier 3 ⇒ `human-approves-pr`; completes when the PR merges |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#131](https://github.com/MadaraUchiha-314/the-loop/pull/131) | spec + T1–T8 | open |

## Progress entries

### 2026-07-31 — the shape of the answer, before the code

- **Phase:** not-started → requirements-definition → design → tasks-breakdown
- **Did:** Read every writer that reaches `portable/` (`control.py`, `poller/poller.py`,
  both through `WorkItemStore`) and the classification issue-128 left behind. Two
  findings decided the design:

  1. **The index must be derived and read by nothing.** `portable/` is tracked, which is
     what makes an index worth having — and also what makes it *proposable by strangers*
     on a repository that accepts pull requests. An index nothing reads cannot be an
     input; an index rebuilt on every write cannot drift. Those two properties are what
     the rest of the design protects.
  2. **An index reintroduces the one shared file decision-046 removed.** Before it, two
     machines conflicted only over a work item they both worked. This is a real cost, not
     an oversight — accepted because a derived file makes the conflict resolvable by
     taking either side, and recorded as such in decision-047 rather than glossed.

  Also settled: `url` is **added** beside `ref`, never substituted (the slug derives from
  the ref, and the pre-issue-128 shim keys on it), and a URL is omitted rather than
  guessed — `WorkItemRef.parse` splits the path at the *first* slash, so an unchecked
  interpolation can produce a link to a different repository.
- **Checkpoint/tests:** none yet — no code written.
- **Next:** T1, red first.
- **Blockers:** none.

### 2026-07-31 — implementation complete (T1–T8)

- **Phase:** tasks-breakdown → implementation → needs-review
- **Did:**
  - **T1/T2** `WorkItemRef.url` (fail-closed: `github` provider, `[A-Za-z0-9._-]+` names,
    else `""`), stamped onto every record by `write_section` through `_identified()`,
    which also normalises key order so a record's shape does not depend on the order its
    sections were written in.
  - **T3/T4** `INDEX_FILE`, `_records()` (the scan both `refs()` and the index share),
    `_index_entries()` and `_write_index()`, called at the end of `write_section` and
    `drop`. The atomic writer already inline in `write_section` was lifted to
    `_write_json` so the index gets the same crash guarantee — reuse, not a second
    implementation.
  - **T5** `StateLayout.portable_index` + a `GENERATED_PATHS` entry (`portable=True`).
    Adding it is what turned the documentation into a build gate: `test_state_portability`
    stayed red until the row in `docs/cli/state.md` existed, which is the mechanism
    working as intended.
  - **T6/T8** `docs/cli/state.md` (tree, classification row, a section for the index with
    its lifecycle and the conflict rule, and a `ref`/`url` section for the record),
    `docs/config/cli/index.md`, `docs/capabilities/cli.md`.
  - **T7** decision-047.
- **Tests changed on purpose (three):** `test_workitem.py`'s "the directory holds exactly
  the record" and `test_poller.py`'s "a cycle only writes the items it touched" now name
  the *records* explicitly — the index is the deliberate exception, and saying so in the
  assertion is better than an assertion that quietly stops meaning what it says. And
  `test_state_portability.py`'s portable-set pin now lists two names, which is the point
  of that pin.
- **Checkpoint/tests:** `make check` — ruff, ruff format, pyright, config validation,
  markdownlint (321 files) and pytest all green: **924 passed, 1 skipped**, of which 15
  are the new `cli/tests/test_portable_index.py` (11 cases, one of them parametrised over
  4 malformed refs). Red→green was observed on the new file before the implementation
  landed (it failed at import on `INDEX_FILE`, then case by case).
- **Next:** post the reviewer briefing on the PR; the tier-3 gate is the human PR review.
- **Blockers:** none.

## Self-review / critic-review

Recorded as it happened, including the rounds that found nothing — `reviews.stopOnNoNewFindings`
stops the loop when a round is empty, and saying which round that was is the evidence.

| Round | Type | Findings | Outcome |
|---|---|---|---|
| 1 | self (design, pre-code) | Three risks were caught while the design was being written rather than in review, and are in `design.md` because of it: the URL built by interpolating a ref whose `repo` may carry further slashes (`WorkItemRef.parse` splits at the *first* one); an index write that could raise and fail an arming `start`; an index that some later caller would start reading | Designed out: fail-closed name check, `OSError` caught and logged, and "read by nothing" written into the decision and the capability doc as a rule, not an accident |
| 2 | self (post-implementation, code) | `_records()` was annotated `List[tuple]` — true, and useless to a reader or to pyright | Tightened to `List[Tuple[Path, Dict[str, Any]]]` |
| 3 | self (post-implementation, integration) | Checked what else could misread the new file, and what the index costs: no other scanner touches `portable/` (`the_loop.sessions.registry` scans `local/` and additionally requires a `-<number>.json` name); `drop()` maintains the index, including on the empty-record path inside `write_section`; `_identified()` removes a stale `url` when one can no longer be derived; a poll cycle over *n* work items is O(*n*²) small reads, which at one file per actively-tracked item is not worth caching against | No changes. The cost is stated in `design.md` and decision-047 rather than hidden |
| — | critic | `reviews.critics[]` is empty in this repository's harness config — no second harness/model is configured to run one here | Not run; escalated to the human PR review, which is the tier-3 gate anyway |

## Open questions raised on the ticket

- Whether a **markdown** index (clickable on GitHub) is what "easily navigable" meant.
  JSON shipped, for consistency with the directory it indexes; a rendered table is a small
  additive follow-up if the answer is yes.
