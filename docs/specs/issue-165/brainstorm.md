---
type: brainstorm
phase: brainstorming
workItem: issue-165
status: approved              # draft | in-review | approved  (approved == "locked")
approvedBy: []                # recorded on the PR review (paper trail)
collaborators: [product-manager, architect, engineer]
overrides: {}
---

# Brainstorm: writing the-loop's artifacts for a human reader

> Phase 0 — the root artifact. Carries the **literature survey**
> [issue #165](https://github.com/MadaraUchiha-314/the-loop/issues/165) asks for, and the
> reasoning that produced `requirements.md`.

## Problem / opportunity

the-loop's artifacts are written for the agent that produced them, not the human who has
to approve them. `docs/specs/issue-163/requirements.md` is 30 KB. `SKILL.md` is 307
lines. The reviewer's job is to say yes or no, and the document makes them read an essay
first.

Two forces made it that way, and both are in the harness by design:

- Every phase gate demands a section, so an artifact grows a section per gate whether or
  not that gate has anything to say for this work item.
- `tokenEconomy.outputVerbosity` compresses **chat output** and explicitly preserves
  `specs` — so the one lever the-loop already has for verbosity is aimed away from the
  documents the reviewer actually reads.

## Constraints

- **EARS stays formal.** `WHEN … THEN the system SHALL …` is a testable contract, not
  prose. Same for schema `description`s and API contracts. Any style rule has to carve
  these out or it breaks the requirements gate.
- **No gate may weaken.** Succinct cannot mean "drop the Security considerations
  section". Brevity is about words, not coverage.
- **Diagrams are already mandated** (`userInteraction.diagramFormat: mermaid`) but only
  *permitted*, never *preferred* — nothing says "draw this instead of describing it".
- Whatever ships must be enforceable by something other than good intentions. issue-124
  and issue-148 are both this repo learning that prose describing a rule does not execute
  it.

## Literature survey (issue #165, bullet 5)

Surveyed August 2026. Four skills, one style-guide tradition, one docs framework.

| Prior art | What it does | What we take | What we leave |
|---|---|---|---|
| [avoid-ai-writing](https://github.com/conorbronsdon/avoid-ai-writing) (MIT) | Audits 21 categories of machine writing across 7 buckets — formatting, sentence structure, word tiers, slot-fill templates, structure, filler, rhythm. Severity tiers P0/P1/P2; modes detect / rewrite / edit; context + voice profiles. Explicitly warns the patterns are signals, not proof (>60% false positives on non-native speakers). | The **severity tiering** and the **detect-before-rewrite** order. The false-positive warning — it is why our mechanical check is P0-only. | The 21-category word lists. A ban on "leverage" is a lint rule, not a writing model, and this repo's prose is technical enough to trip it constantly. |
| [anti-ai-slop-writing](https://github.com/jalaalrd/anti-ai-slop-writing) (MIT) | 50+ flagged words, 35+ phrases, 16 banned openers, plus structural rules (rule-of-three, uniform sentence length, em-dash overuse). Core file under 500 lines with a separate vocabulary reference. | The **two-file shape** — a short contract plus a long catalogue — which is the shape our own skill uses. | The vocabulary ban list, for the same reason. Also: a blanket em-dash ban would rewrite most of this repository for no reader benefit. |
| Stop Slop | Editor-style pass that cuts filler, jargon and throat-clearing openers while preserving voice. | "Throat-clearing opener" as the single highest-yield cut. | Nothing else — it overlaps the two above. |
| Technical-writing-expert skills (several) | Turn the agent into a docs specialist for READMEs and API references. | Nothing. They generate documentation; our problem is that we already generate too much of it. | The whole thing. |
| Plain-language style guides (Google / Microsoft / GOV.UK) | Short sentences, active voice, second person, front-loaded conclusions, no hedging. | **Front-load the conclusion** and **one idea per paragraph** — the two rules that survive translation into an agent instruction. | Register advice (contractions, "you") that fights the formal carve-out. |
| [Diátaxis](https://diataxis.fr) | Documentation splits into tutorial / how-to / reference / explanation; mixing modes is the root cause of bloat. | The **diagnosis**: our artifacts bloat because each one mixes explanation with reference. The fix is a per-artifact *shape*, not a per-sentence rule. | Adopting the four-mode taxonomy wholesale. the-loop's artifacts already have names and gates. |

**What the survey settles.** Every existing skill treats this as a *vocabulary* problem —
ban words, rewrite sentences. That is the wrong altitude for us. A 30 KB requirements
document does not get better by removing "leverage" from it; it gets better by being 3 KB.
So the-loop's skill is about **shape and budget** first (what a document is allowed to
contain, and how long), and about tells second — and the tells chapter borrows from the
prior art rather than re-deriving it.

**Register, don't vendor.** decision-005 already settled this pattern for `caveman` and
`ponytail`: the-loop implements the technique natively and lists the third-party skill in
`externalTools` so an operator who prefers the packaged version can install it. The three
MIT skills above get the same treatment.

## Options considered

- **Option A — prose guidance only.** Add a "be concise" bullet to `SKILL.md`.
  *Rejected:* that bullet already exists in spirit (`prSummary.condensed`) and the specs
  are still 30 KB. Unenforced prose is what issue-148 was about.
- **Option B — a hard gate on word count.** A graph hook that blocks the phase when
  `design.md` exceeds N words. *Rejected:* readability is a judgement, and a gate that
  misfires is a gate people route around (the same reasoning `test_docs_parity` gives for
  checking presence rather than value). A budget that blocks would be gamed by moving
  prose into an appendix.
- **Option C — a skill plus budgets in the templates, with a narrow mechanical test.**
  The skill carries the judgement; the templates carry the budget where the author is
  already looking; the test guards only what is mechanical (the contract is present, the
  P0 tells are absent, the skill obeys its own budget). **Chosen.**
- **Option D — a `the-loop writing lint` CLI command.** *Deferred:* it needs a core →
  API → client slice (issue-161's contract) to earn its place, and nothing yet says the
  advisory test is insufficient. Revisit if the budgets are ignored in practice.

## Open questions

1. Should the budgets block a phase gate rather than advise? Leaning no — see Option B.
   Raised for the reviewer.
2. Does the concise register apply to the reference docs under `skills/the-loop/reference/`,
   or only to per-work-item artifacts? Leaning: the register applies everywhere, the
   budgets only to the artifacts (a reference doc is read once, a spec is reviewed under
   time pressure).

## Hand-off → requirements

Carried forward: a bundled writing skill (contract + tells catalogue), a
`userInteraction.writingStyle` config block with per-artifact budgets, the diagram-first
rule, the formal carve-out, budgets written into the templates, and a parity test. Left
behind: word ban-lists, blocking gates, a CLI linter.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109).
