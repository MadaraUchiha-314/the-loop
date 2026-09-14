---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#365"
---

# Security review: retire the execution log

## Security review (gate)

- **Mechanism:** the-loop's checklist (`reference/security.md`) — this session has no
  built-in `/security-review` skill available.
- **Outcome:** pass, no findings.
- **Findings:** none. The review was run against the diff, not from memory — checklist
  below.

| Checklist item | Verdict |
|---|---|
| New input reaching an argv, a shell or a subprocess | none — the change removes a hook and re-targets gate declarations; no new process is spawned |
| Path traversal | the new `produces`/`validates` values are **graph constants** (`evidence/<name>.md`), never operator or ticket input; `resolve_produces` joins them to the work item's own `spec_dir` (`model.py:257`) and `validate_produces_entry`'s compile-time check is unchanged |
| Authorization boundary moved | no — `phase-selection` still decides which phases run, `routing.authorizedUsers` still bounds who may say so, and `security-review` keeps `skippable: true` with a subject it blocks on |
| A gate weakened | no — every gate that read a section of the execution log reads an equivalent section of a named file, and `validate-artifacts`' fail-closed block (decision-063) plus parity assertion P5a are untouched. Proved by `test_graph_review_chain_integration.py`, which blocks all six nodes on a missing record |
| Secret or token exposure | none — no new file is written by the CLI at all; the records are agent-authored markdown in a tree as public as the repository, and the bundled templates repeat the existing "never a token, a credential or an internal hostname" rule |
| Data destroyed | none — existing `execution-log.md` files are left in place by design (decision-126 D5), and `/the-loop:upgrade-the-loop` is explicitly told never to delete one |

- **Abuse case — "delete the evidence file to pass the gate":** unchanged from today. The
  gate reads the disk on every run, so the node re-blocks; `the-loop status --recompute`
  derives completion from the artifacts alone and ignores stored state. Asserted by
  `test_a_review_node_blocks_when_the_record_is_absent_entirely`.
- **Abuse case — "a declared skip relaxes a neighbouring gate":** refused by construction
  and asserted by `test_a_declared_skip_relaxes_only_its_own_nodes_gate`.
- **Human sign-off:** n/a for the security round itself (no findings); the work item is
  risk tier 4, so the **PR** still requires the owner's approval before it merges.
