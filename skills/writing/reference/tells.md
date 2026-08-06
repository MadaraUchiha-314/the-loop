# Writing tells — the catalogue

Read this during a revise pass, not while drafting. Drafting against a ban-list produces
stilted prose; cutting against one produces short prose.

Tiered by cost, following [avoid-ai-writing](https://github.com/conorbronsdon/avoid-ai-writing)'s
severity model. **P0** never survives review. **P1** is fixed before the PR. **P2** is
polish. Everything below P0 is a judgement call — that skill measured false-positive
rates above 60% on non-native speakers, so treat each entry as a prompt to look, not as a
verdict.

Only the P0 list is mechanically checked, and only in the-loop's own repository. The rest
lives here on purpose: "leverage" and "robust" are ordinary technical English, and a build
that goes red over them is a build people learn to route around.

---

## P0 — never ships

| Tell | Example | Fix |
|---|---|---|
| Chatbot artifact | "I hope this helps!", "Let me know if you have questions", "Feel free to reach out" | Delete. The document is the answer. |
| Assistant self-reference | "As an AI assistant, I…" | Delete. |
| Cutoff disclaimer | "As of my last knowledge update…" | State the date and the source, or say you do not know. |
| Throat-clearing verb | "Let's dive into…", "delve into the details of…" | Start at the point. |
| Hedged filler | "It's worth noting that X", "It is important to note that X" | "X." |
| Slot-fill opener | "In today's fast-paced engineering environment…" | Delete the sentence. |
| Marketing slot-fill | "unleash the power of", "embark on a journey" | Say what it does. |
| Hollow intensifier | "a game-changer" | Give the measurement. |
| Emoji in a heading | `## 🚀 Getting started` | `## Getting started`. Structure carries emphasis. |

## P1 — fix before the PR

**The "not just X — it's Y" reveal.** "This isn't just a config change, it's a shift in
how the-loop thinks about docs." Two claims wearing a costume. Make the claim you mean,
once.

**The triad reflex.** Three parallel items when the content has two, or five. Count the
real ones and list those.

**Restatement closers.** A final paragraph summarising what the reader just read. Cut it;
the spine already front-loaded the conclusion.

**Bold inflation.** More than a couple of **bolded** spans per screen and none of them
reads as emphasis. Bold the term being defined, not the sentence you like.

**Hedge stacking.** "This may potentially help in some cases." Either it does or you do
not know — say which, and say why you do not know.

**Evaluative adjectives with no number.** "Significantly faster", "robust handling",
"comprehensive coverage". Replace with the measurement, the mechanism, or the count. If
none exists, the claim was not ready.

**Uniform paragraph metronome.** Every paragraph three sentences, every sentence the same
length. Real emphasis needs variation. A one-sentence paragraph is allowed to carry the
weight.

**Synonym cycling.** Calling one thing a "budget", a "limit", a "cap" and a "threshold" in
one document. Pick the term; repeat it. Technical prose earns clarity by repetition, not
by variety.

**Unfilled brackets.** `<placeholder>` surviving into a real artifact — outside a
template, where it is the point.

## P2 — polish

- Passive voice hiding the actor: "it was decided" → who decided.
- "In order to" → "to". "Utilize" → "use". "Prior to" → "before".
- Nominalisation: "performs a validation of" → "validates".
- Long-form links: "click here" → link the noun.
- Trailing "etc." where the list should be complete or explicitly open-ended.

---

## Protected content

A revise pass **never** rewrites:

- quoted material, review comments, or anyone else's words;
- code, commands, config values, log lines, test output;
- committed evidence under `<specDir>/<id>/evidence/`;
- EARS criteria, abuse cases, RFC-2119 keywords, API contracts and schema descriptions
  (`userInteraction.writingStyle.formalRegisters`);
- historical specs under `docs/specs/`. They are the record of what was written then.
  Editing one to match today's style destroys the evidence it exists to hold.

## When the budget still will not close

Not a writing problem. One of these is true:

1. **Content is in the wrong document.** Verification detail belongs to
   `testing-plan.md`, not `design.md`. Durable rationale belongs to
   `docs/decisions/decision-<nnn>.md`, not the spec.
2. **The work item is too big.** A design that cannot be described in its budget is
   usually two designs. Split the ticket.
3. **The budget is genuinely wrong for this artifact.** Say so in the document, in one
   sentence, and raise it on the PR. `userInteraction.writingStyle.budgets` is
   configurable; quietly running over it is what makes budgets meaningless.
