---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#429"
---

# Self-review: the stop gate blocks on a node the work item never entered

> The self/critic review before requesting human review
> ([`reference/reviewing.md`](../../../../skills/the-loop/reference/reviewing.md)). I read
> the branch diff adversarially, asking two things: what would make CI or a reviewer
> reject it, and in which direction the gate could now be wrong.

## Review cycles

### Cycle 1: the ticket's diagnosis against the code

1. **The ticket's `current: null` does not reproduce on `main`.**
   - The gate reads `currentNode`, not `current`.
   - `core.graphs.check` never returns a null `currentNode` for a repository that
     resolves. `--recompute` sets it to the first unmet node.
   - The ticket's own table (`WAIT phase-selection` first) would have put the gate on
     `phase-selection`, which is a `wait`, so no block.

   I reproduced the symptom a different way: a recorded selection with the pointer
   still at `phase-selection` (`bugfix.md` § Steps to reproduce). The bugfix names the
   real mechanism and says why it differs from the ticket. Both suggested fixes are
   still taken in substance: fix 1 is the new field, fix 2 is the explicit
   inconclusive rule.
2. **Fix 1 taken literally would have broken CI.** Making `--recompute` report the
   pointer as `currentNode` changes `ok` and `--fail-on` for every CI run, and CI's
   contract is "the artifacts alone". I rejected that in favour of a second field
   (`design.md` § Trade-offs).

### Cycle 2: the diff

1. **Found and fixed: a wrong rationale in the first draft.** The first `run_check`
   docstring and a design bullet said `--recompute` is what keeps *verdicts* from
   being forged. Reading `Runtime.status`: both modes call `evaluate` identically.
   Only `currentNode`, `forced` and `parked` differ. Both texts now state the real
   reason, which is that the walk from the graph's start keeps a forward-moved pointer
   from hiding a broken node.
2. **The walk needs the pointer to be in `nodes` first.** Otherwise a pointer naming
   no node would walk the whole graph and reach the downstream blocks, which is the
   bug again by another route. The gate checks membership up front. A test pins it
   (`test_a_pointer_naming_no_node_in_the_report_is_inconclusive`).
3. **A running service serves the old report.** During verification a local
   control-plane service that had auto-started on the pre-change code answered
   without `pointer`. The gate then took the R2.3 path, `currentNode` as the bound,
   which is the old behaviour. It did not crash. So an operator's fix takes effect
   once the service restarts. I noted this in the reviewer briefing rather than coded
   around it: every CLI change reaching a long-running service has this property.

## Checked and left as is

- **Forced nodes.** A pointer `force`d past an unmet node still gets that node demanded.
  This is unchanged, and it is a finding rather than an invention: the item did walk
  past it. It is out of scope in `bugfix.md`.
- **`wait` before the pointer.** The first unmet node is a human `wait`, so the gate
  does not look further, even when the pointer node itself is `block`. This is the
  behaviour before this change, when `currentNode` was that same `wait` node, and it
  is kept deliberately.
- **`--fail-on block` in `check`.** It still bounds by `currentNode` and reads no
  pointer. That is CI's contract and it is unchanged.
- **The long `_state_line` f-string.** It is over 88 columns. `ruff format` leaves
  strings alone and `ruff check` passes, matching neighbouring lines in the module.

## Verdict

Ready for human review. No open findings.
