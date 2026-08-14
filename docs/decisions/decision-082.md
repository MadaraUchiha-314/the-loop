# Decision 082: the learnings directory is a `workflow` key, and it defaults into `docs/`

- **Status:** proposed
- **Date:** 2026-08-14
- **Deciders:** @MadaraUchiha-314 (owner), the-loop (engineer)
- **Work item:** [issue-224](https://github.com/MadaraUchiha-314/the-loop/issues/224)

## Context

the-loop keeps four trees of checked-in knowledge in a project it works: the per-work-item
specs, the capability docs, the decision log and the learnings. `workflow.specDir` and
`workflow.capabilitiesDir` let a project place the first two. The learnings had no such
key — `learnings/` was written literally into the skill, the automation reference, three
commands and the manifest — so every adopting project got a top-level directory it did not
choose, and this repository kept its learnings outside the `docs/` tree that holds
everything else the loop maintains.

[Issue-224](https://github.com/MadaraUchiha-314/the-loop/issues/224) asks for the key and
for the default to become `docs/learnings`. Two questions had to be answered before either
could be written, and each had an obvious answer that was worth checking.

**Which block does the key belong to?** `selfImprovement` holds every other learnings knob
(`enabled`, `maxIndexLines`, `writeGateOccurrences`) and its descriptions already name the
learnings paths, so a directory key there keeps one feature in one block.

**What happens to a project that already has `learnings/`?** Changing a default changes
where an already-adopted project's loop reads and writes.

## Decision

**The key is `workflow.learningsDir`, default `docs/learnings`, and an existing tree is
relocated only by an operator who says so.**

### The key lives with the other directory keys, not with the lifecycle knobs

Three reasons, in order of weight:

1. **The question being answered is "where do the-loop's documents go?"** — a layout
   question, asked once, about all three trees at the same time. Under `selfImprovement`,
   finding it requires already knowing that learnings are a self-improvement feature.
2. **The onboarding groups make the split expensive.** `x-onboarding` puts `workflow` in
   the `confirm` group — init proposes values and asks the operator to confirm them — and
   `selfImprovement` in `advanced`, where defaults are applied silently and the group is
   only walked on the full tour. A key that determines the project's layout has to be in
   the group that is actually shown.
3. **`capabilitiesDir` is the precedent.** Capability docs are no more a "workflow"
   concept than learnings are; they live under `workflow` because that is where this
   schema puts directory locations. A second convention would be the drift.

The cost is one indirection: `selfImprovement`'s descriptions now point at a key in
another block, which is paid in prose — they name `<workflow.learningsDir>/topics/…` so
the reader is one hop from the answer.

### The default moves, and nothing moves a project's data for it

- `manifest.deprecated` is the wrong tool. `/the-loop:upgrade-the-loop` **deletes** those
  paths, and every existing entry says as much in its `reason` ("SAFE TO DELETE, not a
  migration" — a verbatim copy of a plugin file holding no project data). Learnings are the
  operator's data, so the upgrade command instead **presents both outcomes** — move the
  tree, or pin the old location with `workflow.learningsDir: learnings` — and does neither
  without confirmation.
- **No runtime fallback.** "Use `learnings/` if it exists, else `docs/learnings`" was
  rejected: it gives one question two answers, resolved by whichever directory happens to
  exist. That is the shape of the defect issue-123 produced when two modules each carried
  their own copy of the spec-directory literal. The configured value, defaulted when unset,
  is the single answer.
- **No migration and no version bump.** The key is optional and additive, so a config that
  omits it stays valid.

### One consequence is stated rather than avoided

The default places the learnings **inside the documentation tree**, so a project that
publishes `docs/` publishes its learnings with it. That is the right default for a tree
whose whole purpose is to be reviewed by a human, and the key is the escape hatch for a
project that disagrees. The schema description, the automation reference and the config
reference all say so at the point the operator chooses.

## Consequences

- One new optional property in `harness-config.schema.json`; the template, the packaged
  default and this repository's own config all state `docs/learnings`.
- `learnings/` → `docs/learnings/` in this repository, moved with `git mv` so history
  follows; the manifest's `knowledge` entries follow it.
- The skill, the automation reference and three commands name `<learningsDir>` instead of a
  literal path; `/the-loop:upgrade-the-loop` gains the relocation paragraph.
- The CLI still does not read the learnings tree: `harness_config.READS` is unchanged, so
  the enumerable read surface decision-044 pins does not grow. If a CLI reader is ever
  added, it must apply the containment check `graphlink._is_contained` already applies to
  `specDir`.

## Alternatives considered

| Alternative | Why not |
|-------------|---------|
| `selfImprovement.learningsDir` | Keeps one feature in one block, but hides a layout decision in the `advanced` onboarding group and splits the three directory keys across two blocks. |
| Leave the default at `learnings/` and only add the key | Answers half the ticket. The root-level directory is the complaint; a default nobody changes is the behaviour everyone gets. |
| Runtime fallback to a legacy `learnings/` | Two answers to one question, resolved by filesystem state. See above. |
| `manifest.deprecated` entry for `learnings/` | That mechanism deletes; these are the operator's files. |
