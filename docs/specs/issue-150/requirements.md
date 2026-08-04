---
type: requirements
phase: requirements-definition
workItem: "issue-150"
status: approved
approvedBy: [MadaraUchiha-314]
collaborators: [engineer]
overrides: {}
---

# Requirements: Replace the README workflow mermaid diagram with an Excalidraw diagram

> Phase 1 of 3 (requirements → design → tasks). Tier 1–2 (trivial docs change,
> `autonomy.tiers` → autonomous-complete): this spec is deliberately compact. The
> requirement is the operator's direct, unambiguous instruction — "create an excalidraw
> diagram instead of the mermaid diagram for the workflow depicted in README.md" — and
> they asked to iterate on the result through the PR, which stands as the phase
> approval ([issue #150](https://github.com/MadaraUchiha-314/the-loop/issues/150)).

## Introduction

The README's "The loop, in one line" section depicts the workflow as a mermaid
`flowchart TD`. The operator wants that hero diagram to be a hand-drawn-style
Excalidraw diagram instead, without losing any of the information the mermaid
version carries.

## Requirements

**User story:** As a reader of the README, I want the workflow diagram as an
Excalidraw drawing, so the project's hero visual is friendlier while carrying the
same information.

Acceptance criteria (EARS):

1. WHEN the README is viewed on GitHub THEN the system SHALL render an Excalidraw
   workflow diagram in place of the mermaid `flowchart TD` block.
2. WHEN the diagram is compared with the removed mermaid original THEN the system
   SHALL preserve every node, edge, edge label ("convert", "human review"), the two
   zone groupings, and the `loop:<phase>` labels.
3. WHEN a contributor wants to edit the diagram THEN the system SHALL provide a
   checked-in editable source that opens at excalidraw.com.

## Security considerations

Threat-model-lite: no untrusted actors, no trust boundary is created or moved, and
no abuse case applies — the change is a static image plus markdown in a public
README. The only vector considered is the embedded image itself: SVG can carry
scripts, so the export must contain no scripting (verified in design). No new attack
surface.
