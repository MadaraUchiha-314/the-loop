---
type: requirements
phase: requirements-definition
workItem: "github:MadaraUchiha-314/the-loop#472"
status: in-review            # draft | in-review | approved — tier 3: the PR approval is the human gate
approvedBy: []
collaborators: [engineer]
overrides: {}
riskTier: 3                  # user-facing copy of the one gate every work item answers; parser untouched
---

<!-- Authored per the the-loop:writing skill. -->

# Requirements: make the phase-selection comment easier to read

> Phase 1 of 4 (requirements → design → testing plan → tasks). Tier 3
> (`human-approves-pr`): the change is the layout of the comment every work item's
> author answers first. The rows it carries, the grammar a reply is parsed with and what
> gets frozen are unchanged. No credential, token scope or sensitive path is touched.

## Introduction

[Issue #472](https://github.com/MadaraUchiha-314/the-loop/issues/472): "Make the phase
selection comment easier to read."

**What is broken.** The `phase-selection` checklist is one long run of bold paragraphs.
With harness, model and effort declared, it is about 960 words, and every section carries
its own explanation inline. A reader has to read all of it to find what to tick. The
sections are not visibly separated: each one opens with a bold sentence, so the reader
cannot tell where the phases end and the settings begin.

**What this changes.** The issue asks for clear sections, collapsible explanations
(`<details>` and `<summary>`), emoji in the section headings, and any other way to make
the text easier to read. The comment keeps every row and every word of explanation. It
changes how they are laid out:

- a heading per section, each opened by an emoji;
- a quick-start line at the top, saying the one reply that runs the full process;
- the phases and the settings split into two groups;
- each setting's default stated in one line, before its rows;
- every explanation collapsed under a `<details>` block.

## Requirements

### Requirement 1: sections a reader can tell apart

**User story:** As the author of a work item, I want the checklist split into labelled
sections, so I can find the question I care about without reading the rest.

#### Acceptance criteria (EARS)

1.1 The checklist SHALL open with a heading naming the question ("which phases does this
work item need?").

1.2 The checklist SHALL render each question as its own markdown heading, and each
heading SHALL start with an emoji that no other heading in the comment uses.

1.3 The checklist SHALL group the phase rows under one heading, and SHALL group every
setting that is not a phase under a second heading that says so.

1.4 WHEN the loop owns no outer loop (a contribution) THEN the settings group SHALL say so
in place of the surface and Claude-artifact sections, as it does today.

### Requirement 2: the action first, the explanation on demand

**User story:** As the author, I want to see what to do and what happens by default
before any explanation, so a full-process reply takes seconds.

#### Acceptance criteria (EARS)

2.1 The checklist SHALL state, before any row, that replying the execute keyword with the
boxes untouched runs the full process, and how to tailor the selection instead.

2.2 Each setting section SHALL state its default in one line before its rows.

2.3 Every explanatory paragraph SHALL be inside a `<details>` block whose `<summary>`
says what it explains. No row, and no default line, SHALL be inside a collapsed block,
except the list of phases that always run.

2.4 The checklist SHALL end with a short section saying how to answer.

2.5 The checklist SHALL keep every fact it states today: no explanation is removed, only
moved under a `<details>` block.

### Requirement 3: the reply contract does not move

**User story:** As the operator, I want the reformatting to leave every reader of the
comment working, so nothing that parses it breaks.

#### Acceptance criteria (EARS)

3.1 Every row SHALL keep its exact shape (`- [x] <phase>`, ``- [ ] `<token>` — <about>``)
and its order, so `_parse_selection` and the Slack mirror's `selection_rows` read the
same rows from it as before.

3.2 The protected phases SHALL stay bare bullets (`- <phase>`), which is what the Slack
mirror reads as "always runs". No other line in the comment SHALL have that shape.

3.3 The comment SHALL still end with the selection marker and the self-authored stamp.

3.4 WHEN the checklist is drawn as Slack mrkdwn or condensed into a digest THEN
`<details>` and `</details>` SHALL be dropped, and a `<summary>` SHALL be drawn as a bold
line, so no raw HTML reaches a room.
