# Evidence: abuse-case inspection (T8) and the no-retro-fit check (T12)

Work item: issue-164 · rows T8 and T12 of [`../testing-plan.md`](../testing-plan.md).

## Abuse case 1 — a path in the section is never consumed by code

The claim in [`../design.md`](../design.md) §Security design is that a hostile path string
in a design document has nowhere to go, because nothing reads, resolves, opens or fetches
the paths the section lists. The proof is the diff: `cli/` gains no statement that touches
one. Every change under `cli/` is either a test or the single YAML list entry.

```console
git diff --stat -- cli/
 cli/tests/test_graph_hooks.py | 69 +++++++++++++++++++++++++++++++++++++++++++
 cli/tests/test_graph_model.py | 37 +++++++++++++++++++++++
 cli/the_loop/graph/pdlc.yaml  |  6 +++-
 3 files changed, 111 insertions(+), 1 deletion(-)
```

The non-test change in full — one string appended to a list `validate-artifacts` already
iterates, plus the comment explaining why:

```diff
--- a/cli/the_loop/graph/pdlc.yaml
+++ b/cli/the_loop/graph/pdlc.yaml
@@ -68,7 +68,11 @@ nodes:
     stage: design
     entry: [set-phase-label, log-entry]
     exit:
-      - {hook: validate-artifacts, with: {locked: true, sections: ["Architecture", "Security design", "Testing strategy"]}}
+      # `Module structure` (issue-164) is where the code will land: the tree of
+      # paths the work item creates, changes or removes. It is gated rather than
+      # suggested because a reviewer who cannot see the layout at this node sees
+      # it in the diff instead — after approving the design.
+      - {hook: validate-artifacts, with: {locked: true, sections: ["Architecture", "Module structure", "Security design", "Testing strategy"]}}
```

`validate-artifacts` resolves the section by string comparison against parsed headings
(`cli/the_loop/graph/hooks/artifacts.py`) and checks the body is non-empty. No path
resolution, no filesystem call on a listed path, no subprocess, no network.

## Abuse case 2 — the section cannot be ticked by its own heading

Covered by an executed test rather than an argument:
`test_a_module_structure_heading_with_nothing_under_it_blocks` writes a design carrying
every gated section with `## Module structure` left bare, runs the shipped gate's real
params through the hook, and asserts `empty: Module structure`. See
[`unit.md`](unit.md) §T3.

## Abuse case 3 — a work item that legitimately changes no code

`test_a_work_item_that_changes_no_code_still_clears_the_gate` writes the one-sentence
answer R1.6 prescribes and asserts the gate passes. The gate is therefore not a reason to
invent a module tree, and the section is never deleted to get past it.

## T12 — no pre-existing spec was re-authored

Gates run forward: the ~30 designs already under `docs/specs/` carry no `Module structure`
section and are untouched by this change. The only addition under `docs/specs/` is this
work item's own directory.

```console
git status --porcelain -- docs/specs/
  ?? docs/specs/issue-164/
```
