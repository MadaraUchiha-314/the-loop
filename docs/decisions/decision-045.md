# Decision 045: `produces` names an artifact, not a filename — several accepted names, exactly one present

- **Status:** proposed
- **Date:** 2026-07-31
- **Deciders:** @MadaraUchiha-314 (issue #124)
- **Work item:** issue-124
- **Spec:** `docs/specs/issue-124/`
- **Refines:** [decision-041](decision-041.md) — which modelled the PDLC as a graph of
  nodes with entry/exit hooks. Nothing in it is reversed; this fills in what a node's
  `produces` entry actually denotes, which 041 left implicit and the shipped graph then
  read as "one entry, one filename".

## Context

[Issue #124](https://github.com/MadaraUchiha-314/the-loop/issues/124). the-loop has
documented two names for the phase-1 spec artifact since long before the process graph
existed: `requirements.md`, **or `bugfix.md` for a bug**. It says so in
`skills/the-loop/SKILL.md`, in `reference/workflow.md`, in `.the-loop/manifest.yaml`
(which tracks `docs/specs/<id>/bugfix.md` with `phase: requirements-definition`), in
`commands/work-on.md` and `commands/work-status.md`, and it ships a
`skills/the-loop/templates/bugfix.md` to author it from.

The graph that landed in [issue-109](../specs/issue-109/) knew one:

```yaml
- id: requirements-definition
  produces: [requirements.md]
```

`validate-artifacts` resolved `produces` literally, so a work item that followed the
documented process was blocked by that same process:

```console
$ uv run the-loop check issue-104 --recompute
  BLOCK  requirements-definition
         · required artifact is missing (docs/specs/issue-104/requirements.md)
```

The graph landed **after** every existing `bugfix.md` (issues 36, 78, 80, 93, 104), so
nothing exercised the combination until #119 — which hit it in CI on #120 and worked
around it by naming the file `requirements.md` while keeping `type: bugfix` front matter.
The workaround was undocumented, so the next bug hit the same wall.

Two things made this more than a typo. First, the same literal name appears in the
`design` node's `enforces-boundaries-from` hook, where an unresolvable upstream returns
**skip** rather than block — so for every bug work item, the check that each trust
boundary raised in phase 1 is answered in the design has never run, while reporting
success. Second, the bundled `bugfix.md` template offers `## Acceptance criteria (EARS)`
where the node requires a `Requirements` section, so correcting only the filename moved
the block one line down.

**Nothing compared the three files that have to agree** — the shipped graph, the manifest
inventory, and the templates an agent actually authors from. That parity gap is the
defect; the naming disagreement is what it let through.

## Decision

**A `produces` entry names an artifact, not a filename. It may accept several names,
separated by `|`. Exactly one of them may be present.**

```yaml
produces: ["requirements.md|bugfix.md"]
```

Both directions, stated explicitly:

| Situation | Verdict | Why |
|---|---|---|
| Exactly one accepted name present | **Validated normally** — `locked`, `frontMatter`, `sections`, `checkmarks`, all unchanged | The name became flexible; the standard the artifact is held to did not move. |
| No accepted name present | **Block**, naming *every* accepted name | An agent cannot write the right file if the block does not say what the right file may be called. |
| More than one present | **Block as ambiguous** | Two artifacts filling one slot have no defined source of truth. A resolver that quietly preferred the first-declared name would approve the gate against whichever the graph happened to list first — possibly the stale one. Fail closed. |

Consequences:

- **One resolver.** `resolve_produces` in `graph/model.py` — the module that already owns
  the `produces` contract — returns one `ArtifactSlot` per entry, carrying the accepted
  names and which of them exist. `hooks/artifacts.py` and `hooks/lint.py` both use it;
  they previously carried a byte-identical private copy each, which is this same defect
  one level down. **The resolver never chooses** between present alternatives: that is a
  policy decision and it belongs to the hook that has to make it.
- **The entry is kept verbatim.** `Node.produces` stores `"requirements.md|bugfix.md"`
  unsplit, so `the-loop graph show --format json` reports what the graph declares rather
  than claiming two artifacts where the graph means one.
- **A malformed entry is a startup failure.** `a||b`, `|a`, `a|` and a bare separator
  raise `GraphConfigError` at compile time, naming the node and the entry — consistent
  with the graph's thesis that every structural failure is a startup failure, and caught
  by the `the-loop graph show --format json` step already in CI.
- **`upstream` resolves the same way.** `enforces-boundaries-from` takes the same
  alternation, and when several accepted names are present it **joins** their bodies
  rather than choosing — a boundary raised in either file still has to be answered
  downstream. This turns a silently-skipping security gate into one that runs.
- **`bugfix.md` is retired from nothing.** It stays a first-class phase-1 artifact name in
  the skill, the reference, the manifest, both command docs and the templates. Consuming
  repositories see no behaviour change on upgrade except gates that now work.
- **One section vocabulary.** `templates/bugfix.md` gains the `## Requirements` heading the
  node requires (EARS criteria nested under it, as `templates/requirements.md` does)
  instead of `sections:` learning its own alternation. One name for one section.
- **Parity is a test, not a convention.** `cli/tests/test_graph_parity.py` asserts, in both
  directions, that every artifact the manifest tracks at a phase is accepted by that
  phase's node, that every name the graph gates is tracked by the manifest, and that every
  gated name has a bundled template which declares the right phase and offers every
  section that node requires. It failed on the tree before this change — twice, once per
  half of the defect.

## Alternatives considered

- **Retire `bugfix.md`; one phase-1 artifact name, with `type: bugfix` front matter
  carrying the distinction** — issue #124's Option 2, and the cheapest to implement: it is
  what #119's workaround already does in practice, and one name means one gate with no new
  syntax. **Rejected by the maintainer**: it changes documented plugin behaviour for
  consuming repositories, which would need the skill, the reference, the manifest, both
  command docs and a migration note for every repo with a `bugfix.md` on disk — a breaking
  change to fix a bug. Keeping both documented shapes working costs one small, testable
  addition to a contract that is the-loop's own and ships with the CLI.
- **List-of-lists — `produces: [[requirements.md, bugfix.md]]`** — needs no parsing and no
  separator to reserve. Rejected: it reads as nesting rather than choice, makes the common
  single-name case irregular, and changes the JSON shape of `graph show` for every
  existing node.
- **Prefer the first declared name when several are present** — rejected. It is the one
  choice that lets a gate pass against a stale artifact while the live one sits beside it,
  and it makes the outcome depend on declaration order in a file most readers never open.
- **Teach `sections:` its own alternation** so the bugfix template could keep
  `## Acceptance criteria (EARS)` — rejected. A second mechanism for a single occurrence,
  and it would leave the-loop with two names for the same *section* as well as two for the
  same file.
- **Rename the five existing `bugfix.md` specs to `requirements.md`** — rejected by the
  maintainer. They are closed work items with merged PRs; nothing re-runs their gates, so
  renaming rewrites history for no gate benefit.
- **Fix the names without adding the parity test** — rejected, and it is the alternative
  that matters most. The naming mismatch is a symptom; three files silently disagreeing is
  the disease. Without the test the next artifact name, section heading or template lands
  the same way, and the only detection mechanism is a person hitting the block.
