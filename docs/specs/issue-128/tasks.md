---
type: tasks
phase: tasks-breakdown
workItem: issue-128
status: approved             # draft | in-review | approved
approvedBy: []               # tier-3: the human gate is the PR review — see execution-log
overrides: {}
---

# Tasks: portable state — what travels with the work, what belongs to the machine

> Phase 3 of 3. A DAG of small, verifiable tasks, each referencing the requirements it
> satisfies.

```mermaid
graph LR
  T1["T1 declaration<br/>state.py"] --> T2["T2 test S1–S2<br/>(red first)"]
  T1 --> T3["T3 docs/cli/state.md"]
  T3 --> T4["T4 .gitignore"]
  T3 --> T5["T5 test S3–S5"]
  T4 --> T5
  T3 --> T6["T6 links & corrections"]
  T3 --> T7["T7 decision-046 + capability doc"]
  T5 --> T8["T8 evidence + briefing"]
  T6 --> T8
  T7 --> T8
```

## Tasks

- [x] **T1 — declare the generated paths.** `GeneratedPath` + `GENERATED_PATHS` in
  `cli/the_loop/state.py`: five entries (session record, control record, poll state,
  event log, pidfile), each with `attr`, `default`, `portable`, `holds`, `why`. No
  runtime consumer. *(R3.1)*
- [x] **T2 — pin the declaration against the layout (red first).**
  `cli/tests/test_state_portability.py` S1–S2: every public path property of
  `StateLayout` is claimed by an entry, and every entry's `attr`/`default` resolves.
  Written before T1 is complete; verified red by removing an entry. *(R3.2, R5.2)*
- [x] **T3 — write the state reference.** `docs/cli/state.md`: the two kinds of state,
  the classification table (first column = the declaration's `default`), a section per
  file with a JSON example, field table and lifecycle, the hand-off procedure, the
  `~/.the-loop` case, the costs, what must never be carried, and the security note.
  *(R1.1–R1.3, R2.1, R2.3, R2.4)*
- [x] **T4 — apply the recipe here.** Replace this repository's three the-loop state
  blocks in `.gitignore` with the documented block, byte for byte, including dropping
  the blanket ignore of the pre-issue-106 poll state. *(R2.2)*
- [x] **T5 — pin the docs and the recipe.** S3–S5: every declared path documented with a
  matching classification; the block verbatim in `.gitignore`; the block's patterns
  actually ignore the local paths and spare the portable ones. *(R3.3, R3.4, R3.5)*
- [x] **T6 — links and corrections.** Sidebar entry in `docs/.vitepress/config.mts`;
  pointers from `docs/cli/concepts.md`, `docs/cli/index.md` and the `state.root` option;
  delete *"All of it is git-ignored runtime state"* from `docs/config/cli/index.md`.
  *(R1.4)*
- [x] **T7 — record the decision.** `docs/decisions/decision-046.md` + a row in
  `docs/decisions/decisions.md`; behaviour bullet and history row in
  `docs/capabilities/cli.md`. *(R4.1–R4.3)*
- [x] **T8 — evidence and reviewer briefing.** Full suite green, `git check-ignore -v`
  evidence for all five paths, execution log updated, PR briefing posted. *(R5.1, R5.2)*
