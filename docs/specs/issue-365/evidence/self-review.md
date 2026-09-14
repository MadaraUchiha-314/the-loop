---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#365"
---

# Self-review: retire the execution log

> The `self-review` node's proof, written under the shape this work item introduces —
> this directory is the dogfood: `docs/specs/issue-365/` carries no execution log.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| 1 | the-loop (self) | new findings | 3, all fixed before the first push — see below | this PR |
| 2 | the-loop (self) | zero (converged) | re-read the diff after the fixes; nothing new | this PR |
| 3 | the-loop (self) | new findings | 1, fixed before the push — see round 3 below | [PR #366](https://github.com/MadaraUchiha-314/the-loop/pull/366) |

### Round 3 finding (after the owner's review round)

**A blanket rename clobbered the constant that makes the rename safe.** Sweeping
`graph-state` → `work-item-state` across the tree rewrote
`LEGACY_STATE_FILENAME = "graph-state.json"` — the one place the old name has to survive,
or a work item mid-flight silently loses its pointer. Caught by re-reading the diff rather
than by a test, because the tests for it were written against the constant and would have
passed while asserting nothing. Fixed, and the case is now pinned by
`test_a_work_item_mid_flight_keeps_its_pointer_across_the_rename`, which writes the literal
old filename.

A second, smaller one the tests did catch: `WorkItemState.load` read `repos` with a list
comprehension, so a state file carrying `"repos": "octo/app"` deserialized into eight
one-character repositories. Now a non-list is *no declaration*, which is what every other
absence in this key means.

### Round 1 findings

1. **The design said `produces:`, the implementation used `validates:`.** Drafting the
   design I reasoned that a per-node record makes "this node wrote it" true again, so
   `produces:` was the honest verb. Implementing it showed why not: `produces:` is bound to
   a **phase** by the manifest and checked in both directions by the parity suite (P1/P2),
   and five of the six review-chain nodes deliberately carry no phase. `validates:` is the
   correct verb and the smaller change. Design D1 and decision-126 were rewritten to match
   what shipped rather than left describing an intention.
2. **A skipped node's gate never runs at all.** The design's first D2 justified one file
   per node by planned-absence leakage through `skipped_artifacts`. Reading
   `Runtime._route_skips` showed the stronger fact: a declared-skipped node is routed past
   before its chain is entered, so the leak needs a *shared* subject to exist. The
   conclusion (one file per node) survives; the reason was corrected, and the remaining
   real risk — a gate satisfied by another node's writing — is now what the design argues,
   with a test (`test_one_nodes_record_never_satisfies_another_nodes_gate`).
3. **Test side effects reached the working tree.** `uv run pytest` rewrote
   `.the-loop/portable/github-octo-repo-15.json` and `uv.lock`. Neither belongs to this
   change; both were reverted. The portable-record write is a pre-existing test-hygiene
   defect in this repository, not caused here, and is left for its own ticket.

### What was re-read adversarially

- Every `validates:` target against the bundled template that has to satisfy it (P3/P5c
  assert this, but the templates were also read by hand).
- All five graphs for an emptied `entry:` chain — one node (`pdlc-pr-loop`'s `complete`)
  now carries `entry: []`, which the compiler accepts and which matches its `exit: []`.
- The three e2e scenarios for a gate whose fixture was deleted but whose `complete:` step
  remained: `ask-reply` needed `evidence/verification.md` because it declares
  `test-planning` away, and that was found by running the suite, not by reading it.
