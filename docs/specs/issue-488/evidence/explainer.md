---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#488"
---

# Explainer: the explainer, the spec quiz and the code quiz

> Written by hand during review. This work item was in flight when its own feature
> landed, so `spec-explainer`, `spec-quiz`, `code-explainer` and `code-quiz` were walked
> past as `not-offered`. The page follows `skills/the-loop/reference/explainer.md` and
> is built from `templates/explainer.html` with the engine unchanged. No gate reads this
> record for #488. It exists so the reviewer briefing can link the page.

## Explainer

| Field | Value |
|---|---|
| Depth | deep |
| Location | https://claude.ai/artifact/NCGgpPaJ1FudgCfE3WKzbK |
| Published as | own artifact |
| Questions | 5 (spec quiz) + 5 (code quiz) |

**Why `deep`:** a new concept (attributable quiz gates), a new event kind, a contract
change to `list-comments` (`isSelf`), and tier 4.

**Quiz rules (R6), checked before publishing:**

- **Correct answers are balanced across positions:** spec `1,2,0,3,1`, code `2,0,3,0,1`.
- **The correct option is never the longest one.** Lengths were measured, and three
  options were rewritten to fix that.
- **No trivia:** no line numbers or file names are asked.
- **Each `why`** names the misunderstanding behind the tempting wrong answer.
- **The spec quiz stays at the spec's level, and the code quiz mixes the two.**

**One render check (phone width, dark):**

- no page errors;
- no horizontal scroll at 400 px;
- 5 + 5 questions render;
- feedback appears only after a choice.

**Privacy:** the artifact is private to the operator. It is not committed, so the
redaction grep does not apply. It holds no credential, hostname or personal data beyond
public GitHub logins.
