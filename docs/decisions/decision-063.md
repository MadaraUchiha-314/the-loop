# Decision 063: Where the code will land is a gated section of `design.md`, not a new artifact

- **Status:** proposed
- **Date:** 2026-08-06
- **Deciders:** @MadaraUchiha-314 (issue #164)
- **Work item:** issue-164
- **Spec:** `docs/specs/issue-164/`
- **Refines:** [decision-041](decision-041.md) (the PDLC is an executable graph) and
  [decision-004](decision-004.md) (the Kiro 3-phase spec). Nothing in either is reversed;
  this adds one section to the design artifact and one condition to the node that locks it.

## Context

[Issue #164](https://github.com/MadaraUchiha-314/the-loop/issues/164). `design.md` told a
reviewer what the components are, what they are responsible for and how they interact. It
never told them **where the code would live**. Neither the bundled template nor the `design`
node's gate asked for the files, modules or packages the work item would create, change or
remove.

So a reviewer who wanted the layout had two options, and both are too late or too indirect:

- read `tasks.md`, which describes *work* — "add the parity test", "fold in the docs" — and
  names paths only incidentally; or
- wait for the diff, which arrives after the design has already been approved.

Placement is a design decision. It is where "should this live in `cli/` or in the skill?"
gets settled, and it is one of the few design questions a reviewer can answer quickly and
usefully. Leaving it out of the artifact meant the loop asked for approval of a shape it had
not shown.

## Decision

**One section, gated at the node that locks the artifact.**

`skills/the-loop/templates/design.md` gains `## Module structure`, between
*Components & interfaces* (what the parts are) and *UI/UX design*. It carries a tree of
repository-relative paths marked `new` / `changed` / `removed`, a table giving each path a
one-line responsibility and the requirement it serves, and a mermaid dependency diagram when
three or more of those modules depend on one another.

`cli/the_loop/graph/pdlc.yaml` adds `"Module structure"` to the `design` node's
`validate-artifacts` `sections:` list, beside `Architecture`, `Security design` and
`Testing strategy`.

| Sub-decision | What was chosen | Why |
|---|---|---|
| **D1 — gated, not advisory** | The section is a condition of the `design` gate | A rule stated in prose and held by nothing goes missing. issue-124 (a gate that resolved to nothing and reported success) and issue-148 (prose and graph drifting apart) are the two times this repository paid for the alternative. The cost is a hard stop on a design that omits the section, including for a one-file change — accepted, because that design costs one sentence to fix. |
| **D2 — a section, not an artifact** | `design.md` §Module structure, not `module-structure.md` | A separate artifact would need a node, a lock, a template, a manifest entry and parity coverage to say what one heading says. The chain is long enough that adding a link needs a stronger reason than tidiness — the same argument [decision-060](decision-060.md) §D3 made for keeping verification results inside the testing plan. |
| **D3 — at `design`, not `tasks-breakdown`** | The node that locks `design.md` | By tasks-breakdown the shape is already approved, and the question "should this live here?" has stopped being answerable cheaply. |
| **D4 — the delta, not the repository** | Scoped to what the work item touches | `docs/architecture/architecture.md` is the standing view. A section that re-renders the whole tree buries the four paths that actually change, and it is stale the day after it is written. |
| **D5 — no config knob** | The section is unconditional | `design.moduleStructure.required` would be a switch for turning off a gate nobody has asked to turn off, and every other gated section of every other node is unconditional today. Minimalism ladder: YAGNI. |
| **D6 — no retro-fit** | Existing specs are untouched | Gates run when a node runs, so the designs already in `docs/specs/` are unaffected and no build goes red over history. Re-authoring twenty designs to satisfy a new heading would be editing the record for a green build — the abuse case [issue-165](../specs/issue-165/design.md) wrote a test to prevent. |

### A work item that changes no code

The gate treats an empty required section as a finding, which is what stops "TBD" from
being a way through — and it is also why a docs-only work item needs an explicit answer.
The template's rule: say so in one sentence and name the files that *do* change. A gated
section is never deleted to shorten a document
([decision-061](decision-061.md) and the `the-loop:writing` skill).

### What holds it

`cli/tests/test_graph_parity.py` P3 already walks every gated section of every producing
node and asserts the bundled template offers it, read through the gate's own heading
parser — so gating a section the template does not carry is red without an edit to that
test. `cli/tests/test_graph_model.py` pins the design gate's section set, and
`cli/tests/test_graph_hooks.py` proves the three cases that matter against the shipped gate:
a missing section blocks, an empty one blocks, and a one-sentence no-code answer passes.

## Alternatives considered

- **A template section with no gate.** Cheapest, and reversible. Rejected as D1: the
  measured outcome of an ungated rule in this repository is that it is skipped, and the
  phase labels issue-73 found unused are the same shape of evidence.
- **Put the module structure in `tasks.md`.** The DAG already names paths. Rejected as D3:
  it answers the question after the design gate, and it answers it as a by-product of
  describing work rather than as a claim a reviewer can check.
- **Generate the structure from the diff at review time.** Accurate by construction, and
  useless for the purpose — the point is to show the layout *before* the code exists.
  Worth revisiting as a **verification** aid: a later work item could compare the section
  against the delivered diff and report divergence. R4.3 records the manual version of that
  in the meantime (divergence goes in the PR briefing).
- **Extend `Components & interfaces` instead of adding a heading.** Rejected: a gate can
  only require a section it can name, and merging placement into a section about contracts
  is what left placement unstated in the first place.
