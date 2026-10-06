---
type: design
phase: design
workItem: "github:MadaraUchiha-314/the-loop#472"
status: in-review
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Design: make the phase-selection comment easier to read

> Phase 2 of 4. Derived from [`requirements.md`](requirements.md).

## Overview

**Only the renderer changes.** `_checklist_body` in `cli/the_loop/graph/hooks/selection.py`
builds the comment, and its two helpers `_channel_lines` and `_choice_lines` build two
of its sections. All three are rewritten to a fixed layout. The rows they emit are
byte-identical, so the reply parser and the Slack mirror read the same rows. One small
addition to `cli/the_loop/channels/digest.py` unfolds `<details>` blocks when the comment
is relayed to Slack.

## The layout

```text
## 🤖 the-loop — which phases does this work item need?
> ⚡ Quick start: reply `the-loop execute` with the boxes untouched …
> To tailor it: untick … tick … then reply …
<details> ℹ️ How this works </details>

### 🧩 Phases — ticked ones run
- [x] <phase> …
#### ➕ Optional phases — off unless you tick them     (only when opt-in phases exist)
- [ ] <phase> — <about> …
<details> 🔒 N more phases always run … </details>      (or the ⚠️ "every phase is selectable" line)

### ⚙️ Settings — not phases; each has a default
#### 📍 Where should the outer loop happen?        Default line, row, <details>
#### 📄 Publish the spec chain as a Claude artifact too?
#### 🧵 How many sessions should this work item's pull requests get?
#### 💬 Is this work item worked in a channel of its own?
#### 🛠️ Which harness should this work item run on?   (only when offered)
#### 🧠 Which model should this work item run on?     (only when offered)
#### 🎚️ How hard should it think?                    (only when offered)

### ✅ Ready?
Reply `the-loop execute` …
<!-- the-loop:phase-selection -->
```

The heading levels are deliberate. `##` gives the title GitHub's underline. `###` marks
the two groups and the closing section. `####` marks each question inside a group. A
reader skimming the bold headings sees three groups and, inside the settings group, one
question per heading.

Each question keeps its existing wording. The wording is what a reader already knows,
and what the tests and the Slack control already name.

## Decisions

- **Rows stay outside `<details>`.** GitHub renders a task list inside `<details>`, but a
  collapsed box is a box nobody sees. Hiding a choice would make the default invisible,
  which is the opposite of the issue's aim. The one exception is the list of protected
  phases. Those are bare bullets, not boxes, so collapsing them hides no choice.
- **The default goes before the rows.** The question a skimmer asks is "what happens if
  I leave this alone?" Each setting answers it in one line (`**Default:** …`) before its
  rows. The full explanation moves into `<details>`.
- **One quick-start callout.** The most common answer, "run everything", used to be the
  second-to-last paragraph. It moves to the top, as a blockquote, so a reader sees it
  before any row.
- **The "not a phase" note is said once.** Today five sections each open with "Not a
  phase". The settings group heading now says it once, and the per-section repeats move
  into the collapsed explanations.
- **Summaries are plain text.** GitHub does not reliably render markdown inside
  `<summary>`, so each summary is an emoji plus plain words.
- **The Slack digest unfolds `<details>`.** Slack mrkdwn has no collapsible block, and it
  reads `<…>` as link syntax. So `to_mrkdwn` and `condense` drop `<details>` and
  `</details>` lines and draw `<summary>X</summary>` as `**X**`. Both do it outside
  code, the same way the other line rules are applied. The Block Kit control is drawn
  from the rows alone, so it does not change.

## Alternatives considered

- **A table of settings** (`| setting | default | choose |`). Rejected: a task-list box
  cannot be put inside a table cell, so the rows would move away from their explanations.
- **Collapsing whole sections**, rows included. Rejected for the reason above: a
  collapsed default is an invisible default.
- **GitHub alert blocks (`> [!TIP]`).** Rejected: the Slack digest would show the
  `[!TIP]` marker as literal text, and a plain blockquote with a bold label reads the same
  on GitHub.

## Risks

- **A line that the Slack mirror misreads as a protected phase.** `_PLAIN_ROW` treats any
  bullet holding a single token as an "always runs" phase. The new text has no such
  bullets except the protected list. A test checks that the mirror reads only the graph's
  protected phases as `always`.
