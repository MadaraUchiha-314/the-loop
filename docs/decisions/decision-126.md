# Decision 126: the execution log is retired; each gate keeps one record of its own under `evidence/`

- **Status:** proposed
- **Date:** 2026-09-14
- **Deciders:** the-loop (architect, engineer), reported by @MadaraUchiha-314
- **Work item:** [issue-365](https://github.com/MadaraUchiha-314/the-loop/issues/365)

## Context

`docs/specs/<id>/execution-log.md` was two different things wearing one name.

**A narrative.** A 130-line bundled template materialized into every work item; a phase
transitions table; append-only progress entries; a `log-entry` hook appending a checkpoint
at 47 node boundaries across five shipped graphs; a `phase:` front-matter field mirroring
the ticket label; and a prose entry — *Did / Checkpoint / Next / Blockers* — demanded
before every context reset. Every fact in it existed elsewhere first: the current node,
attempts and declared skips in `work-item-state.json`, the coarse phase on the `loop:<phase>`
label, the chronology in the harness's own transcript, the red→green evidence in the
commits.

**A set of proofs.** Eight sections that six review-chain nodes, plus `verification`'s
kept gate and the opt-in `design-critic-review`, read as their exit condition. Those gates
exist because they once did not: before issue-167 all six declared `sections:` and no
artifact, so `validate-artifacts` resolved nothing, returned *skipped*, and — a skip not
being a decision ([decision-060](decision-060.md)) — the chain passed straight through
`security-review` included ([decision-063](decision-063.md)).

The ticket is about the first: *"generating the execution log is costing a LOT of tokens —
agent harnesses already maintain a log of what has happened, we don't need that to be
generated again."*

## Decision

**Delete the narrative. Give each gate one small record of its own, under `evidence/`.**

| Node | Record it gates | Section(s) |
|---|---|---|
| `design-critic-review` (opt-in) | `evidence/design-critic-review.md` | Design critic review |
| `self-review` | `evidence/self-review.md` | Review cycles |
| `critic-review` | `evidence/critic-review.md` | Review cycles |
| `security-review` | `evidence/security-review.md` | Security review (gate) |
| `verification` (only when `test-planning` was declared away) | `evidence/verification.md` | Verification results |
| `evidence` | `evidence/final-validation.md` | Final validation evidence |
| `capability-docs` | `evidence/documentation.md` | Capability docs, Documentation |
| `reviewer-briefing` | `evidence/pull-requests.md` | Pull requests |

And with it:

- The `log-entry` hook is deleted from the registry and from all 47 entry chains. A node
  boundary is already an event in the event log and a transition in `work-item-state.json`.
- The bundled `execution-log.md` template is deleted; the `execution-log` role leaves
  `.the-loop/manifest.yaml`.
- The multi-repo `repos:` declaration (issue-183) leaves the log. It shipped in
  **`tasks.md`**'s front matter and moved again the same day, on the owner's review, to
  the `phase-selection` gate and `work-item-state.json` — see
  [decision-127](decision-127.md), which supersedes this bullet and the alternative below.
  Absence still means *no declaration*, never an empty one.
- The **checkpoint-then-reset** protocol keeps its discipline and loses its prose: tick the
  checkmarks, commit, keep the label in sync. A fresh window re-enters from
  `work-item-state.json` and the first unticked task — which is what "Next:" said, derived
  rather than written.
- `resolve_session`'s dead-session fallback seeds `requirements.md`, `design.md`,
  `tasks.md`.

**One file per gate, never one shared record.** A shared `Review cycles` section would let
`critic-review` pass on the round `self-review` wrote — which is what the shared execution
log did. Separate files make each assertion its own; a skipped node is routed past before
its chain runs, so a skip removes exactly one assertion.

**Each gate keeps the `validates:` verb it already used.** `produces:` is not a synonym for
authorship here: it names the artifact a **phase** is judged by, and the manifest binds
each to a phase the parity suite checks in both directions. Five of the six review-chain
nodes deliberately carry no phase — the chain was one `needs-review` label, and minting a
label per node would change every consuming repository's vocabulary — so `produces:` would
force either a phase they must not have or a manifest entry P1 cannot satisfy. It also
keeps `skipped_artifacts` (which reads `node.produces`) empty of these names, so no
declared skip can soften a gate the work item still walks.

**Existing logs are left exactly where they are.** 132 in this repository, more in
consuming projects. They are the operator's record of work already done, so they are *not*
in `manifest.deprecated` (everything there is safe-to-delete plugin internals) and
`/the-loop:upgrade-the-loop` reports them as no longer read rather than removing them —
the precedent the relocated learnings tree set. Nothing in the-loop reads one, so a log on
disk changes no gate's outcome.

## Alternatives considered

**Drop the gates with the log.** The smallest reading of "remove this functionality":
delete the eight sections and the nodes' `sections:` checks. Rejected — it would also
delete `validate-artifacts`' fail-closed block, parity assertion P5a and decision-063, and
return six nodes to reporting success on every run without asserting anything. That is the
defect issue-167 was filed for, and it is not what costs tokens: the proofs are a handful
of lines written once by the node that ran, while the narrative was a template, 15–17 hook
appends and a prose checkpoint per reset. If the gates should go too, that is a separate
work item with its own approval.

**Keep one smaller shared file.** Tidier on disk, and wrong for the reason above — a gate
satisfiable by another node's writing. It also costs more tokens than it saves: one file
re-read and re-appended at six gates, against six files each written once.

**Put `repos:` in `design.md`.** Defensible (which repositories receive code is a design
fact) but one gate further from the PRs being awaited. `tasks.md` was chosen instead — the
artifact the `implementation` node consumes. Both are superseded by
[decision-127](decision-127.md): the owner's review moved the declaration off artifacts
altogether, onto the gate that already freezes every other per-work-item choice.

## Consequences

- **Breaking** for consuming projects: the work-item artifact contract changed. A work
  item in flight keeps walking — its next gate blocks naming the `evidence/<file>.md` to
  write.
- Token cost per work item drops by the template, every `log-entry` append, and every
  prose checkpoint; what remains is written once, only for the phases actually walked.
- `validates:`, `onlyWhenSkipped:` and the skip vocabulary are reused unchanged. The only
  test-infrastructure change is `_SPEC_FILE` in the parity suite, widened so a manifest
  `pathPattern` one directory down (`evidence/x.md`) is matched rather than silently
  excluded.
- the-loop no longer keeps a chronology of its own anywhere. That is the ticket's premise:
  the harness already does, and a second copy is generation billed twice.
